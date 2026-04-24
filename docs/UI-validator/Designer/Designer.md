# UI-Validator Designer - Documentazione

## 1. Introduzione

Il **Designer** è uno strumento per registrare sequenze di azioni UI (click, input, scroll, drag) su uno schermo. Durante la registrazione, cattura screenshot, genera BBox intelligenti usando edge detection, estrae testo con OCR (EasyOCR) e feature vector con ResNet18. Tutto viene salvato in un database SQLite per revisione e modifica successiva.

**Workflow principale**:
- **Create Session** → Registra azioni con Mini UI
- **Dati salvati** → DB + screenshot PNG
- **Summary Screen** → Visualizza e modifica i dati

---

## 2. Pagine Disponibili

### 2.1 Create Screen (`designer_create.py`)

Schermata iniziale per creare una nuova registrazione.

**Elementi**:
- **Nome Sessione** (TextInput): Nome univoco per la sessione
- **Cartella Output** (FileBrowser): Cartella dove salvare i dati
- **Monitor Selezionato** (Spinner): Quale monitor usare per la registrazione
- **Pulsante "Avvia Registrazione"**: Inizia la registrazione

**Flusso**:
1. User inserisce dati
2. Valida input (nome non vuoto, cartella esistente, monitor selezionato)
3. Crea cartella progetto: `{output_folder}/{session_name}/`
4. **Minimizza Kivy window** (SW_MINIMIZE)
5. Lancia `main_designer.py` in subprocess con argomenti
6. Background thread in attesa di `session_done.json`
7. Quando subprocess finisce:
   - Ripristina Kivy window (SW_RESTORE, SetForegroundWindow)
   - Carica sessione nel Summary Screen
   - Naviga a Summary Screen

---

### 2.2 Open Screen (`designer_open.py`)

Schermata per aprire una sessione esistente.

**Elementi**:
- **Cartella Designer** (FileBrowser): Cartella progetto
- **Pulsante "Apri Registrazione"**: Carica la sessione

**Flusso**:
1. User seleziona cartella progetto
2. Valida che la cartella contiene un database
3. Carica sessione dal DB
4. Naviga a Summary Screen

---

### 2.3 Summary Screen (`designer_summary.py`)

Schermata per visualizzare, modificare e salvare una sessione registrata.

**Layout**:
```
[< Back]  Designer — Session: xxx (N steps)
──────────────────────────────────────────────
│ LEFT PANEL      │  RIGHT PANEL             │
│ Steps list:     │  Screenshot viewer:      │
│  1 CLICK        │  ┌────────────────────┐  │
│  2 INPUT        │  │ [BBox overlays]    │  │
│  3 DRAG_DD      │  │ [Click dots]       │  │
│  4 SCROLL       │  │ (fit_mode: contain)│  │
│                 │  └────────────────────┘  │
│                 │  Metadata bar:           │
│                 │  OCR: [text...]          │
│ [Save]          │  ResNet: [512-dim...]    │
└─────────────────┴──────────────────────────┘
```

**Funzionalità**:
- **Step list** (sinistra): Scorri e clicca per visualizzare uno step
- **Screenshot** (destra): Image viewer con `fit_mode: "contain"` (responsive)
- **BBox interattive**:
  - Drag interior → sposta BBox
  - Drag edge/corner → ridimensiona
  - Hover → cursor diventa "hand"
- **Metadata bar**: Mostra OCR text e ResNet features
  - **Single-action steps**: 1 BBox
  - **DRAG_AND_DROP**: 2 BBox (start + end) con info per entrambe
- **Save button**: Ricavola OCR/ResNet per BBox modificate, salva in DB
  - Disabilitato se nessuna modifica
  - Lancia worker process `_ocr_feature_update.py` per ogni BBox modificato

---

## 3. Flusso Operativo quando Avvio Esecuzione - DETTAGLIATO

### 3.1 User Usage - Mini UI Color, F9, ESC, Ctrl

#### Mini UI Layout (Dark Theme, Bottom-Left)
```
● REC  Step 1     [F9]
```
- Larghezza: 135px, Altezza: 28px
- Posizionamento: Angolo inferiore sinistro dello schermo
- Sempre in primo piano (topmost), semi-trasparente (alpha: 0.92)

