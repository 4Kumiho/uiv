# UI-Validator Executor - Documentation

## 1. Introduction

**Executor** is a tool that replays recorded UI action sequences on a screen. It loads a Designer session database, finds UI elements using intelligent 2-stage matching (template + OCR + ResNet), executes recorded actions, records a video of the replay, and reports results with success/failure status and match confidence scores.

**Main workflow**:
- **Create Session** → Select Designer session + monitor
- **Execution** → Automatic element matching and action replay with video recording
- **Summary Screen** → View video and colored step results

---

## 2. Available Screens

### 2.1 Create Screen (`executor_create.py`)

Initial screen for starting a new execution session.

**Elements**:
- **Session Name** (TextInput): Unique name for this execution
- **Designer Folder** (FileBrowser): Folder containing Designer session
- **Output Folder** (FileBrowser): Where to save execution results
- **Monitor** (Spinner): Which monitor to replay on
- **Start Execution button**: Begins the execution

**Flow**:
1. User enters session details
2. Validates input (non-empty name, existing folders, monitor selected)
3. Searches Designer folder for `.db` file
4. **Minimizes Kivy window** (SW_MINIMIZE)
5. Launches `main_executor.py` as a subprocess
6. Background thread waits for `execution_done.json` signal
7. When subprocess finishes:
   - Restores Kivy window (SW_RESTORE, SetForegroundWindow)
   - Loads session in Summary Screen
   - Navigates to Summary Screen

---

### 2.2 Open Screen (`executor_open.py`)

Screen to open an existing execution session.

**Elements**:
- **Execution Folder** (FileBrowser): The execution folder to open
- **Open Execution button**: Loads the session

**Flow**:
1. User selects an execution folder
2. Validates that folder contains `execution.db`
3. Loads execution session from database
4. Navigates to Summary Screen

---

### 2.3 Summary Screen (`executor_summary.py`)

Screen for viewing execution results with synchronized video playback.

**Layout**:
```
[< Back]  Execution: xxx — ● COMPLETED / ✗ FAILED / ⏹ STOPPED
──────────────────────────────────────────────────────────────
│ LEFT PANEL (40%)    │  RIGHT PANEL (60%)               │
│ Steps:              │  VideoPlayer (Kivy)              │
│  - CLICK   [green]  │  ┌────────────────────────────┐  │
│  - INPUT   [green]  │  │                            │  │
│  - CLICK   [red]    │  │  execution.mp4 (looping)   │  │
│  - DRAG    [yellow] │  │                            │  │
│  - SCROLL  [gray]   │  └────────────────────────────┘  │
│                     │  Step Information:               │
│ [selected shows]:   │  ┌────────────────────────────┐  │
│  Status: PASS       │  │ Step N: ACTION_TYPE        │  │
│  Score: 0.92        │  │ Status: PASS               │  │
│  Stage: 1           │  │ Match Score: 0.92          │  │
│  Found at: {x,y}    │  │ Match Stage: 1             │  │
│                     │  │ Found at: x=100, y=50      │  │
└─────────────────────┴──────────────────────────────────┘
```

**Features**:
- **Step list** (left): Colored buttons showing status
  - Green (✓): Step executed successfully
  - Red (✗): Step failed to match or execute
  - Yellow (—): Step was stopped by user
  - Gray (?): Unknown/pending status
- **Video player** (right): Synchronized playback of execution
- **Step info panel** (right): Details of selected step
- **Click to jump**: Click any step → video jumps to that timestamp
- **Color-coded**: Status colors match buttons in step list

---

## 3. Data Structure for Execution Tracking

### 3.0 What Gets Recorded

The Executor captures execution details for each step:

```
Recording Process:
1. Capture current screenshot
2. Use 2-stage matching to find element
3. Execute action if found
4. Capture screenshot after action
5. Save execution record with:
   - Status (PASS/FAIL/STOPPED)
   - Match score (0.0-1.0)
   - Match stage (1 or 2)
   - Found bbox location
   - Video timestamp
   - Error message (if failed)
```

**Why this matters**:
- **Match Score**: How confident the matching algorithm was (1.0 = perfect)
- **Match Stage**: Which stage found the element (1 = original position, 2 = full-screen search)
- **Video Timestamp**: Exact moment in video when action executed
- **Error Details**: Why a step failed (element not found, execution error, etc.)

---

## 4. Operational Flow - Execution Session

### 4.1 Mini UI Overlay - Controls and Indicators

#### Mini UI Layout (Dark Theme, Bottom-Left)
```
● REC  Step 1/10
```
- Width: 135px, Height: 28px
- Position: Bottom-left corner of screen
- Always on top, semi-transparent (alpha: 0.92)

