# UI-Validator Implementation Plan

**Date:** 2026-04-22  
**Status:** Planning Phase  
**Approach:** Executor-First Strategy

---

## 📊 Project Overview

UI-Validator è una versione **semplificata e intelligente** di miao che risolve due problemi:
**FOCUS: Linux + Windows (non Mac per ora)**

1. **Designer troppo lento** → Cattura automatica delle azioni (no manual step creation)
2. **Executor impreciso** → Matching intelligente che trova elementi spostati

---

## 🎯 Architecture

### Designer Flow (Smart Screenshot Reuse)

**Flow ottimizzato con screenshot unico per azione:**

```
User clicca "Create Designer"
    ↓
Finestra si minimizza
    ↓
Mini UI appare (REC rosso = loading)
    ↓
[ATTENDI STABILIZZAZIONE INIZIALE]
    ↓
[SCREENSHOT INIZIALE] (stato app stabile, pronto)
rec diventa verde = puoi procedere
    ↓
AZIONE 1 (es: INPUT testo):
  rec torna rosso = salvataggio
  - Digita testo
  - FINE INPUT when: F9 | ENTER | CLICK su elemento
    ↓
[ATTENDI STABILIZZAZIONE]
    ↓
[SCREENSHOT POST-AZIONE-1 / PRE-AZIONE-2] 
  - Cattura: tipo azione, coordinate, bbox, ocr, resnet
  - Questo screenshot = SUCCESS PROOF per azione 1
    ↓
rec ridiventa verde
    ↓
AZIONE 2 (es: CLICK):
  (Se veniva da INPUT + CLICK, il CLICK è azione 2 e usa lo screenshot di sopra come PRE)
    ↓
[ATTENDI STABILIZZAZIONE]
    ↓
[SCREENSHOT POST-AZIONE-2 / PRE-AZIONE-3]
    ↓
[...continua per ogni azione...]
    ↓
ESC → End Designer → Salva tutti gli step → Summary Screen
```

**Vantaggi:**
- ✅ 50% meno screenshot (efficienza I/O)
- ✅ Stato sempre stabile quando catturato
- ✅ Continuità tra azioni

**Keyboard Shortcuts:**
- `CTRL` → Ricattura screenshot iniziale (se need durante azione)
- `F9` → Fine INPUT (termina digitazione, cattura screenshot POST)
- `ENTER` → Fine INPUT (a capo, termina input, cattura screenshot POST)
- **ESC** → **SOLA FUNZIONE: Fine Designer/Executor** → Salva tutto → Summary Screen
  (Se premi ESC durante INPUT, termina INPUT e Designer completamente)

### Executor Flow
```
User clicca "Create Execution" → Immette path designer + nome
    ↓
Clicca "Avvia Esecuzione"
    ↓
Finestra si minimizza
    ↓
Mini UI appare in basso a sinistra (EXE - ESC STOP)
    ↓
Start recording schermo ffmpeg
    ↓
Per ogni step nel designer:
  1. Legge screenshot di riferimento + bbox dal designer.db
  2. Matching intelligente (3-Stage):
     - **Stage 1:** Match sulla bbox originale (Voting: Template + OCR + ResNet)
     - **Stage 2:** Se fallisce, ESPANDE bbox e cerca nei dintorni
     - **Stage 3:** Se fallisce, full-screen search
  3. Esegue azione sulla posizione trovata
  4. WAIT FOR SCREEN STABILITY:
     - Se pagina ha animazioni/transizioni, aspetta che finiscano
     - Pixel diff < 2% tra 2 screenshot consecutivi (100ms apart)
     - Timeout max 3s
  5. Screenshot post-azione (riusato come PRE per step successivo)
  6. Salva risultato (success/fail/match_score)
    ↓
Stop recording schermo ffmpeg
    ↓
ESC → STOP Execution (salva execution state) → Summary Screen
    (gli step non eseguiti = status STOPPED)
    
oppure
    
Fine di tutti gli step → Summary Screen (tutti gli step completati)
```

---

## 🏗️ Folder Structure