#### Colori
| Elemento   | Colore                     | Significato                       |
|------------|----------------------------|-----------------------------------|
| `●` Dot    | Arancione (#f39c12)        | Recording in progress             |
| **REC**    | Testo bianco, sfondo rosso | Status label                      |
| **Step N** | Testo grigio               | Numero del next step da catturare |
| **[F9]**   | Arancione button           | Input finalizer button            |

#### Controls
| Azione | Effetto |
|--------|---------|
| **ESC** | Termina registrazione, chiude Mini UI, scrive `session_done.json`, esce |
| **F9** | Finalizza INPUT (quando in text field): chiama `_finalize_input_action()` |
| **ENTER** | Aggiunge newline al testo (quando in INPUT): continua l'input |
| **CTRL+C** | Fallback per terminare (se ESC non funziona) |
| **Click mouse** | Cattura SINGLE_CLICK: genera BBox, OCR, ResNet |
| **Double-Click** | Cattura DOUBLE_CLICK: stessa logica di SINGLE_CLICK |
| **Right-Click** | Cattura RIGHT_CLICK: stessa logica di SINGLE_CLICK |
| **Drag mouse** | Cattura DRAG_AND_DROP: 2 BBox (start + end) |
| **Scroll mouse** | Cattura SCROLL: registra dx, dy |
| **Keyboard type** | Cattura INPUT: F9 per finire, ENTER per andare a capo, ricava BBox dal buffer screenshot |

#### Mini UI States

1. **Rosso (Saving)** - Modelli OCR/ResNet in precaricamento, oppure step in salvataggio
2. **Verde (Ready)** - Pronto a catturare azioni
3. **Step N** - Numero aggiornato per ogni step completato

---

### Dettagli Fase di Registrazione

#### Fase 1: Inizializzazione

```
1. User clicca "Avvia Registrazione" in Create Screen
2. Valida input (nome, cartella, monitor)
3. Crea cartella progetto: {output_folder}/{session_name}/
4. Crea sottocartella: {project}/screenshots/
5. Minimizza Kivy window (ShowWindow, SW_MINIMIZE)
6. Lancia main_designer.py in subprocess:
   - main_designer.py session_name output_folder monitor_num
```

**main_designer.py initialization**:
```python
1. Add project_root to sys.path
2. DesignerApp.__init__(session_name, db_path, monitor_num)
3. app.start():
   - Create DesignerSession in DB (ottiene session_id da autoincrement)
   - Ottieni monitor info da mss (resolution, position)
   - Setup logging con colored output
   - Crea ScreenshotHandler
   - Crea MiniUI (tkinter, dark theme)
   - wait_for_screen_stability() - attende schermo stabile
   - set_loading() - rosso UI
   - Crea ActionCapture con global hooks
   - start_recording() - mouse + keyboard listening
   - Preload models in background thread:
     - OCRGenerator().extract(dummy_image)
     - FeatureGenerator().extract(dummy_image)
   - set_ready() - verde UI
   - Entra in loop while not should_stop
4. Quando user preme ESC:
   - should_stop = True
   - Esce dal loop
   - _cleanup()
   - Scrive session_done.json con session_id + db_path
   - main_designer.py esce
```

#### Fase 2: Recording Loop

```
while not should_stop:
  - mini_ui.update()
  - Aspetta mouse/keyboard events (global hooks)
  - Quando evento rilevato:
    - ActionCapture._on_mouse_event() / _on_key_event()
    - Cattura coordinate/testo
    - screenshot_handler.wait_for_screen_stability()
    - Prende screenshot dal buffer
    - Chiama on_action_callback
  - Aggiorna Mini UI Step counter
  - Attende stabilità prima del prossimo step
```

#### Fase 3: Action Capture e Salvataggio

Quando un'azione viene catturata:

```
1. _on_action_captured(action_dict):
   - Salva screenshot come PNG in {project}/screenshots/step_NNN.png
   - Estrae BBox intelligente dalle coordinate click
   - Estrae OCR text da BBox
   - Estrae ResNet 512-dim features da BBox
   - _save_step_to_db():
     - Crea DesignerStep object
     - Salva nel DB
   - Incrementa step_count
   - Aggiorna Mini UI con nuovo numero step
   - Attende stabilità schermo

2. Per DRAG_AND_DROP:
   - Cattura 2 coordinate (start + end)
   - Genera 2 BBox (uno per start, uno per end)
   - Estrae OCR + ResNet per entrambe
   - Salva entrambe nel DB (drag_end_bbox, drag_end_ocr_text, drag_end_features)

3. Per INPUT:
   - Buffer screenshot è quello di PRIMA che l'utente inizi a digitare
   - Utente digita testo (ENTER per andare a capo)
   - User preme F9 per finalizzare
   - Ricava BBox dal buffer screenshot
   - Estrae OCR + ResNet da BBox
   - Salva nel DB con input_text, bbox, ocr_text, features
```

#### Fase 4: Terminazione

```
User presses ESC:
1. ActionCapture.listener.stop()
2. ActionCapture._cleanup()
3. should_stop = True
4. Main loop exits
5. Write session_done.json:
   {
     "session_id": 1,
     "db_path": "C:/.../{session_name}.db",
     "monitor_info": {left, top, width, height}
   }
6. main_designer.py exits
```

**designer_create.py** (background thread):
```
1. Aspetta proc.wait() (subprocess finito)
2. Legge session_done.json
3. Clock.schedule_once(_on_session_done, 0)  # Kivy thread-safe
4. _on_session_done():
   - ShowWindow(hwnd, SW_RESTORE)
   - SetForegroundWindow(hwnd)
   - summary.load_session(session_id, db_path)
   - Navigate to "designer_summary"
```

---

## 4. Flusso Operativo quando Sono in Summary Table

### Loading Sessione

```
1. designer_summary.load_session(session_id, db_path) è chiamato
   - Salva session_id e db_path come attributi
   - Setta _pending_load = True

2. on_enter() è chiamato (Kivy lifecycle):
   - Controlla _pending_load
   - Clock.schedule_once(_populate, 0)  # Kivy thread-safe

3. _populate():
   - Apre DesignerDatabase(db_path)
   - db.get_session(session_id)
   - db.get_steps(session_id)  # Ordered by step_number
   - Chiude DB
   - Setta session_label con info
   - Chiama _build_step_list()

4. _build_step_list():
   - Crea StepRow per ogni step
   - Aggiunge alla ScrollView (left panel)
   - Seleziona primo step automaticamente
```

### Viewing Step

```
1. User clicca su StepRow:
   - _on_step_selected(row)
   - Trova step nella lista usando step_number
   - Log: "Step X bbox detected: (x,y,w,h)"
   - _show_step_image(step)

2. _show_step_image(step):
   - Decodifica screenshot PNG bytes → numpy BGR
   - Salva come self._current_screenshot_bgr
   - _draw_overlays(bgr, step):
     - Legge bbox coordinate da JSON
     - Disegna rettangolo (rosso per start, viola per end)
     - Legge coordinate click da JSON
     - Disegna cerchio al click point
     - Ritorna annotated BGR
   - Converte BGR → RGB
   - Flip verticale (OpenCV y=top, Kivy y=bottom)
   - Crea Kivy Texture
   - Binda touch events per bbox interazione
   - _update_metadata(step):
     - Mostra OCR text (primo 100 char)
     - Mostra ResNet info (512-dim vector)
     - Per DRAG_AND_DROP: mostra info di entrambe le BBox
```

### Modifying BBox

```
1. User tocca BBox:
   - _on_image_touch_down():
     - Converte widget touch coord → image coord
     - Cerca quale BBox è stato toccato
     - Individua edge (move, corner, edge)

2. User trascina:
   - _on_image_touch_move():
     - Calcola delta da ultima posizione
     - _apply_bbox_drag():
       - Applica movimento/ridimensionamento
       - Clamp per rimanere dentro immagine
       - Aggiorna bbox coordinates
     - _redraw_image_with_modified_bbox():
       - Disegna preview con bbox modificata

3. User rilascia:
   - _on_image_touch_up():
     - Finalizza drag
     - Salva bbox modificata in step object
     - Log: "Bbox N moved/resized: (x,y,w,h)"
     - Marca step come modificato in _modified_steps
     - Attiva Save button
     - Ridisegna immagine con bbox finale
```

### Saving Modified BBox

```
1. User clicca Save:
   - save_session():
     - Per ogni step in _modified_steps:
       - _process_input_action():
         - Decodifica screenshot PNG
         - Legge bbox JSON
         - BBoxGenerator.crop_image() per croppare
         - Lancia _ocr_feature_update.py in subprocess:
           - ./src/app/core/designer/_ocr_feature_update.py
           - Argomenti: screenshot_path bbox_json
           - Output: {"ocr_text": "...", "features": "hex_string"}
         - Riceve output JSON
         - Converte hex → bytes
         - Salva step.ocr_text, step.features
       - Per DRAG_AND_DROP: processa anche drag_end_bbox

2. Dopo tutti i worker process finiti:
   - Apre DB connection
   - db.update_step(session_id, step) per ogni step
   - Ricarica steps da DB:
     - Ricorda step_number dello step corrente
     - Ricarica tutti gli steps
     - Trova step con stesso step_number
     - _show_step_image() per ridisegnare con dati aggiornati
   - Resetta _modified_steps
   - Disabilita Save button
```

### Navigating Back

```
User clicca "< Back":
  - go_back():
    - _clear_image()
    - Navigate to "main" screen
    - manager.transition.direction = "right"
```

---

## 5. DB (Database)

**Tipo**: SQLite  
**Percorso**: `{project_folder}/{session_name}.db`  
**Auto-creazione**: Prima volta che DesignerDatabase() è inizializzato

### Schema

**Tabella: designer_session**
```sql
CREATE TABLE designer_session (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  name         TEXT NOT NULL,
  created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
)
```

**Tabella: designer_step**
```sql
CREATE TABLE designer_step (
  id                      INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id              INTEGER NOT NULL FOREIGN KEY REFERENCES designer_session(id),
  step_number             INTEGER NOT NULL,
  action_type             TEXT NOT NULL,  -- SINGLE_CLICK, DOUBLE_CLICK, RIGHT_CLICK, SCROLL, INPUT, DRAG_AND_DROP
  
  -- Screenshot and coordinates
  screenshot              BLOB,  -- PNG bytes
  screenshot_path         TEXT,  -- File path
  coordinates             TEXT,  -- JSON {"x": int, "y": int}
  
  -- Main BBox and extraction
  bbox                    TEXT,  -- JSON {"x": int, "y": int, "w": int, "h": int}
  ocr_text                TEXT,  -- Extracted text
  features                BLOB,  -- ResNet18 512-dim vector as bytes
  
  -- Action-specific
  input_text              TEXT,  -- For INPUT action
  press_enter_after       BOOLEAN DEFAULT FALSE,
  
  -- For SCROLL action
  scroll_dx               INTEGER,
  scroll_dy               INTEGER,
  
  -- For DRAG_AND_DROP action (second BBox)
  drag_end_coordinates    TEXT,  -- JSON {"x": int, "y": int}
  drag_end_bbox           TEXT,  -- JSON {"x": int, "y": int, "w": int, "h": int}
  drag_end_ocr_text       TEXT,  -- Extracted text from drag_end BBox
  drag_end_features       BLOB,  -- ResNet18 512-dim vector for drag_end BBox
  
  created_at              DATETIME DEFAULT CURRENT_TIMESTAMP
)
```

### Operazioni

**Da main_designer.py**:
- `db.create_session(name)` → crea DesignerSession, ritorna session object con ID
- `db.add_step(session_id, step)` → inserisce nuovo DesignerStep

**Da designer_summary.py**:
- `db.get_session(session_id)` → ritorna DesignerSession object
- `db.get_steps(session_id)` → ritorna lista di DesignerStep ordinati per step_number
- `db.update_step(session_id, step)` → aggiorna step esistente nel DB
- `db.close()` → dispone connection pool

---

## 6. Modelli Utilizzati

### 6.1 BBox (Bounding Box Generator)

**File**: `_bbox_generator.py`  
**Classe**: `BBoxGenerator`  
**Metodo**: `generate_smart_bbox(screenshot, click_x, click_y)`

#### Algoritmo (Multi-method approach)

```python
1. Canny Edge Detection (ultra-sensibile):
   - threshold1 = 5, threshold2 = 30
   - Morphological close + dilate

2. Adaptive Thresholding:
   - GAUSSIAN_C, kernel 15x15
   - Dilate

3. Multiple Binary Thresholds:
   - Dark areas (threshold 100)
   - Light areas (threshold 150 inverted)
   - Combina con bitwise_or

4. Contour Finding:
   - Trova contours da tutti i metodi
   - Filtra per contour vicino al click point (euclidean distance)
   - Seleziona più grande contour nell'area

5. Output BBox:
   - min_size = 5px
   - max_size = 1000px
   - Ritorna {"x": int, "y": int, "w": int, "h": int}
```

#### Output Format
```json
{
  "x": 100,      // Top-left X coordinate
  "y": 200,      // Top-left Y coordinate
  "w": 150,      // Width
  "h": 80        // Height
}
```

#### Salvataggio
- Serializzato come JSON string nel campo `bbox` del DB
- Per DRAG_AND_DROP: 2 BBox in `bbox` e `drag_end_bbox`


TOOD: MIGLIORARE LA RILEVAZIONE DELLE BBOX

---


### 6.2 OCR (Optical Character Recognition)

**File**: `_ocr_generator.py`  
**Classe**: `OCRGenerator`  
**Metodo**: `extract(bbox_image)`

#### Modello: EasyOCR

**Configurazione**:
- Language: `['en']` (English only)
- GPU: `False` (CPU processing)
- Lazy initialization (first call preloads model)

#### Algoritmo

```python
1. Lazy load EasyOCR Reader (first call):
   easyocr.Reader(['en'], gpu=False)

2. readtext(bbox_image):
   - Ritorna lista di tuples: [(text, confidence), ...]
   - Estrae tutti i testi

3. Join testi con spazio
4. Strip whitespace
5. Ritorna string (empty string se nessun testo)
```

#### Output Format
```python
"Extracted text from BBox"  # Plain string
```

#### Salvataggio
- Serializzato direttamente nel campo `ocr_text` del DB
- Max 255 chars (dipende da TEXT column type)
- Per DRAG_AND_DROP: 2 OCR in `ocr_text` e `drag_end_ocr_text`

#### Performance
- Primo load: ~2-3 secondi (preload in background thread)
- Successivi: ~0.5-1 secondo per BBox

---

### 6.3 ResNet (Residual Network Features)

**File**: `_feature_generator.py`  
**Classe**: `FeatureGenerator`  
**Metodo**: `extract(bbox_image)`

#### Modello: ResNet18 Pretrained

**Configurazione**:
- Base: ResNet18 (torchvision.models.resnet18)
- Pretrained: True (ImageNet weights)
- Devices: GPU se disponibile, altrimenti CPU
- Lazy initialization (first call preloads model)

#### Architettura

```
ResNet18 (pretrained su ImageNet)
  ├─ Layer 1-4: Feature extraction
  └─ Rimuovi final classification layer
  → Global Average Pooling
  → 512-dim feature vector
```

#### Algoritmo

```python
1. Lazy load ResNet18:
   - models.resnet18(pretrained=True)
   - Remove final FC layer (classification)
   - nn.Sequential(*children[:-1])
   - model.eval() (inference mode)
   - GPU se disponibile

2. Preprocessing:
   - np.ndarray BGR → PIL.Image RGB
   - Resize(256) → CenterCrop(224)
   - ToTensor()
   - Normalize(ImageNet mean/std)
   - batch_size=1

3. Forward pass:
   - model(tensor) → output
   - Output shape: (1, 512) dopo global avg pool

4. Output:
   - Detach + CPU + numpy
   - Shape: (512,)
   - dtype: float32

5. Ritorna numpy.ndarray (512,)
```

#### Output Format
```python
numpy.ndarray, dtype=float32, shape=(512,)
# Serializzato come bytes nel DB:
array.astype(np.float32).tobytes()  # 2048 bytes
```

#### Salvataggio
- Salvato come BLOB nel campo `features` del DB
- In _ocr_feature_update.py: convertito a hex string per JSON
- In DB storage: convertito da hex back to bytes
- Per DRAG_AND_DROP: 2 features in `features` e `drag_end_features`

#### Performance
- Primo load: ~5-10 secondi (preload in background thread)
- Successivi: ~0.2-0.5 secondi per BBox
- GPU: ~5x più veloce

#### Utilizzo
- **Matching**: Confronta similarity tra elementi visualmente simili
- **Clustering**: Raggruppa elementi per feature similarity
- **Search**: Find visually similar elements in session
