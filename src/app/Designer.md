# UI-Validator Designer - Documentazione Completa

## 1. Flusso Operativo Dettagliato

### 1.1 Avvio Sessione
Quando clicchi **"Avvia Registrazione"** in Designer Create:

    [Kivy Main Window - DesignerCreateScreen]
      |
    Valida input (nome sessione, cartella output, monitor)
      |
    Verifica che nel Folder di destinazione non esista un folder con lo stesso nome
      +- Se esiste -> Mostra errore "Sessione gia esiste"
      +- Se non esiste -> Continua
      |
    Minimizza finestra Kivy (SW_MINIMIZE)
      |
    Lancia subprocess Python con main_designer.py
      |
    Avvia background thread per monitorare subprocess

### 1.2 Fase di Inizializzazione (subprocess)

    [main_designer.py avviato]
      |
    Crea cartella progetto: output_folder/session_name/
      |
    Crea cartella screenshots: output_folder/session_name/screenshots/
      |
    Inizializza database SQLite: session_name.db
      |
    Crea DesignerSession nel DB
      |
    Rileva monitor (mss) e coordinate
      |
    Crea Mini UI (tkinter overlay)
      |
    Cattura screenshot iniziale nel buffer
      |
    Avvia ActionCapture (global mouse/keyboard hooks)
      |
    Pronto per registrazione

### 1.3 Ciclo di Registrazione (Event Loop)
Quando esegui un'azione (click, tipo testo, scroll):

    ===== USER PERFORMS ACTION =====
      (SINGLE_CLICK, DOUBLE_CLICK, RIGHT_CLICK, INPUT,
       SCROLL, DRAG_AND_DROP)
    =================================
      |
    [ActionCapture global listener catches event]
      |
    [Mini UI: REC -> RED]  (Saving in progress)
      |
    [_on_action_captured fired]
      - Incrementa step counter
      - Estrae buffer screenshot
      - Genera bbox intelligente (per azioni che hanno coordinates)
      - Salva PNG file in screenshots folder
      - Salva DesignerStep nel DB
      - REC rimane ROSSO
      |
    [ActionCapture in background thread]
      - Aspetta stabilizzazione schermo (< 2% pixel change, max 3s)
      - Aspetta un tempo minimo di 0.2 sec
      - Cattura nuovo screenshot nel buffer
      - Notifica "buffer pronto"
      |
    [_on_buffer_ready fired]
      - [Mini UI: REC -> GREEN]  (Pronto per prossima azione)

#### SINGLE_CLICK
- **Cosa cattura**: Coordinate (x, y) del click
- **BBox generato**: Si (automatico da edge detection)
- **OCR**: Si (estrae testo dal bbox, utile per identificare testo bottoni)
- **ResNet**: Si (estra info di deep learning dell BBox)
- **Quando**: Click singolo su un elemento

#### DOUBLE_CLICK
- **Cosa cattura**: Coordinate (x, y), numero di click
- **Riconoscimento**: Due click nello stesso punto entro 0.4s
- **BBox generato**: Si
- **OCR**: Si
- **ResNet**: Si
- **Quando**: Due click veloci per selezionare testo o aprire elementi