```
src/app/
├── designer_pages/
│   ├── create_screen/         # Designer creation UI
│   │   ├── designer_create.py
│   │   └── designer_create.kv
│   ├── open_screen/           # Designer open UI
│   │   ├── designer_open.py
│   │   └── designer_open.kv
│   └── summary_screen/        # Designer summary/review
│       ├── designer_summary.py
│       └── designer_summary.kv
│
├── executor_pages/
│   ├── create_screen/         # Executor creation UI
│   │   ├── executor_create.py
│   │   └── executor_create.kv
│   ├── open_screen/           # Executor open UI
│   │   ├── executor_open.py
│   │   └── executor_open.kv
│   └── summary_screen/        # Executor summary/results
│       ├── executor_summary.py
│       └── executor_summary.kv
│
├── core/                      # Core engine
│   ├── designer/
│   │   ├── action_capture.py  # Cattura automatica azioni
│   │   ├── screenshot_handler.py
│   │   └── bbox_generator.py  # BBox intelligente
│   │
│   ├── executor/
│   │   ├── matcher.py         # Matching algorithm (Stage 1-3)
│   │   ├── bbox_expander.py   # Espansione intelligente bbox
│   │   ├── action_executor.py # Esecuzione azioni
│   │   └── feature_matcher.py # ResNet feature matching
│   │
│   ├── database/
│   │   ├── designer_db.py     # Designer DB schema
│   │   ├── executor_db.py     # Executor DB schema
│   │   └── models.py          # SQLAlchemy models
│   │
│   └── utils/
│       ├── mini_ui.py         # Mini interfaccia (REC, EXE, F9)
│       ├── window_manager.py  # Minimizza/Massimizza
│       └── hooks.py           # Mouse/tastiera hooks
│
└── assets/                    # Icons, images
```

---

## 🔧 Core Components Detail

### 1. Designer Action Capture System

**File:** `src/app/core/designer/action_capture.py`

```python
class ActionCapture:
    def __init__(self):
        self.actions = []
        self.input_active = False
        self.hooks = MouseKeyboardHooks()
    
    def start_recording(self):
        """Attiva mouse + tastiera hooks"""
        self.hooks.on_mouse_click = self.handle_click
        self.hooks.on_mouse_double_click = self.handle_double_click
        self.hooks.on_mouse_drag = self.handle_drag
        self.hooks.on_keyboard_input = self.handle_input
        self.hooks.on_key_press = self.handle_key
        self.hooks.start()
    
    def handle_key(self, key_code):
        """Rileva F9, ENTER per terminare INPUT"""
        if key_code in [keyboard.Key.f9, keyboard.Key.enter]:
            if self.input_active:
                self.finalize_input_action()
    
    def handle_click(self, x, y):
        """
        Single click:
        - Se INPUT attivo: termina INPUT e salva, poi cattura CLICK come azione nuova
        - Altrimenti: cattura CLICK normalmente
        """
        if self.input_active:
            # Termina INPUT precedente
            self.finalize_input_action()
        
        # Cattura CLICK usando screenshot stabile
        screenshot = self.wait_for_stability()
        bbox = self.generate_smart_bbox(screenshot, x, y)
        
        action = {
            'type': 'SINGLE_CLICK',
            'coordinates': (x, y),
            'bbox': bbox,
            'screenshot': screenshot,
            'ocr_text': self.ocr_engine.extract(screenshot[bbox]),
            'features': self.feature_extractor.extract(screenshot[bbox]),
            'timestamp': time.time()
        }
        self.save_action(action)
    
    def handle_input(self, char):
        """Cattura digitazione testo"""
        self.input_active = True
        self.input_text += char
    
    def finalize_input_action(self):
        """Salva INPUT action con screenshot stabile"""
        if not self.input_active:
            return
        
        screenshot = self.wait_for_stability()
        # Cerca bbox dell'input field attivo
        bbox = self.find_active_input_bbox(screenshot)
        
        action = {
            'type': 'INPUT',
            'input_text': self.input_text,
            'bbox': bbox,
            'screenshot': screenshot,
            'ocr_text': self.input_text,
            'features': self.feature_extractor.extract(screenshot[bbox]),
            'timestamp': time.time()
        }
        self.save_action(action)
        self.input_active = False
        self.input_text = ""
    
    def handle_drag(self, x1, y1, x2, y2):
        """
        Drag and drop cattura 2 screenshot:
        1. START: source element bbox + ocr + resnet
        2. END: destination element bbox + ocr + resnet
        """
        # Screenshot 1: source
        screenshot_start = self.wait_for_stability()
        bbox_start = self.generate_smart_bbox(screenshot_start, x1, y1)
        
        # Esegui drag (visuale, non salviamo)
        # ... drag motion ...
        
        # Screenshot 2: destination
        screenshot_end = self.wait_for_stability()
        bbox_end = self.generate_smart_bbox(screenshot_end, x2, y2)
        
        action = {
            'type': 'DRAG',
            'coordinates': (x1, y1),
            'bbox': bbox_start,
            'screenshot': screenshot_start,
            'ocr_text': self.ocr_engine.extract(screenshot_start[bbox_start]),
            'features': self.feature_extractor.extract(screenshot_start[bbox_start]),
            'drag_end_coordinates': (x2, y2),
            'drag_end_bbox': bbox_end,
            'drag_end_ocr_text': self.ocr_engine.extract(screenshot_end[bbox_end]),
            'drag_end_features': self.feature_extractor.extract(screenshot_end[bbox_end]),
            'timestamp': time.time()
        }
        self.save_action(action)
    
    def wait_for_stability(self, timeout_ms=3000):
        """Aspetta che schermo si stabilizzi, poi cattura"""
        return self.screenshot_handler.wait_for_screen_stability(timeout_ms)
    
    def generate_smart_bbox(self, screenshot, x, y):
        """Genera BBox intelligente attorno all'elemento"""
        # Usa edge detection + contour finding
        return bbox
```

