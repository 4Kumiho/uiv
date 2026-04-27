# UI-Validator Designer - Documentation

## 1. Introduction

**Designer** is a tool that records UI action sequences (clicks, text input, scrolling, dragging) on a screen. During recording, it captures screenshots, generates smart bounding boxes using edge detection, extracts text via OCR (EasyOCR), and extracts visual features using ResNet18. All data is saved to a SQLite database for review and editing.

**Main workflow**:
- **Create Session** → Record actions with Mini UI overlay
- **Data saved** → Database + PNG screenshots
- **Summary Screen** → View and modify recorded data

---

## 2. Available Screens

### 2.1 Create Screen (`designer_create.py`)

Initial screen for starting a new recording session.

**Elements**:
- **Session Name** (TextInput): Unique name for this session
- **Output Folder** (FileBrowser): Where to save the data
- **Monitor** (Spinner): Which monitor to record from
- **Start Recording button**: Begins the recording

**Flow**:
1. User enters session details
2. Validates input (non-empty name, existing folder, monitor selected)
3. Creates project folder: `{output_folder}/{session_name}/`
4. **Minimizes Kivy window** (SW_MINIMIZE)
5. Launches `main_designer.py` as a subprocess
6. Background thread waits for `session_done.json` signal
7. When subprocess finishes:
   - Restores Kivy window (SW_RESTORE, SetForegroundWindow)
   - Loads session in Summary Screen
   - Navigates to Summary Screen

---

### 2.2 Open Screen (`designer_open.py`)

Screen to open an existing recording session.

**Elements**:
- **Project Folder** (FileBrowser): The project folder to open
- **Open Recording button**: Loads the session

**Flow**:
1. User selects a project folder
2. Validates that folder contains a database
3. Loads session from database
4. Navigates to Summary Screen

---

### 2.3 Summary Screen (`designer_summary.py`)

Screen for viewing, editing, and saving a recorded session.

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

**Features**:
- **Step list** (left): Scroll and click to view a step
- **Screenshot** (right): Image viewer with `fit_mode: "contain"` (responsive)
- **Interactive BBox**:
  - Drag interior → move BBox
  - Drag edge/corner → resize BBox
  - Drag click dot → reposition where the click occurred
  - Hover → cursor changes to "hand"
- **Metadata bar**: Shows OCR text and ResNet features
  - **Single-action steps**: 1 BBox
  - **DRAG_AND_DROP**: 2 BBox (start + end) with info for both
- **Save button**: Re-extracts OCR/ResNet for modified BBox, saves to database
  - Disabled if no changes made
  - Launches worker process `_ocr_feature_update.py` for each modified BBox

---

## 3. Data Structure Optimization (Position-Independent Matching)

### 3.0 What Makes the New Design Robust

The Designer now stores both **absolute** and **relative** coordinates:

```
Full-screen monitor (1920×1080)
┌─────────────────────────────────────┐
│  bbox (absolute): x=100, y=50       │
│  ┌──────────────────────────────┐   │
│  │                              │   │
│  │  click: (180, 110) absolute  │   │
│  │  click: (80, 60) relative    │   │
│  │                              │   │
│  └──────────────────────────────┘   │
└─────────────────────────────────────┘

coordinates (absolute):   {x: 180, y: 110}
coordinates_rel:         {x: 80, y: 60}    ← 180-100, 110-50
```

**Why this matters**:
- **Absolute data** (`bbox`, `coordinates`) → optimizes matching when window is in original position
- **Relative data** (`coordinates_rel`) → enables robust matching even when window moves
- **BBox crop** (`bbox_screenshot`) → allows full-screen search independent of original position

This architecture makes the **Executor** robust to window repositioning while maintaining performance when windows stay in place.

---

## 3. Detailed Operational Flow - Recording Session

### 3.1 Mini UI Overlay - Controls and Indicators

#### Mini UI Layout (Dark Theme, Bottom-Left)
```
● REC  Step 1     [F9]
```
- Width: 135px, Height: 28px
- Position: Bottom-left corner of screen
- Always on top, semi-transparent (alpha: 0.92)