#### RIGHT_CLICK
- **Cosa cattura**: Coordinate (x, y) del right-click
- **BBox generato**: Si
- **OCR**: Si
- **ResNet**: Si (estra info di deep learning dell BBox)
- **Menu contesto**: Non catturato (e un'azione successiva)
- **Quando**: Click destro per menu contestuali

#### INPUT (Text)
- **Cosa cattura**: Testo digitato ("ciao", "user@example.com", ecc.)
- **BBox generato**: No (e testo in un campo, non un elemento specifico)
- **Attivazione**: Inizia al primo carattere digitato
- **Terminazione**: 
  - **ENTER** = Newline (il testo continua nella riga dopo)
  - **F9** = Fine INPUT (salva l'azione e processa)
- **Quando**: Digiti in un campo di testo, form, search bar

#### SCROLL
- **Cosa cattura**: Direzione (dx, dy), posizione (x, y)
- **BBox generato**: No (e un'azione globale)
- **OCR**: No
- **ResNet**: No
- **Quando**: Ruoti la rotella del mouse per scorrere

#### DRAG_AND_DROP
- **Cosa cattura**: 
  - Posizione inizio (x1, y1)
  - Posizione fine (x2, y2)
  - Distanza trascinamento
- **BBox generato**: Si per entrambe le posizioni
- **OCR**: Si per entrambe
- **ResNet**: Si per entrambe
- **Quando**: Trascini un elemento da una posizione a un'altra
- **Nota**: Cattura 2 screenshot (prima e dopo il drag) - Per verificare che elemento e arrivato a destinazione (vedi 7.2)

### 1.4 Fine Sessione

    [User presses ESC]
      |
    Arresta ActionCapture (global hooks removed)
      |
    Chiude Mini UI
      |
    Chiude database
      |
    Scrive session_done.json con metadata
      |
    Subprocess termina
      |
    [Background thread in Kivy:]
      - Legge session_done.json
      - Ripristina finestra (SW_SHOW)
      - Naviga a Summary Screen
      |
    [Summary Screen carica dati]
      - Legge DB
      - Lista tutti gli step sulla sinistra
      - Seleziona automaticamente primo step
      - Mostra screenshot annotata con overlays

---





## 2. Struttura Folder Output

    C:/Users/alenzi/Desktop/Test/
    +-- 5/                                 (session_name: "5")
        +-- 5.db                           (SQLite database)
        +-- 5_debug.log                    (Debug log del subprocess)
        +-- session_done.json              (Segnale fine sessione)
        +-- screenshots/                   (Cartella screenshot)
            +-- step_001.png               (Buffer screenshot prima di click 1)
            +-- step_002.png               (Buffer screenshot prima di click 2)
            +-- step_003.png
            +-- ...

### Cosa rappresenta ogni PNG?
- **step_N.png** = screenshot dello stato PRECEDENTE all'azione N
- Cioe: se fai click al step 1, step_001.png e lo schermo prima del click
- Dopo il click, il sistema stabilizza la pagina e cattura step_002.png nel buffer
- Il bbox e le coordinate si riferiscono a step_001.png (l'immagine dell'azione)

---

## 3. Struttura Database

### 3.1 Tabelle

#### `designer_session`
```sql
id              INTEGER PRIMARY KEY
name            STRING      -- Nome sessione (es: "5")
created_at      DATETIME    -- Timestamp creazione
```

#### `designer_step`
```sql
id              INTEGER PRIMARY KEY
session_id      INTEGER FK -> designer_session.id
step_number     INTEGER     -- 1, 2, 3, ... (ordine cronologico)
action_type     STRING      -- "SINGLE_CLICK", "DOUBLE_CLICK", "RIGHT_CLICK", "SCROLL", "INPUT", "DRAG_AND_DROP"

-- Screenshot e posizionamento (inizio azione)
screenshot      BLOB        -- PNG bytes (immagine compressa)
screenshot_path STRING      -- Percorso file: screenshots/step_001.png
coordinates     STRING      -- JSON: {"x": 100, "y": 200}  (click/start point)

-- Bounding box (elemento cliccato) + AI
bbox            STRING      -- JSON: {"x": 50, "y": 150, "w": 100, "h": 50}
ocr_text        STRING      -- Testo estratto dalla bbox (OCR - placeholder)
features        BLOB        -- ResNet18 features (512-dim - placeholder)

-- Azioni specifiche
input_text      STRING      -- Testo digitato (per INPUT)
scroll_dx       INTEGER     -- Scroll orizzontale (per SCROLL)
scroll_dy       INTEGER     -- Scroll verticale (per SCROLL)

-- Per DRAG_AND_DROP (end position)
drag_end_coordinates  STRING  -- JSON: {"x": 200, "y": 300}  (end point)
drag_end_bbox         STRING  -- JSON bbox at destination
drag_end_ocr_text     STRING  -- OCR text at destination
drag_end_features     BLOB    -- ResNet18 features at destination

-- Per RIGHT_CLICK (context menu)
right_click_menu  STRING    -- TODO: Menu items captured (future)

created_at      DATETIME
```




### 3.2 Esempio Query
```python
# Caricare tutti gli step di una sessione
steps = db.get_steps(session_id=1)

for step in steps:
    print(f"Step {step.step_number}: {step.action_type}")
    print(f"  Click at: {step.coordinates}")
    print(f"  BBox: {step.bbox}")
    print(f"  OCR: {step.ocr_text}")
    
    # Decodificare immagine
    img = cv2.imdecode(np.frombuffer(step.screenshot, dtype=np.uint8), cv2.IMREAD_COLOR)
```

---

## 4. User Abilities - Comandi Registrabili

### 4.1 Tasti Speciali (User Controls)

#### **ENTER - Newline (Continua testo)**
```
[Stai digitando testo in un textarea]
  |
Premi ENTER
  |
Testo a a capo senza scrivere \n
  |
INPUT rimane attivo, continui a digitare
```

#### **F9 - Fine INPUT (Salva azione)**
```
[Hai digitato tutto il testo che serviva]
  |
Premi F9
  |
Salva INPUT action nel DB con tutto il testo (incluse newline)
  |
Attende stabilizzazione
  |
Cattura nuovo buffer screenshot
  |
REC diventa GREEN
```

#### **CTRL - Screenshot Manuale (Override Buffer)**
```
Caso: Una pagina sta caricando (es: 5 secondi)
      timeout stabilizzazione = 3 secondi

[Azione iniziata -> timeout raggiunto]
  |
Premi CTRL (sinistra o destra)
  |
Cattura screenshot immediato
  |
Sostituisce il buffer
  |
REC diventa GREEN subito (senza aspettare stabilizzazione)
```

#### **ESC - Termina Sessione**
```
[Premi ESC]
  |
Arresta tutti i listener
  |
Chiude database
  |
Scrive session_done.json
  |
Subprocess termina
  |
Kivy ripristina finestra e mostra Summary
```

---

### 4.2 Indicatori Mini UI

```

| *  REC  #5  [F9] [CTRL] [X] |  <- Mini UI (tkinter, 180x28px)


* = Dot (rosso quando saving, verde quando pronto)
REC = Label (Text)
#5 = Step counter
[F9] = Pulsante per terminare input (visibile solo durante INPUT)
[CTRL] = Tooltip
[X] = Pulsante per ESC (visibile sempre)
```

**Significato colori:**
- (RED) **ROSSO**: Sistema sta elaborando azione
  - Salva screenshot/step nel DB
  - Aspetta stabilizzazione
  - Cattura nuovo buffer screenshot
  - Non fare azioni mentre e rosso!

- (GREEN) **VERDE**: Pronto per prossima azione
  - Buffer screenshot caricato
  - Puoi cliccare/digitare quando vuoi

---

## 5. Algoritmi e Perche

### 5.1 Intelligent BBox Generation (Deteccion Elemento)

**Problema:** Come sapere quale elemento e stato cliccato?

**Soluzione:** Edge Detection + Contour Analysis



```python
def generate_smart_bbox(screenshot, click_x, click_y):
    # PASSO 1: Canny Edge Detection
    gray = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 100, 200)  # Rileva bordi
    
    # PASSO 2: Dilate (connetti bordi vicini)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    dilated = cv2.dilate(edges, kernel, iterations=2)
    
    # PASSO 3: Find Contours (lista di forme trovate)
    contours = cv2.findContours(dilated, ...)
    
    # PASSO 4: Seleziona il bbox piu intelligente
    # - Trova TUTTI i contours che contengono il click point
    # - Prendi il MAS PICCOLO (il piu "tight" intorno al click)
    # - Fallback: Se nessuno contiene il click, crea un quadrato 100x100
    #   centrato sul click
```

**Perche questo algoritmo?**
1. [OK] Edge detection funziona con qualsiasi UI (web, desktop, mobile)
2. [OK] Non dipende da colori o fonts
3. [OK] Selezione "smallest containing" riduce falsi positivi
4. [OK] Fallback garantisce sempre un bbox valido

**Esempio:**
```
Clicchi un pulsante "Login"
  |
Edge Detection trova il bordo del bottone
  |
Dilate connette i bordi
  |
Contour Analysis sa che il bottone e grande 150x50px
  |
BBox salvato: {"x": 200, "y": 100, "w": 150, "h": 50}
  |
Nella summary:
  - Rettangolo blu mostra il bottone
  - OCR (futura): "LOGIN" (legge il testo dal bbox)
  - Executor usa sia BBox che OCR per trovare elementi simili
```

**OCR + BBox + ResNet = Matching Robusto (Parallelo)**
```
Executor cerca il bottone in una nuova versione dell'app:
Calcola matching parallelo su 3 layer contemporaneamente:

 LAYER 1: BBox 
| Calcola similarity tra bbox salvato  |
| e tutte le forme nella nuova schema  |
| Score: 0.0-1.0                       |

         |
 LAYER 2: OCR 
| Cerca testo "LOGIN" nella schema     |
| Calcola text similarity (fuzzy match)|
| Score: 0.0-1.0                       |

         |
 LAYER 3: ResNet 
| Calcola image similarity tra feature |
| vector salvato e aree nella schema   |
| Score: 0.0-1.0                       |

         |
 VOTING FINALE 
| score_finale = (bbox_score x 0.4) +  |
|               (ocr_score x 0.3) +    |
|               (resnet_score x 0.3)   |
|                                      |
| Se score > 0.75 -> Clicca             |
| Se score < 0.50 -> Errore             |
| 0.50-0.75 -> Confidence bassa, alert  |

```

---

### 5.2 Screen Stability Detection (Aspetta Caricamento)

**Problema:** Click su un link che carica una pagina. Quando catturare lo screenshot?

**Soluzione:** Pixel Diff < 2%

```python
def wait_for_screen_stability(timeout_ms=3000, min_stable_ms=200):
    start_time = time.time()
    stable_time = None
    prev_screenshot = None
    
    while time.elapsed < timeout_ms:
        current = capture_screen()
        
        if prev_screenshot is not None:
            # Calcola differenza pixel
            diff = cv2.absdiff(prev_screenshot, current)
            changed_pixels = np.count_nonzero(diff) / diff.size
            
            if changed_pixels < 0.02:  # < 2% cambiamento
                if stable_time is None:
                    stable_time = time.time()
                # Aspetta tempo minimo (0.2s) dopo stabilizzazione
                if time.time() - stable_time >= min_stable_ms / 1000:
                    return current  # [OK] Schermo stabile!
            else:
                stable_time = None  # Reset se ancora cambia
        
        prev_screenshot = current
        time.sleep(100ms)
    
    return current  # Timeout: ritorna ultimo screenshot
```

**Perche 2%?**
- **> 2%**: Pagina probabilmente ancora caricando (testo che appare, animazioni)
- **< 2%**: Schermo stabilizzato (solo mouse cursor cambia, che non conta)

**Tempo minimo 0.2 secondi:**
- Evita di catturare screenshot in momenti di micro-flicker
- Garantisce che UI sia completamente ferma
- Utile per transizioni CSS e animazioni rapide

**Timeout 3 secondi:**
- Covers 95% dei casi reali
- Se supera: Premi **CTRL** per override manuale

**Esempio Timeline:**
```
t=0ms    Click su link
t=100ms  Pagina inizia a caricare (50% pixel change)
t=300ms  Pagina continua (30% pixel change)
t=1000ms Pagina quasi carica (5% pixel change)
t=1200ms Pagina completamente carica (1% pixel change) [OK]
         -> Screenshot catturato qui
t=3000ms Timeout (non raggiunto in questo caso)
```

---

### 5.3 Buffer Screenshot System (Pre-Cattura)

**Problema:** Se catturi lo screenshot DOPO il click, l'azione e gia visibile. Vogliamo lo schermo PRIMA.

**Soluzione:** Buffer

```
Startup
  |
Cattura screenshot -> BUFFER

User clicks
  |
Action usa BUFFER screenshot (stato PRIMA del click) [OK]
  |
Aspetta stabilizzazione
  |
Cattura nuovo screenshot -> BUFFER (stato DOPO il click)
  |
Pronto per prossima azione

[Ciclo ripete]
```

**Vantaggi:**
- Immagine mostra lo stato PRIMA dell'azione (e quello che l'Executor dovra matching)
- Bbox e coordinates si riferiscono all'elemento cliccato, visibile nell'immagine
- Flusso senza ritardi (non aspetti after il click)

---

### 5.4 Coordinate Conversion (Multi-Monitor)

**Problema:** Se hai 2 monitor:
- Monitor 1: 1920x1080, position (0, 0)
- Monitor 2: 1920x1080, position (1920, 0) oppure (0, -1080)

Quando clicchi su Monitor 2, il click assoluto e (2400, 300), ma la screenshot e relativa a Monitor 2.

**Soluzione:**
```python
# Click e in coordinate assolute (globali)
click_x, click_y = 2400, 300

# Screenshot e relativa a monitor
monitor_info = {'left': 1920, 'top': 0, 'width': 1920, 'height': 1080}

# Converti a coordinate relative al monitor
x_rel = click_x - monitor_info['left']  # 2400 - 1920 = 480
y_rel = click_y - monitor_info['top']   # 300 - 0 = 300

# Ora bbox/circle usano (480, 300) che e dentro la screenshot
```

---

### 5.5 OCR + ResNet Features (AI Matching)

**Problema:** Click cambia posizione o bottone viene tradotto. Come trovare lo stesso elemento in una versione diversa dell'app?

**Soluzione:** Combinare BBox + OCR + ResNet

```
Elemento identificato da 3 layer:

LAYER 1: BBox (Edge Detection)
 Pro: Preciso, veloce
 Contro: Fragile se elemento muove di 10px

LAYER 2: OCR (Optical Character Recognition)
 Pro: Indipendente da layout, valido anche se tradotto
 Contro: Non funziona su icone/immagini senza testo
 Quando usare: Bottoni con testo, label, placeholder

LAYER 3: ResNet18 Features (Deep Learning)
 Pro: Robusto a trasformazioni, funziona su immagini/icone
 Contro: Richiede GPU, piu lento
 Quando usare: Bottoni con icone, immagini, elementi grafici
```

**Flusso di Matching nell'Executor (Parallelo - Voting):**
```
Cerco elemento in schermata nuova:

 In parallelo, calcola 3 score contemporaneamente 
|                                                   |
| LAYER 1: BBox Matching                            |
| - Per ogni forma nella schermata, calcola IoU     |
|   (Intersection over Union) con bbox salvato      |
| - Prendi forma con highest BBox similarity score  |
|                                                   |
| LAYER 2: OCR Text Matching                        |
| - Usa OCR per estrarre testo dalla schermata      |
| - Cerca "LOGIN" con fuzzy string matching         |
| - Calcola similarity su testo trovato (0-1)       |
|                                                   |
| LAYER 3: ResNet Features Matching                 |
| - Per ogni area della schermata, estrai features  |
| - Calcola cosine similarity con features salvato  |
| - Prendi area con highest ResNet score            |
|                                                   |

         |
    Voting finale:
    score = (layer1 x 0.4) + (layer2 x 0.3) + (layer3 x 0.3)
         |
    Se score > 0.75 -> Clicca sull'elemento [OK]
    Se 0.50-0.75 -> Low confidence, warning
    Se score < 0.50 -> Elemento non trovato, errore
```

---

## 6. Flusso Completo: Esempio Pratico

### 6.1 Scenario: Accesso a Google

**Sessione "google_login"** - Dimostrazione del flusso end-to-end con 3 step:

**Step 1: SINGLE_CLICK** sulla barra di ricerca
- [REC (RED)] Buffer screenshot catturato PRIMA del click
- BBox generato intorno alla search bar
- OCR: "Google Search"
- Aspetta stabilizzazione (< 2% pixel change) + 0.2sec
- [REC (GREEN)] Nuovo screenshot in buffer

**Step 2: INPUT** digitazione testo "hello world"
- [REC (RED)] INPUT attivo (testo accumulato)
- Premi F9 per terminare (ENTER = newline, non salva)
- OCR: n/a (e testo, non elemento)
- [REC (GREEN)] Pronto

**Step 3: SINGLE_CLICK** bottone "Cerca"
- [REC (RED)] Azione invio form
- Aspetta stabilizzazione: pagina carica (2.2 secondi totali)
- BBox, OCR, ResNet estratti
- [REC (GREEN)] Pronto

**Summary Screen:**
- Left panel: 3 step items con numero e action badge
- Right panel: Step 1 selezionato di default
  - Screenshot con rettangolo blu attorno a search bar
  - Metadata:
    - OCR: "Google Search"
    - ResNet: 512-dim vector (placeholder)

**Struttura cartella creata:**
```
C:/Projects/google_login/
   google_login.db
   google_login_debug.log
   session_done.json
   screenshots/
       step_001.png (search bar visible)
       step_002.png (text "hello world" visible)
       step_003.png (Google results page)
```

---

## 7. Prossime Fasi (Implementation Roadmap)

### 7.1 RIGHT_CLICK Support
```python
# In action_capture.py:
def _on_mouse_click(self, x, y, button, pressed):
    if button == mouse.Button.right:
        # Processa RIGHT_CLICK come SINGLE_CLICK
        # Genera bbox, OCR, ResNet
        # Note: Non cattura context menu (e azione successiva)
```

### 7.2 DRAG_AND_DROP Support
```python
# In action_capture.py:
def _on_mouse_move(self, x, y):
    if mouse_pressed:
        # Traccia movimento
        # Al release:
        #   - Cattura screenshot PRIMA del drag (buffer)
        #   - Salva posizione inizio (x1, y1)
        #   - Genera bbox inizio + OCR + ResNet
        #   - Attende stabilizzazione
        #   - Cattura screenshot DOPO del drag
        #   - Salva posizione fine (x2, y2)
        #   - Genera bbox fine + OCR + ResNet
        
        # Perche 2 screenshot?
        # - Executor deve verificare che elemento e arrivato a destinazione
        # - "Prima" mostra elemento nel punto di origine
        # - "Dopo" mostra elemento nel punto di destinazione
        # - Utile per drag in canvas, timeline, sortable lists
```

### 7.3 OCR Text Extraction
```python
# In main_designer.py:
def _extract_ocr(self, bbox_image):
    """Estrae testo dal bbox usando OCR."""
    try:
        import pytesseract
        # Alternative: easyocr, paddle-ocr
        text = pytesseract.image_to_string(bbox_image)
        return text.strip() if text else ""
    except Exception as e:
        print(f"OCR error: {e}")
        return ""

# In _on_action_captured:
if action_type in ('SINGLE_CLICK', 'DOUBLE_CLICK', 'RIGHT_CLICK'):
    ocr_text = self._extract_ocr(bbox_image)
    step.ocr_text = ocr_text
```

### 7.4 ResNet18 Feature Extraction
```python
# In main_designer.py:
def _extract_features(self, bbox_image):
    """Estrae 512-dim feature vector da bbox usando ResNet18."""
    try:
        import torch
        import torchvision.models as models
        from torchvision import transforms
        
        # Load ResNet18 (pretrained)
        model = models.resnet18(pretrained=True)
        model.eval()
        
        # Prepara immagine
        transform = transforms.Compose([
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406],
                               std=[0.229, 0.224, 0.225])
        ])
        img_tensor = transform(Image.fromarray(bbox_image)).unsqueeze(0)
        
        # Estrai features dall'ultimo layer
        with torch.no_grad():
            features = model(img_tensor)  # 512-dim
        
        return features.cpu().numpy().tobytes()
    except Exception as e:
        print(f"ResNet error: {e}")
        return None

# In _on_action_captured:
if action_type in ('SINGLE_CLICK', 'DOUBLE_CLICK', 'RIGHT_CLICK'):
    features = self._extract_features(bbox_image)
    step.features = features
```

### 7.5 Verifica Cartella Duplicata
```python
# In designer_create.py start():
project_folder = os.path.join(output_folder, name)
if os.path.exists(project_folder):
    self._error_msg = f"Sessione '{name}' gia esiste in questa cartella"
    return
```

### 7.6 ENTER = Newline in INPUT
```python
# In action_capture.py _on_key_press():
if key == keyboard.Key.enter:
    # ENTER non termina INPUT
    self.input_text += '\n'  # Newline
    # INPUT rimane attivo
    return

if key == keyboard.Key.f9:
    # F9 termina INPUT
    self._finalize_input_action()
```

### 7.7 Executor (Replay) - Matching Parallelo
```
Carica sessione dal Summary
  |
Per ogni step:
  
  1. Se SINGLE_CLICK/DOUBLE_CLICK/RIGHT_CLICK:
      Matching Parallelo (3 layer) 
     |                                |
     | LAYER 1: BBox Matching         |
     | - Estrai tutte le forme della  |
     |   schermata attuale            |
     | - Calcola IoU con bbox salvato |
     |                                |
     | LAYER 2: OCR Text Matching     |
     | - Estrai OCR da schermata      |
     | - Cerca testo salvato ("LOGIN")|
     | - Fuzzy matching per tolleranza|
     |                                |
     | LAYER 3: ResNet Matching       |
     | - Estrai features da aree      |
     | - Cosine similarity con saved  |
     |   feature vector               |
     |                                |
     | VOTING:                        |
     | score = (layer1x0.4) +         |
     |         (layer2x0.3) +         |
     |         (layer3x0.3)           |
     |                                |
     | Se score > 0.75 -> Clicca [OK]    |
     | Se 0.50-0.75 -> Warning(WARNING)       |
     | Se < 0.50 -> Errore (ERROR)          |
     
  
  2. Se INPUT:
     - Clicca campo di testo (con matching parallelo)
     - Digita testo (incluse newline)
  
  3. Se SCROLL:
     - Esegui scroll (posizione globale, no matching)
  
  4. Se DRAG_AND_DROP:
     - Matching parallelo per elemento inizio
     - Trascina verso destinazione
     - Matching parallelo per elemento fine
     - Verifica concordanza tra bbox/ocr prima e dopo
  
  5. Se RIGHT_CLICK:
     - Matching parallelo
     - Clicca destro
     - Aspetta context menu (manual interaction)
  |
  Verifica risultato (screenshot comparison con step successivo)
```

---

## 8. Troubleshooting

### REC rimane ROSSO troppo a lungo
**Causa**: Pagina caricando lentamente (> 3s)
**Soluzione**: Premi **CTRL** per catturare screenshot manuale

### BBox non corretta
**Causa**: Elemento ha bordi sfumati (gradients) o contours complessi
**Soluzione**: 
- Edge detection potrebbe non catturare perfettamente
- Fallback quadrato 100x100 intorno al click e attivato
- OCR layer completa il matching

### Screenshot sbagliato per uno step
**Causa**: Buffer non allineato
**Soluzione**: Premi **CTRL** prima di fare l'azione successiva per "riallineare"

### Finestra non ripristina dopo ESC
**Causa**: session_done.json non scritto
**Soluzione**: 
- Controlla che session_done.json esista nella cartella progetto
- Guarda debug log (session_name_debug.log) per errori

### DRAG_AND_DROP non catturato correttamente
**Causa**: Movimento troppo veloce, listener perde mousemove events
**Soluzione**:
- Esegui drag piu lentamente
- Se fallisce, usa due azioni separate: SINGLE_CLICK inizio + SINGLE_CLICK fine

### OCR ritorna testo vuoto
**Causa**: Immagine bbox e troppo piccola o elementi grafici senza testo
**Soluzione**: 
- ResNet features completano il matching
- Prova ad aumentare bbox (minimo 40x20px consigliato)

### ResNet features non estratti
**Causa**: GPU non disponibile o librerie non installate
**Soluzione**:
- Controlla che torchvision sia installato
- Il sistema funziona anche senza ResNet (fallback a BBox+OCR)

---

**Fine Documentazione Designer** 