**Key Libraries:**
- `pynput` - Mouse/tastiera hooks
- `opencv` - Smart bbox generation (edge detection, contours)

---

### 2. Executor Matching Algorithm

**File:** `src/app/core/executor/matcher.py`

```python
class IntelligentMatcher:
    def __init__(self, designer_db_path):
        self.designer_db = DesignerDatabase(designer_db_path)
        self.feature_matcher = FeatureMatcher()  # ResNet18
    
    def find_element(self, step_id):
        """
        Algoritmo a 3-stage per trovare elemento
        anche se finestra è spostata
        Ogni stage combina: Template + OCR + ResNet
        """
        step = self.designer_db.get_step(step_id)
        original_bbox = step['bbox']  # Coordinate originali
        screenshot = self.capture_screenshot()
        
        # STAGE 1: Match sulla bbox originale
        match = self.combined_match(screenshot, step, original_bbox)
        if match and match['score'] > 0.85:
            return match
        
        # STAGE 2: Espandi bbox e cerca automaticamente
        expanded_match = self.find_element_expanded(screenshot, step, original_bbox)
        if expanded_match and expanded_match['score'] > 0.85:
            return expanded_match
        
        # STAGE 3: Full screen search (threshold più rilassato)
        fullscreen_match = self.find_element_fullscreen(screenshot, step)
        if fullscreen_match and fullscreen_match['score'] > 0.8:
            return fullscreen_match
        
        # Se tutto fallisce, ritorna errore
        return {'score': 0, 'coordinates': None, 'error': 'Element not found'}
    
    def combined_match(self, screenshot, step, bbox):
        """
        Voting intelligente: almeno 2 su 3 metodi devono concordare
        Non semplice media (evita diluzione dei segnali)
        """
        template_score = self.template_match(screenshot, step['screenshot'], bbox)
        ocr_score = self.ocr_match(screenshot, step['ocr_text'], bbox)
        resnet_score = self.feature_matcher.match(screenshot, step['features'], bbox)
        
        scores = [template_score, ocr_score, resnet_score]
        high_scores = sum(1 for s in scores if s > 0.80)  # Quanti > 0.80?
        
        if high_scores >= 2:  # 2+ su 3 "d'accordo"
            combined_score = max(scores)  # Prendi il migliore
            return {'score': combined_score, 'coordinates': bbox, 'confidence': 'HIGH'}
        
        # Se meno di 2 metodi concordano, score basso
        combined_score = sum(scores) / 3
        return {'score': combined_score, 'coordinates': bbox, 'confidence': 'LOW'}
    
    def find_element_expanded(self, screenshot, reference, original_bbox):
        """
        Espande bbox in zone concentriche
        cerca il match migliore dinamicamente
        """
        x, y, w, h = original_bbox
        expansion_steps = [0, 50, 100, 200, 400]  # pixels
        
        for expansion in expansion_steps:
            expanded = (x-expansion, y-expansion, w+2*expansion, h+2*expansion)
            match = self.template_match(screenshot, reference, expanded)
            if match['score'] > 0.85:
                return match
        
        return None
```