#### Color Indicators
| Element    | Color                   | Meaning                             |
|------------|-------------------------|------------------------------------|
| `●` Dot    | Orange (#f39c12)        | Recording in progress               |
| **REC**    | White text, red bg      | Status label (always visible)       |
| **Step N** | Gray text               | Next step number to record          |
| **[F9]**   | Orange button           | Input finalizer button              |

#### Keyboard Controls
| Action | Effect |
|--------|---------|
| **ESC** | Stop recording, close Mini UI, write `session_done.json`, exit |
| **F9** | Finalize INPUT (when in text field) |
| **ENTER** | Add newline to text (during INPUT), continue typing |
| **CTRL+C** | Alternative way to stop (if ESC doesn't work) |
| **Mouse click** | Capture SINGLE_CLICK: generates BBox, extracts OCR and features |
| **Double-click** | Capture DOUBLE_CLICK: same as single click |
| **Right-click** | Capture RIGHT_CLICK: same as single click |
| **Mouse drag** | Capture DRAG_AND_DROP: 2 BBox (start + end positions) |
| **Mouse scroll** | Capture SCROLL: records dx, dy values |
| **Type text** | Capture INPUT: press F9 to finish, ENTER for new line |

#### Mini UI States

1. **Red (Loading)** — Models (OCR/ResNet) are preloading or step is being saved
2. **Green (Ready)** — Ready to capture actions
3. **Step N** — Updated after each completed step

---

### Recording Phases - Detailed

#### Phase 1: Initialization

```
1. User clicks "Start Recording" in Create Screen
2. Validates input (name, folder, monitor)
3. Creates project folder: {output_folder}/{session_name}/
4. Creates subfolder: {project}/screenshots/
5. Minimizes Kivy window (ShowWindow, SW_MINIMIZE)
6. Launches main_designer.py as subprocess:
   - main_designer.py session_name output_folder monitor_num
```

**main_designer.py startup**:
```
1. Add project_root to sys.path
2. Initialize DesignerApp(session_name, db_path, monitor_num)
3. app.start():
   - Create DesignerSession in database (auto-generated session_id)
   - Get monitor info from mss (resolution, position)
   - Setup logging with colored output
   - Create ScreenshotHandler
   - Create MiniUI overlay (dark theme)
   - wait_for_screen_stability() — wait for screen to settle
   - set_loading() — show red status
   - Create ActionCapture with global keyboard/mouse hooks
   - start_recording() — begin listening for events
   - Preload models in background thread:
     - Load OCR model (EasyOCR)
     - Load ResNet18 model
   - set_ready() — show green status
   - Enter loop: while not should_stop
4. When user presses ESC:
   - Set should_stop = True
   - Exit loop
   - Clean up resources
   - Write session_done.json with session_id + db_path
   - Exit main_designer.py
```

#### Phase 2: Recording Loop

```
While recording is active:
  - mini_ui.update() — update display
  - Wait for mouse/keyboard events (global hooks)
  - When event detected:
    - ActionCapture._on_mouse_event() or _on_key_event()
    - Capture coordinates/text
    - screenshot_handler.wait_for_screen_stability()
    - Grab screenshot from buffer
    - Call on_action_callback
  - Update Mini UI step counter
  - Wait for screen stability before next step
```

#### Phase 3: Action Capture and Processing

When an action is captured:

```
1. _on_action_captured(action_dict):
   - Save screenshot as PNG in {project}/screenshots/step_NNN.png
   - Generate smart BBox from click coordinates
   - Crop image to BBox region (produces bbox_screenshot)
   - Extract OCR text from BBox crop
   - Extract ResNet 512-dimensional feature vector from BBox crop
   - Calculate relative coordinates: rel_x = click_x - bbox.x
   - _save_step_to_db():
     - Create DesignerStep object with:
       * screenshot (full-screen PNG)
       * bbox (absolute coordinates)
       * coordinates (absolute click position)
       * bbox_screenshot (PNG crop of element)
       * coordinates_rel (relative click position)
       * ocr_text, features
     - Save to database
   - Increment step counter
   - Update Mini UI with new step number
   - Wait for screen stability

2. For DRAG_AND_DROP:
   - Capture 2 coordinates (start + end)
   - Generate 2 BBox (one for start, one for end)
   - Crop to both BBox regions
   - Extract OCR + ResNet for both
   - Calculate relative coordinates for both start and end
   - Save all data:
     * bbox, coordinates, bbox_screenshot, coordinates_rel (start)
     * drag_end_bbox, drag_end_coordinates, drag_end_bbox_screenshot, drag_end_coordinates_rel (end)

3. For INPUT (text):
   - Screenshot taken BEFORE user starts typing
   - User types text (press ENTER for new line)
   - User presses F9 to finish
   - Generate BBox from the initial screenshot
   - Crop and extract OCR + ResNet from BBox crop
   - Calculate relative coordinates
   - Save to database with input_text, bbox, coordinates_rel, bbox_screenshot, ocr_text, features
```

#### Phase 4: Termination

```
User presses ESC:
1. ActionCapture.listener.stop() — stop event listeners
2. ActionCapture._cleanup() — release resources
3. Set should_stop = True
4. Main loop exits
5. Write session_done.json:
   {
     "session_id": 1,
     "db_path": "C:/.../{session_name}.db"
   }
6. main_designer.py exits
```

**designer_create.py (background thread)**:
```
1. Wait for subprocess to finish (proc.wait())
2. Read session_done.json
3. Call Clock.schedule_once(_on_session_done, 0)  # Thread-safe Kivy call
4. _on_session_done():
   - Restore Kivy window (SW_RESTORE)
   - Bring window to foreground (SetForegroundWindow)
   - summary.load_session(session_id, db_path)
   - Navigate to "designer_summary" screen
```

---

## 4. Summary Screen Operations

### Loading a Session

```
1. designer_summary.load_session(session_id, db_path) is called
   - Stores session_id and db_path as attributes
   - Sets _pending_load = True

2. on_enter() is called (Kivy lifecycle event):
   - Checks _pending_load
   - Calls Clock.schedule_once(_populate, 0)  # Thread-safe

3. _populate():
   - Opens DesignerDatabase(db_path)
   - Fetches session and all steps (ordered by step_number)
   - Closes database connection
   - Updates session label with info
   - Calls _build_step_list()

4. _build_step_list():
   - Creates StepRow for each step
   - Adds to ScrollView (left panel)
   - Automatically selects first step
```

### Viewing a Step

```
1. User clicks on a StepRow:
   - _on_step_selected(row)
   - Finds step using step_number
   - Calls _show_step_image(step)

2. _show_step_image(step):
   - Decodes screenshot PNG bytes → numpy BGR array
   - Stores as self._current_screenshot_bgr
   - _draw_overlays(bgr, step):
     - Reads BBox coordinates from JSON
     - Draws rectangle (red for start, purple for end)
     - Reads click coordinates from JSON
     - Draws circle at click point
     - Returns annotated BGR image
   - Converts BGR → RGB
   - Flips vertically (OpenCV y=top, Kivy y=bottom)
   - Creates Kivy Texture for display
   - Binds touch events for BBox interaction
   - _update_metadata(step):
     - Shows OCR text (first 100 chars)
     - Shows ResNet info (512-dimensional vector)
     - For DRAG_AND_DROP: shows info for both BBox
```

### Modifying BBox and Click Points

```
1. User touches BBox or click dot:
   - _on_image_touch_down():
     - Converts touch coordinates from widget space to image space
     - Detects which BBox was touched (or click point within 20px)
     - Identifies interaction type (move, resize corner, resize edge)

2. User drags:
   - _on_image_touch_move():
     - Calculates delta from last position
     - _apply_bbox_drag():
       - Applies movement or resize
       - Clamps to stay within image bounds
       - Updates BBox coordinates
     - _redraw_image_with_modified_bbox():
       - Draws preview with modified BBox or click position

3. User releases:
   - _on_image_touch_up():
     - Finalizes drag operation
     - Saves modified BBox/click point to step object
     - Marks step as modified in _modified_steps set
     - Enables Save button
     - Redraws image with final BBox
```

### Saving Modified Steps

```
1. User clicks Save:
   - save_session():
     - For each modified step in _modified_steps:
       - Logs step information (bbox, coordinates, action_type)
       - _process_step():
         - Decodes screenshot PNG
         - Reads BBox JSON
         - Crops image to BBox region
         - Launches _ocr_feature_update.py as subprocess:
           - Path: ./src/app/core/designer/_ocr_feature_update.py
           - Arguments: screenshot_path bbox_json
           - Output: {"ocr_text": "...", "features": "hex_string", "bbox_screenshot": "hex_string"}
         - Receives JSON output from process
         - Converts hex strings → bytes
         - Saves step.ocr_text, step.features, step.bbox_screenshot
         - Recalculates step.coordinates_rel:
           * rel_x = coordinates.x - bbox.x
           * rel_y = coordinates.y - bbox.y
           * Handles manual bbox edits + manual click point edits
         - Logs all updates: "ocr_text", "features", "bbox_screenshot", "coordinates_rel"
       - For DRAG_AND_DROP: also processes drag_end_bbox with same logic

2. Manual edits in Summary Screen (before Save):
   - User drags BBox: bbox and coordinates_rel are recalculated immediately
   - User drags click point: coordinates and coordinates_rel are recalculated immediately
   - Changes marked in _modified_steps set

3. After all worker processes finish:
   - Opens database connection
   - Logs "💾 SAVING ALL N STEPS TO DATABASE..."
   - Calls db.update_step(session_id, step) for each modified step
   - Reloads steps from database:
     - Remembers current step_number
     - Fetches all fresh steps
     - Finds step with same step_number
     - Calls _show_step_image() to redraw with updated data
   - Clears _modified_steps set
   - Disables Save button
   - Logs "✅ SESSION SAVED TO DATABASE"
```

### Going Back

```
User clicks "< Back":
  - go_back():
    - Clears image display
    - Navigates to "main" screen
    - Uses right transition direction
```

---

## 5. Database

**Type**: SQLite  
**Location**: `{project_folder}/{session_name}.db`  
**Auto-creation**: Created automatically on first use

### Tables

**Table: designer_session**
```sql
CREATE TABLE designer_session (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  name         TEXT NOT NULL,
  created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
)
```

**Table: designer_step**
```sql
CREATE TABLE designer_step (
  id                      INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id              INTEGER NOT NULL FOREIGN KEY REFERENCES designer_session(id),
  step_number             INTEGER NOT NULL,
  action_type             TEXT NOT NULL,
  -- Types: SINGLE_CLICK, DOUBLE_CLICK, RIGHT_CLICK, SCROLL, INPUT, DRAG_AND_DROP
  
  -- Screenshot and click location (ABSOLUTE coordinates)
  screenshot              BLOB,              -- PNG image bytes (full-screen)
  screenshot_path         TEXT,              -- File path to PNG
  coordinates             TEXT,              -- JSON: {"x": int, "y": int} (absolute)
  
  -- Main BBox and AI extraction
  bbox                    TEXT,              -- JSON: {"x": int, "y": int, "w": int, "h": int} (absolute)
  bbox_screenshot         BLOB,              -- PNG image bytes (bbox crop only) — NEW
  coordinates_rel         TEXT,              -- JSON: {"x": int, "y": int} (relative to bbox) — NEW
  ocr_text                TEXT,              -- Extracted text from BBox
  features                BLOB,              -- ResNet18 512-dim vector (2048 bytes)
  
  -- For INPUT action
  input_text              TEXT,              -- Text that was typed
  press_enter_after       BOOLEAN DEFAULT FALSE,
  
  -- For SCROLL action
  scroll_dx               INTEGER,           -- Horizontal scroll amount
  scroll_dy               INTEGER,           -- Vertical scroll amount
  
  -- For DRAG_AND_DROP action (end position)
  drag_end_coordinates    TEXT,              -- JSON: {"x": int, "y": int} (absolute)
  drag_end_bbox           TEXT,              -- JSON: {"x": int, "y": int, "w": int, "h": int} (absolute)
  drag_end_bbox_screenshot BLOB,             -- PNG image bytes (drag_end bbox crop) — NEW
  drag_end_coordinates_rel TEXT,             -- JSON: {"x": int, "y": int} (relative to drag_end_bbox) — NEW
  drag_end_ocr_text       TEXT,              -- Extracted text from end position BBox
  drag_end_features       BLOB,              -- ResNet18 512-dim vector for end position
  
  created_at              DATETIME DEFAULT CURRENT_TIMESTAMP
)
```

### New Columns for Position-Independent Matching

| Column | Type | Purpose |
|--------|------|---------|
| `bbox_screenshot` | BLOB | PNG crop of just the element (for full-screen search in Executor) |
| `coordinates_rel` | JSON | Click position relative to bbox origin (e.g., `{"x": 80, "y": 60}`) |
| `drag_end_bbox_screenshot` | BLOB | PNG crop of drag end element |
| `drag_end_coordinates_rel` | JSON | Drag end position relative to drag_end_bbox |

**Relationship**:
```
coordinates_rel.x = coordinates.x - bbox.x
coordinates_rel.y = coordinates.y - bbox.y
```

### Operations

**From main_designer.py**:
- `db.create_session(name)` → creates DesignerSession, returns object with auto-generated ID
- `db.add_step(session_id, step)` → inserts new DesignerStep

**From designer_summary.py**:
- `db.get_session(session_id)` → fetches DesignerSession object
- `db.get_steps(session_id)` → fetches all steps ordered by step_number
- `db.update_step(session_id, step)` → updates existing step in database
- `db.close()` → closes database connection

---

## 6. Models Used

### 6.1 BBox (Smart Bounding Box Generator)

**File**: `_bbox_generator.py`  
**Class**: `BBoxGenerator`  
**Method**: `generate_smart_bbox(screenshot, click_x, click_y)`

#### Core Rules

BBox generation follows two key principles:
1. **Always contains the click point** — The generated box must include the exact pixel where the user clicked
2. **Smallest possible box** — Among all valid boxes, select the one with minimum area

#### Algorithm (Multi-method approach)

The generator combines multiple edge detection techniques to find the best bounding box:

```
1. Canny Edge Detection (sensitive):
   - Thresholds: low=5, high=30
   - Dilates results to connect nearby edges

2. Adaptive Thresholding:
   - Detects edges based on local contrast
   - Kernel size: 15x15
   - Dilates results

3. Binary Thresholding:
   - Captures dark areas (dark pixels < 100)
   - Captures light areas (light pixels > 150)
   - Combines both

4. Contour Selection:
   - Finds all contours from combined edge detection
   - Filters: only contours that CONTAIN the click point
   - Filters: size between 5px and 1000px
   - Filters: shape regularity (at least 30% of area filled)
   - Selects: the SMALLEST contour (minimum area)

5. Fallback (if no contour contains click):
   - Uses corner detection (Harris corners)
   - Finds nearby corners within 60px
   - Builds box around them with 3px padding
   - If no corners: draws 25px square centered on click

6. Sanity Check:
   - Verifies click is inside final box
   - If not, expands box by ±10px around click
```

#### Output Format
```json
{
  "x": 100,      // Top-left X coordinate
  "y": 200,      // Top-left Y coordinate
  "w": 150,      // Width in pixels
  "h": 80        // Height in pixels
}
```

#### Storage
- Serialized as JSON string in database `bbox` field
- For DRAG_AND_DROP: 2 boxes stored in `bbox` and `drag_end_bbox`

---

### 6.2 OCR (Optical Character Recognition)

**File**: `_ocr_generator.py`  
**Class**: `OCRGenerator`  
**Method**: `extract(bbox_image)`

#### Model: EasyOCR

**Configuration**:
- Language: English only
- Processing: CPU (GPU not required)
- Loading: Lazy initialization (first call loads the model)

#### How It Works

```
1. First time you extract text from a BBox:
   - Load EasyOCR English model (~50MB)
   - Takes 2-3 seconds

2. For each BBox:
   - Crop image region using BBox
   - Run OCR reader on cropped image
   - Extract all detected text

3. Post-process:
   - Join all text pieces with spaces
   - Remove leading/trailing whitespace
   - Return as plain string

4. If no text detected:
   - Return empty string
```

#### Output Format
```
"Extracted text from BBox"
```

#### Storage
- Saved as plain text in database `ocr_text` field
- For DRAG_AND_DROP: text stored in `ocr_text` and `drag_end_ocr_text`

#### Speed
- First call: ~2-3 seconds (model loads)
- Subsequent calls: ~0.5-1 second per BBox

---

### 6.3 ResNet (Neural Network Features)

**File**: `_feature_generator.py`  
**Class**: `FeatureGenerator`  
**Method**: `extract(bbox_image)`

#### Model: ResNet18 (ImageNet Pretrained)

**Configuration**:
- Architecture: ResNet18 deep neural network
- Training: Pretrained on ImageNet (1000 object categories)
- Processing: GPU if available, otherwise CPU
- Loading: Lazy initialization (first call loads the model)

#### How It Works

```
1. First time you extract features from a BBox:
   - Load ResNet18 model (~40MB)
   - Takes 5-10 seconds

2. For each BBox:
   - Resize image to 256×256 pixels
   - Crop center 224×224 region
   - Convert BGR → RGB
   - Normalize using ImageNet statistics
   
3. Neural Network Processing:
   - Pass through ResNet layers
   - Remove final classification layer
   - Apply global average pooling
   - Output: 512-dimensional vector

4. Return:
   - Floating point array (512 values)
   - Each value is 0.0 to 1.0+ range
   - Represents visual features (edges, textures, shapes, etc.)
```

#### Output Format
```
512-dimensional float vector stored as 2048 bytes (binary)
```

Serialized in database as:
- BLOB format (binary data)
- Converted to hex string for JSON transport

#### Storage
- Saved as binary blob in database `features` field
- For DRAG_AND_DROP: vectors stored in `features` and `drag_end_features`

#### Speed
- First call: ~5-10 seconds (model loads)
- Subsequent calls: ~0.2-0.5 seconds per BBox
- GPU accelerated: ~5x faster than CPU

#### Uses
- **Visual Matching**: Find similar UI elements
- **Clustering**: Group similar elements together
- **Search**: Find visually related steps in session

---

## 7. Executor Integration (How Designer Data is Used)

The Designer's optimized data structure (with `bbox_screenshot` + `coordinates_rel`) enables the **Executor** to be robust to window repositioning.

### Two-Stage Matching Strategy

**Stage 1: Optimized Match (Original Position)**
```
If window hasn't moved:
  - Load bbox (absolute position)
  - Look for element at original bbox region
  - If found → use original coordinates_rel to click
  - Result: FAST (no full-screen search needed)
```

**Stage 2: Full-Screen Search (Window Moved)**
```
If stage 1 fails OR window likely moved:
  - Load bbox_screenshot (PNG crop of element)
  - Load ocr_text + features
  - Search entire screen for visual match
  - Voting algorithm: Template Match + OCR + ResNet18
  - Once found at new location → use coordinates_rel for precise click
  - Result: ROBUST (works even if window moved)
```

### Data Flow Example

```
Recording (Designer saves):
  bbox: {x: 100, y: 50, w: 200, h: 80}        ← absolute position
  coordinates: {x: 180, y: 110}                 ← absolute click
  bbox_screenshot: <PNG crop bytes>             ← element image
  coordinates_rel: {x: 80, y: 60}               ← relative to bbox
  ocr_text: "Submit"
  features: <512-dim ResNet vector>

Execution (Executor uses):
  Stage 1: Found element at {x: 100, y: 50}
    → Click at: 100 + 80 = 180, 50 + 60 = 110 ✓

  OR if Stage 1 fails:
  Stage 2: Found element at {x: 350, y: 200}  (window moved!)
    → Click at: 350 + 80 = 430, 200 + 60 = 260 ✓
    → Correct click despite window repositioning!
```

---

## 8. Future: Executor Architecture

When the Executor is implemented, it will:

1. **Load Designer steps** from the database
2. **For each step**:
   - Stage 1: Try original bbox position (fast path)
   - Stage 2: Full-screen search using bbox_screenshot + features (robust path)
   - Use coordinates_rel to calculate final click position
   - Execute action (click, type, drag, etc.)
3. **Record execution** with success/failure status and match confidence
4. **Generate summary** showing which steps succeeded and which failed