#### Color Indicators
| Element | Color | Meaning |
|---------|-------|---------|
| `●` Dot | Orange (#f39c12) | Execution in progress |
| **REC** | White text, orange bg | Status label |
| **Step N/Total** | Gray text | Current step / total steps |

#### Keyboard Controls
| Action | Effect |
|--------|--------|
| **ESC** | Stop execution, finalize video, write `execution_done.json`, exit |
| **Mouse/Keyboard** | (Locked during execution) |

---

### Execution Phases - Detailed

#### Phase 1: Initialization

```
1. User clicks "Start Execution" in Create Screen
2. Validates input (name, folders, monitor)
3. Creates execution folder: {output_folder}/{session_name}/
4. Minimizes Kivy window (ShowWindow, SW_MINIMIZE)
5. Launches main_executor.py as subprocess:
   - main_executor.py session_name designer_db_path output_folder monitor_num
```

**main_executor.py startup**:
```
1. Add project_root to sys.path
2. Initialize ExecutorApp(session_name, designer_db_path, output_folder, monitor_num)
3. app.start():
   - Load Designer database
   - Get first Designer session from DB
   - Load all Designer steps (the actions to replay)
   - Create ExecutorDatabase in {output_folder}/{session_name}/
   - Create ExecutionSession record
   - Get monitor info from mss
   - Setup logging
   - Create ScreenshotHandler
   - Create Matcher (2-stage algorithm)
   - Create ActionExecutor (pynput controller)
   - Create MiniUI overlay
   - Preload OCR and ResNet models (lazy-load trigger)
   - Start VideoRecorder with FFmpeg
   - Set ready state
   - Enter loop: for each designer_step
4. When user presses ESC or loop completes:
   - Stop video recording
   - Update session status (COMPLETED or STOPPED)
   - Write execution_done.json with execution_id + db_path + video_path
   - Exit main_executor.py
```

#### Phase 2: Execution Loop

```
For each Designer step in order:
  1. Update Mini UI: "Step N/Total"
  2. Capture current screenshot
  3. Match element:
     - Stage 1: Search near original bbox position (±150px)
     - Stage 2: Full-screen search (if Stage 1 fails)
  4. If element found:
     - Log match score and stage
     - Execute action (click, input, drag, scroll)
     - Wait for screen stability
     - Capture screenshot after action
     - Save ExecutionStep with status=PASS
  5. If element not found:
     - Log match scores from both stages
     - Save ExecutionStep with status=FAIL
  6. Update Mini UI for next step
```

#### Phase 3: Action Execution

When an element is found:

```
1. _on_element_found(matched_bbox):
   - matched_bbox: {'x': int, 'y': int, 'w': int, 'h': int}
   - ActionExecutor.execute(designer_step, matched_bbox):
     - Read coordinates_rel from designer_step
     - Calculate click position:
       * x = matched_bbox['x'] + coordinates_rel['x']
       * y = matched_bbox['y'] + coordinates_rel['y']
     - For SINGLE_CLICK: pynput.mouse.click()
     - For DOUBLE_CLICK: pynput.mouse.click(clicks=2)
     - For RIGHT_CLICK: pynput.mouse.click(button=Button.right)
     - For INPUT: pynput.keyboard.type(text)
     - For DRAG: pynput.mouse drag from start to end
     - For SCROLL: pynput.mouse.scroll(dx, dy)
   - Wait 1 second for screen stability
   - Capture post-action screenshot

2. _save_step(designer_step, status, match_details):
   - Create ExecutionStep with:
     * designer_step_id (reference to original)
     * step_number (order)
     * action_type (CLICK, INPUT, etc.)
     * status (PASS, FAIL, STOPPED)
     * match_score (0.0-1.0 from voting)
     * match_stage (1 or 2)
     * matched_bbox (where element was found)
     * screenshot_after (PNG post-action)
     * video_timestamp (seconds from video start)
     * error_msg (if failed)
   - Save to database
```

#### Phase 4: Termination

```
User presses ESC or all steps complete:
1. Set should_stop = True
2. Main loop continues finishing current step
3. Main loop exits after all steps
4. VideoRecorder.stop():
   - Send 'q' command to FFmpeg
   - Wait for graceful shutdown
   - Save video to {output_folder}/{session_name}/execution.mp4
5. Update ExecutionSession status (COMPLETED or STOPPED)
6. Write execution_done.json:
   {
     "execution_id": 1,
     "db_path": "C:/.../execution.db",
     "video_path": "C:/.../execution.mp4",
     "status": "COMPLETED"
   }
7. main_executor.py exits
```

**executor_create.py (background thread)**:
```
1. Wait for subprocess to finish (proc.wait())
2. Read execution_done.json
3. Call Clock.schedule_once(_on_execution_done, 0)  # Thread-safe
4. _on_execution_done(execution_id, db_path):
   - Restore Kivy window (SW_RESTORE, SetForegroundWindow)
   - summary.load_session(execution_id, db_path)
   - Navigate to "executor_summary" screen
```

---

## 5. Summary Screen Operations

### Loading a Session

```
1. executor_summary.load_session(execution_id, db_path, video_path) is called
2. _on_enter() is called (Kivy lifecycle)
3. _populate():
   - Opens ExecutorDatabase(db_path)
   - Fetches ExecutionSession by ID
   - Fetches all ExecutionSteps ordered by step_number
   - Updates title: "Execution: {name}"
   - Updates status color (green/red/yellow)
   - Calls _populate_steps()
4. _populate_steps():
   - Creates Button for each step
   - Color-codes by status (PASS=green, FAIL=red, STOPPED=yellow)
   - Symbol prefix (✓/✗/—/?)
   - Button text: "{symbol} {step_num}. {action_type}"
5. Load video:
   - Sets video source to execution.mp4
   - Video plays in loop
```

### Viewing a Step

```
1. User clicks on a step button:
   - _on_step_selected(button)
   - Extracts step object from button
   - _update_step_info(step):
     - Shows step number and action type
     - Shows status (PASS/FAIL/STOPPED)
     - Shows match_score (2 decimal places)
     - Shows match_stage (1 or 2)
     - Shows matched_bbox coordinates (x, y)
     - Shows error_msg if status=FAIL

2. Jump video to timestamp:
   - self.ids.video_player.position = step.video_timestamp
   - Video immediately seeks to that moment
   - User can see action being executed
```

---

## 6. Database Schema

**Type**: SQLite  
**Location**: `{execution_folder}/execution.db`  
**Auto-creation**: Created automatically on first use

### Tables

**Table: execution_session**
```sql
CREATE TABLE execution_session (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  name                TEXT NOT NULL,
  designer_db_path    TEXT,           -- Path to source Designer DB
  designer_session_id INTEGER,        -- ID in Designer DB
  video_path          TEXT,           -- Path to execution.mp4
  status              TEXT,           -- COMPLETED, STOPPED, FAILED
  created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
)
```

**Table: execution_step**
```sql
CREATE TABLE execution_step (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id          INTEGER NOT NULL FOREIGN KEY REFERENCES execution_session(id),
  designer_step_id    INTEGER NOT NULL,      -- ID in Designer DB
  step_number         INTEGER NOT NULL,      -- Order
  action_type         TEXT NOT NULL,         -- CLICK, INPUT, DRAG, SCROLL, etc.
  status              TEXT,                  -- PASS, FAIL, STOPPED
  match_score         FLOAT,                 -- 0.0-1.0 (voting result)
  match_stage         INTEGER,               -- 1 or 2
  matched_bbox        TEXT,                  -- JSON: {x, y, w, h}
  screenshot_after    BLOB,                  -- PNG post-action
  video_timestamp     FLOAT,                 -- Seconds from video start
  error_msg           TEXT,                  -- Failure reason
  created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
)
```

---

## 7. 2-Stage Matching Algorithm

### Stage 1: Original Position Search (Fast Path)

```
If original window position hasn't changed:
  1. Extract bbox from Designer (absolute coordinates)
  2. Define search region: bbox ± 150px
  3. Template match bbox_screenshot in region
  4. Vote on confidence:
     - Template score (0.4 weight)
     - OCR score (0.3 weight) - if text available
     - ResNet score (0.3 weight)
  5. If total score >= 0.70 → MATCH FOUND (Stage 1)
  6. Else → proceed to Stage 2
```

**Threshold**: 0.70  
**Advantage**: Fast (no full-screen search), accurate when window position stable

### Stage 2: Full-Screen Search (Robust Path)

```
If Stage 1 fails:
  1. Extract bbox_screenshot (element image)
  2. Template match on entire screen
  3. For each top candidate:
     - Vote on confidence (same weights as Stage 1)
     - Keep best match
  4. If best score >= 0.60 → MATCH FOUND (Stage 2)
  5. Else → MATCH FAILED
```

**Threshold**: 0.60 (lower than Stage 1)  
**Advantage**: Works even if window moved or repositioned

### Voting Algorithm

```
total_score = (0.4 * template_score) + (0.3 * ocr_score) + (0.3 * resnet_score)

Where:
  - template_score: OpenCV matchTemplate (CCOEFF_NORMED)
    Range: 0.0-1.0 (1.0 = perfect pixel match)
  
  - ocr_score: Text similarity
    Range: 0.0-1.0 (0 if no text, 1.0 if perfect match)
    - 0.9 if reference text contained in detected text
    - Word overlap percentage otherwise
  
  - resnet_score: Feature similarity (cosine distance)
    Range: 0.0-1.0 (1.0 = identical features)
    - Extracted from ResNet18 512-dim vectors
    - Cosine similarity = (A·B) / (|A| * |B|)
    - Mapped [-1, 1] to [0, 1]
```

### Why 2-Stage is Robust

```
Scenario 1: Window in original position
  → Stage 1 succeeds (fast)
  → No need for full-screen search

Scenario 2: Window moved 100px right
  → Stage 1 fails (looking in wrong region)
  → Stage 2 succeeds (searches entire screen)
  → Uses bbox_screenshot to find element regardless of position

Scenario 3: UI element visual changed slightly
  → Template match may drop below threshold
  → OCR + ResNet provide additional signals
  → Voting algorithm averages all three signals
  → Often still succeeds despite visual change
```

---

## 8. Component Details

### 8.1 VideoRecorder (`video_recorder.py`)

**Purpose**: Records screen during execution replay

**Implementation**: FFmpeg with platform-specific capture

- **Windows**: `gdigrab` (GDI grab)
- **Linux**: `x11grab` (X11 screen)
- **macOS**: `avfoundation`

**Settings**:
- Framerate: 10 fps (for replay, not real-time)
- Codec: libx264 (H.264)
- Preset: ultrafast (minimal CPU)
- Resolution: Exact monitor resolution
- Offset: Monitor left/top position

**API**:
```python
recorder = VideoRecorder(output_path, monitor_info)
recorder.start()
timestamp = recorder.get_timestamp()  # Seconds since start
recorder.stop()  # Graceful shutdown
```

### 8.2 Matcher (`matcher.py`)

**Purpose**: 2-stage element matching

**Key Methods**:
```python
matcher = Matcher()
result = matcher.find(designer_step, current_screenshot)
# Returns: {
#   'found': bool,
#   'bbox': {'x', 'y', 'w', 'h'},
#   'score': 0.0-1.0,
#   'stage': 1 or 2,
#   'error': str or None
# }
```

**Dependencies**:
- OpenCV (template matching)
- EasyOCR (text extraction)
- ResNet18 (feature extraction)

### 8.3 ActionExecutor (`action_executor.py`)

**Purpose**: Executes actions on found elements

**Supported Actions**:
- SINGLE_CLICK, DOUBLE_CLICK, RIGHT_CLICK
- INPUT (text typing)
- DRAG_AND_DROP
- SCROLL

**Implementation**: `pynput` library for global control

```python
executor = ActionExecutor(monitor_info)
executor.execute(designer_step, found_bbox, wait_time=1.0)
```

### 8.4 ExecutorDatabase (`executor_db.py`)

**Purpose**: CRUD operations for execution records

**Key Methods**:
```python
db = ExecutorDatabase(db_path)
session = db.create_session(name, designer_db_path, designer_session_id)
step = db.add_step(session_id, step_object)
db.update_session_status(session_id, status, video_path)
steps = db.get_steps(session_id)
db.close()
```

---

## 9. Workflow Comparison: Designer vs Executor

| Aspect | Designer | Executor |
|--------|----------|----------|
| **Input** | User actions on screen | Recorded Designer steps |
| **Output** | Database + screenshots | Database + video |
| **Matching** | BBox generation (edge detection) | 2-stage element search |
| **Main Loop** | Wait for user input | Iterate through steps |
| **Mini UI** | Status + step counter + F9 button | Status + step progress |
| **Result Storage** | DesignerStep records | ExecutionStep records |
| **Video** | None | FFmpeg screen recording |
| **Failure Handling** | User can retry | Marks step as FAIL |

---

## 10. Verification Checklist

After implementation, verify:

1. **FFmpeg Setup**
   - [ ] Run `python src/bin/setup_ffmpeg.py`
   - [ ] Check `src/bin/ffmpeg[.exe]` exists

2. **Database Models**
   - [ ] ExecutionSession table created
   - [ ] ExecutionStep table created
   - [ ] Relationships established

3. **Executor Create Flow**
   - [ ] Find Designer DB in folder
   - [ ] Validate monitor selection
   - [ ] Launch subprocess
   - [ ] Wait for signal file
   - [ ] Navigate to summary

4. **Executor Open Flow**
   - [ ] Find execution.db in folder
   - [ ] Load first session
   - [ ] Display in summary

5. **Execution**
   - [ ] Mini UI appears
   - [ ] Video recording starts
   - [ ] Steps execute in order
   - [ ] Match scores logged
   - [ ] ESC stops execution
   - [ ] Signal file written

6. **Summary Screen**
   - [ ] Video plays
   - [ ] Steps colored correctly
   - [ ] Click step → video jumps
   - [ ] Step info displays correctly
   - [ ] Back button returns to main