**3-Stage Algorithm (Each Stage combines: Template + OCR + ResNet):**

1. **Stage 1 - Original BBox**
   - Template Matching (OpenCV) sulla bbox originale
   - OCR text matching per verificare
   - ResNet18 feature matching come backup
   - Threshold: 0.85 (pass if any matches)

2. **Stage 2 - Expanded BBox**
   - Espandi bbox in zone concentriche (50px, 100px, 200px, 400px)
   - Template + OCR + ResNet su ogni zona
   - Threshold: 0.85

3. **Stage 3 - Full Screen**
   - Cerca su intero schermo
   - Template + OCR + ResNet18
   - Threshold: 0.8 (più rilassato perché last resort)

**Special Case: DRAG Action**

Per DRAG, il Designer cattura **2 screenshot separati**:

1. **Screenshot 1 (START):** source element
   - bbox, ocr_text, features (ResNet18)
   - catturato quando inizi il drag

2. **Screenshot 2 (END):** destination element  
   - drag_end_bbox, drag_end_ocr_text, drag_end_features (ResNet18)
   - catturato quando finisce il drag

Nell'Executor, il matching per DRAG:
```python
def find_drag_elements(self, step):
    """Trova sia source che destination per drag"""
    
    # Find source element usando screenshot_start
    source = self.find_element(step.screenshot, step.bbox, step.features)
    if not source:
        return {'success': False, 'error': 'source not found'}
    
    # Find destination element usando screenshot_end
    dest = self.find_element(step.screenshot, step.drag_end_bbox, step.drag_end_features)
    if not dest:
        return {'success': False, 'error': 'destination not found'}
    
    return {
        'success': True,
        'source_coordinates': source['coordinates'],
        'destination_coordinates': dest['coordinates'],
        'source_score': source['score'],
        'dest_score': dest['score']
    }
```

---

### 3. Action Executor

**File:** `src/app/core/executor/action_executor.py`

```python
class SmartActionExecutor:
    def execute_step(self, step, found_coordinates):
        """Esegue azione in modo smart"""
        action_type = step['action_type']
        x, y = found_coordinates
        
        if action_type == 'SINGLE_CLICK':
            self.click(x, y)
        
        elif action_type == 'DOUBLE_CLICK':
            self.double_click(x, y)
        
        elif action_type == 'INPUT':
            self.type_text(step['input_text'])
        
        elif action_type == 'DRAG_DROP':
            dest_x, dest_y = step['destination_coordinates']
            self.drag(x, y, dest_x, dest_y)
        
        # Timing intelligente
        time.sleep(step.get('delay_after', 0.5))
        
        # Screenshot post-azione
        return self.capture_screenshot()
```

---

### 4. Mini UI System & Keyboard Handling

**File:** `src/app/core/utils/mini_ui.py`

**Visual Feedback System:**
- REC **rosso** (sfondo) = loading / saving action (non pronto)
- REC **verde** (sfondo) = pronto, puoi fare azioni

```python
from pynput import keyboard
import time
import tkinter as tk

class MiniUI:
    """
    Mini interfaccia in basso a sinistra con color feedback
    
    DESIGNER MODE:
      - ESC → End Designer (salva) → Summary Screen
      - F9 → Fine INPUT
      - ENTER → Fine INPUT
      - Click → Fine INPUT (se stava digitando)
    
    EXECUTOR MODE:
      - ESC → Stop Execution → Summary Screen
    """
    
    def __init__(self, mode='DESIGNER', on_end_callback=None, on_input_end_callback=None):
        self.mode = mode
        self.on_end_callback = on_end_callback
        self.on_input_end_callback = on_input_end_callback
        self.is_ready = False
        
        # Tkinter window
        self.window = tk.Tk()
        screen_height = self.window.winfo_screenheight()
        self.window.geometry(f"150x50+0+{screen_height-50}")
        self.window.attributes('-topmost', True)
        
        # Label con colore dinamico
        self.label = tk.Label(
            self.window,
            text=f"{mode}",
            fg="white",
            bg="red",  # Inizia ROSSO (loading)
            font=("Arial", 12, "bold"),
            width=15
        )
        self.label.pack()
        
        # Global keyboard listener
        self.listener = keyboard.Listener(on_press=self.on_key_press)
        self.listener.start()
    
    def set_ready(self):
        """Cambia colore a VERDE quando pronto"""
        self.is_ready = True
        self.label.config(bg="green")
        self.label.config(text=f"{self.mode} ✓")
    
    def set_saving(self):
        """Torna ROSSO durante il salvataggio"""
        self.is_ready = False
        self.label.config(bg="red")
        self.label.config(text=f"Saving...")
    
    def on_key_press(self, key):
        """Rileva ESC, F9, ENTER"""
        try:
            if key == keyboard.Key.esc:
                # ESC → End (Designer o Executor)
                if self.on_end_callback:
                    self.on_end_callback()
                self.listener.stop()
                self.window.destroy()
            
            elif key == keyboard.Key.f9 or key == keyboard.Key.enter:
                # F9 o ENTER → Fine INPUT
                if self.mode == 'DESIGNER' and self.on_input_end_callback:
                    self.on_input_end_callback()
        
        except AttributeError:
            pass
```

---

### 5. Smart Screenshot Reuse (Unified Flow)

**Concetto chiave:** Uno screenshot serve **3 scopi contemporaneamente**:

```
[AZIONE 1] → [WAIT STABILIZATION] → [SCREENSHOT S1]
                                         ├─ PRE-AZIONE-2 (matching prossimo step)
                                         ├─ SUCCESS PROOF-1 (visual proof dell'azione 1)
                                         └─ Riusato per il prossimo step
                                             ↓
                                        [AZIONE 2] → [SCREENSHOT S2]
                                                         ├─ PRE-AZIONE-3
                                                         ├─ SUCCESS PROOF-2
                                                         └─ Continua...
```

**3 Funzioni dello Screenshot Post-Azione:**
1. **Matching PRE-azione** — Usato come PRE-screenshot per la azione successiva
2. **Success Proof** — Visual evidence che l'azione precedente ha avuto effetto:
   - Click su "Elimina" → elemento sparisce
   - Drag-drop → elemento appare nella nuova posizione
   - Input text → testo visibile nel campo
   - Scroll → contenuto cambia
3. **Efficient Storage** — 1 screenshot per azione anziché 2

**Benefici:**
| Aspetto | Vecchio | Nuovo |
|---------|--------|-------|
| Screenshot/azione | 2 (pre + post) | 1 (riusato) |
| Efficienza I/O | ⚠️ 2x capture | ✅ 50% I/O |
| Stato stabile | Non garantito | ✅ Sempre |
| Storage | 2x volume | 1x volume |
| Success Evidence | ❌ Nessuno | ✅ Visibile |

**Nel Executor:**
- Usa `step.screenshot` per il matching
- Dopo azione, cattura screenshot POST
- Screenshot POST diventa PRE della azione successiva (automaticamente)

---

### 5b. Screen Stability Detection

**Problema:** Se la pagina ha animazioni (fade-in, slide, loading), catturare subito il screenshot non funziona.

**Soluzione:** Aspetta che lo schermo si stabilizzi prima di catturare:

```python
def wait_for_screen_stability(self, timeout_ms=3000, check_interval_ms=100):
    """
    Cattura screenshot ogni 100ms finché non è stabile.
    Stabile = pixel diff < 2% tra due screenshot
    """
    start_time = time.time()
    prev_screenshot = None
    
    while (time.time() - start_time) < (timeout_ms / 1000):
        current = self.capture_screenshot()
        
        if prev_screenshot is not None:
            # Confronta pixel per pixel
            diff = cv2.absdiff(prev_screenshot, current)
            changed_pixels = np.count_nonzero(diff) / diff.size
            
            if changed_pixels < 0.02:  # < 2% cambiamento
                return current  # Screenshot stabile!
        
        prev_screenshot = current
        time.sleep(check_interval_ms / 1000)
    
    # Timeout: ritorna ultimo screenshot
    return current
```

**Usage:**
```python
# Dopo azione
stable_screenshot = self.wait_for_screen_stability()
# Ora `stable_screenshot` è pronto per cattura
```

---

### 6. ResNet18 Feature Extraction

**Basato su miao `uiv/engine/feature_extractor.py`:**

```python
from torchvision import models, transforms
from torchvision.models.resnet import ResNet18_Weights
import torch
import numpy as np
import cv2

@singleton
class FeatureExtractor:
    """ResNet18 512-dim feature vector per image matching."""
    
    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # Load ResNet18 con weights ImageNet pre-trained
        base = models.resnet18(weights=ResNet18_Weights.IMAGENET1K_V1)
        
        # Remove final classification layer → keep 512-d pooled features
        self.model = torch.nn.Sequential(*list(base.children())[:-1])
        self.model.eval().to(self.device)
        
        # Standard ImageNet preprocessing
        self.transform = transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((224, 224)),  # ResNet aspetta 224x224
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225]
            ),
        ])
    
    def extract(self, image: np.ndarray) -> np.ndarray:
        """Extract 512-dim feature vector from BGR image crop."""
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        tensor = self.transform(rgb).unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            features = self.model(tensor)  # Shape: (1, 512, 1, 1)
        
        return features.cpu().numpy().flatten()  # Flatten to (512,)
    
    def encode(self, image: np.ndarray) -> bytes:
        """Extract features and encode as raw float32 bytes for DB storage."""
        return self.extract(image).astype(np.float32).tobytes()
    
    @staticmethod
    def decode(data: bytes) -> np.ndarray:
        """Decode stored feature vector from bytes."""
        return np.frombuffer(data, dtype=np.float32)
```

**Matching con ResNet:**
```python
def cosine_similarity(feat1, feat2) -> float:
    """0-1 score: 1 = identico, 0 = completamente diverso"""
    from scipy.spatial.distance import cosine
    return 1 - cosine(feat1, feat2)

# In matcher.py:
resnet_score = cosine_similarity(stored_features, current_features)
# Threshold: 0.80+ = match buono
```

**DB Storage (come in miao):**
```python
# Salva nel DB
step.features = FeatureExtractor().encode(image_crop)

# Carica dal DB
stored_features = FeatureExtractor.decode(step.features)  # Returns np.ndarray (512,)
current_features = fe.extract(current_crop)  # Returns np.ndarray (512,)
score = cosine_similarity(stored_features, current_features)
```

---

### 7. Database Schema

**Designer DB (designer.db):**
```python
class DesignerStep(Base):
    __tablename__ = 'designer_step'
    
    id = Column(Integer, primary_key=True)
    step_number = Column(Integer)
    action_type = Column(String)  # CLICK, DOUBLE_CLICK, RIGHT_CLICK, INPUT, DRAG, SCROLL
    
    # Coordinate e screenshot (uno solo, riusato)
    screenshot = Column(LargeBinary)  # PNG image (catturato DOPO stabilizzazione)
    coordinates = Column(String)  # JSON: {"x": 100, "y": 200}
    
    # Element matching data (source element)
    bbox = Column(String)  # JSON: {"x": 10, "y": 20, "w": 100, "h": 50}
    ocr_text = Column(String, nullable=True)  # OCR della bbox
    features = Column(LargeBinary, nullable=True)  # ResNet18 512-dim float32 (encoded as bytes)
    
    # Action-specific fields
    input_text = Column(String, nullable=True)  # Per INPUT actions
    press_enter_after = Column(Boolean, default=False)  # INPUT: press Enter dopo
    
    # DRAG specific: 2 bbox + 2 ocr + 2 resnet (source + destination)
    drag_end_coordinates = Column(String, nullable=True)  # JSON: {"x": 300, "y": 400}
    drag_end_bbox = Column(String, nullable=True)  # JSON destination bbox
    drag_end_ocr_text = Column(String, nullable=True)  # OCR della destination
    drag_end_features = Column(LargeBinary, nullable=True)  # ResNet18 destination features
    
    # SCROLL specific
    scroll_dx = Column(Integer, nullable=True)
    scroll_dy = Column(Integer, nullable=True)
    
    timestamp = Column(DateTime)
    stabilization_wait_ms = Column(Integer, default=1500)
```

**Executor DB (execution.db):**
```python
class ExecutionStep(Base):
    __tablename__ = 'execution_step'
    
    id = Column(Integer, primary_key=True)
    step_id = Column(Integer)  # Reference to designer step
    success = Column(Boolean)
    match_score = Column(Float)  # 0-1 (matching confidence)
    found_coordinates = Column(String)  # JSON: where element was found
    timestamp = Column(DateTime)
    
    # Screenshot POST-azione = SUCCESS PROOF
    # Visualmente mostra se l'azione ha avuto effetto
    screenshot_after = Column(LargeBinary)
    
    # Nota: screenshot_after può essere usato come PRE-screenshot 
    # della azione successiva (continuità)
```

---

## 📈 Implementation Phases

### Phase 1: Core Engine Setup (~40-50 hours)
- [ ] Database schemas (Designer + Executor) — 3h
- [ ] Feature extractor (ResNet18 + encode/decode) — 5h
- [ ] Screen stability detection — 3h
- [ ] Template matching (OpenCV) — 4h
- [ ] OCR integration (EasyOCR) — 3h
- [ ] Cosine similarity matching (ResNet features) — 2h
- [ ] Voting algorithm (Template + OCR + ResNet) — 3h
- [ ] BBox expansion logic (3-stage search) — 4h
- [ ] Action executor (click, double-click, drag, input, scroll) — 6h
- [ ] Testing & tuning thresholds — 10h

### Phase 2: Designer Capture System (~25-30 hours)
- [ ] Mouse/keyboard hooks (pynput) — 4h
- [ ] Action capture (click, double-click, drag, input) — 6h
- [ ] Smart bbox generation (edge detection + contours) — 4h
- [ ] Screenshot capture + storage — 3h
- [ ] F9 input detection + CTRL screenshot override — 3h
- [ ] Feature extraction + DB storage — 3h
- [ ] Designer summary review screen — 3h

### Phase 3: Integration & UI (~20-30 hours)
- [ ] Executor flow (frame + loop through steps) — 5h
- [ ] Screen recording (ffmpeg integration) — 3h
- [ ] Mini UI (ESC single/double, F9) — 3h
- [ ] Window manager (minimize/maximize) — 2h
- [ ] Designer create/open screens — 5h
- [ ] Executor create/open screens — 5h
- [ ] Summary screens for both — 4h
- [ ] Integration testing (end-to-end) — 5h
- [ ] Edge cases + error handling — 5h

**Total: ~100 hours (~2.5 weeks full-time, 5-6 weeks part-time)**

---

## 🎯 Decisioni Tecniche - FINALIZED

✅ **Keyboard Shortcuts:**
- `CTRL` — Ricattura screenshot iniziale (se necessario durante azione)
- `F9` — Fine INPUT → Cattura screenshot POST
- `ENTER` — Fine INPUT → Cattura screenshot POST
- `ESC` — **UNA SOLA FUNZIONE: Termina completamente (Designer o Executor) → Summary Screen**
  (Se premi ESC durante INPUT, finisce INPUT e Designer tutto insieme)

✅ **Database Schema:**
- Renamed: `GTImage` → `DesignerStep`
- Screenshot unico per azione (riusato come PRE e POST)
- DRAG: 2 bbox + 2 ocr + 2 resnet (source + destination)

✅ **Feature Extraction (come miao):**
- ResNet18 con ImageNet1K pre-trained weights
- Layer: avgpool (512-dim float32 vector)
- Storage: encoded as bytes nel DB
- Matching: cosine similarity (threshold 0.80+)

✅ **Matching Algorithm:**
- Voting intelligente: almeno 2 su 3 metodi (Template + OCR + ResNet)
- 3-Stage search: original bbox → expanded → full-screen
- Special DRAG: match source e destination separatamente

✅ **Screen Stability:**
- Aspetta che animazioni finiscano (pixel diff < 2%)
- Check ogni 100ms, timeout 3s max
- Screenshot catturato solo quando stabile

✅ **Performance Target:**
- Matching < 1s per step (acceptable latency)
- Full-screen template matching parallelizable se lento


---

## 📝 Next Steps

1. **Leggere questo plan** ✅
2. **Decidere su librerie/tecnologie**
3. **Creare folder structure**
4. **Implementare Phase 1 (Executor)**
5. **Test con designer DB di miao**

---

**Ready to code?** 🚀

---
