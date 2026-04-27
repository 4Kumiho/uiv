# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**UI-Validator** is an intelligent UI automation tool that records and replays screen interactions. It consists of two main components:

- **Designer**: Records user actions (clicks, text input, dragging, scrolling) on a screen, captures screenshots, detects elements with bounding boxes, and extracts text + visual features via OCR and ResNet18.
- **Executor**: Replays recorded actions with intelligent element matching that handles screen shifts and visual variations using a 3-stage matching algorithm (template + OCR + ResNet features).

The entire application is built with **Kivy** (Python GUI framework) and uses **SQLAlchemy** to manage SQLite databases.

## Quick Start

### Run the Application

```bash
# Activate virtual environment (if needed)
.venv\Scripts\activate

# Run the UI-Validator app
python -m __main__
```

The app starts on the main screen with options to:
- Create a new Designer recording session
- Open an existing Designer session
- Create a new Executor replay session
- Open an existing Executor session

### Project Structure

```
src/app/
├── menu_pages/main_screen/          # Main menu screen
├── designer_pages/
│   ├── create_screen/               # Start new Designer session
│   ├── open_screen/                 # Load existing Designer session
│   └── summary_screen/              # Review/edit recorded steps
├── executor_pages/
│   ├── create_screen/               # Start new Executor session
│   ├── open_screen/                 # Load existing Executor session
│   └── summary_screen/              # View execution results
└── core/
    ├── designer/                    # Recording engine
    │   ├── main_designer.py         # Orchestration of Designer flow
    │   ├── action_capture.py        # Hooks for mouse/keyboard
    │   ├── screenshot_handler.py    # Screen capture & stability detection
    │   ├── mini_ui.py               # Visual feedback overlay (REC indicator)
    │   ├── _bbox_generator.py       # Smart bounding box detection
    │   ├── _ocr_generator.py        # Text extraction via EasyOCR
    │   └── _feature_generator.py    # ResNet18 feature extraction
    ├── executor/                    # Replay engine (planned)
    ├── database/
    │   ├── designer_db.py           # Database connection & queries
    │   └── models.py                # SQLAlchemy ORM models
    └── utils/
        └── window_manager.py        # Window minimize/restore operations
```

## Architecture Overview

### Designer Flow (Recording)

1. **Initialize**: User provides session name + output folder in `DesignerCreateScreen`
2. **Start**: Kivy window minimizes; `main_designer.py` subprocess starts, creating a Mini UI overlay
3. **Wait for Stability**: System waits for screen to stabilize (animation-free state)
4. **Action Capture**: Global mouse/keyboard hooks detect user interactions:
   - **Click**: Captured, bbox generated, screenshot taken
   - **Input**: Text is buffered until user presses F9/ENTER or clicks elsewhere
   - **Drag**: Two screenshots captured (start and end)
   - **Scroll**: Aggregated over 0.3s (debounce)
5. **Screenshot Reuse**: Post-action screenshot serves three purposes:
   - **Pre-screenshot** for next step's matching
   - **Success proof** that action had visual effect
   - Efficient 1 screenshot per action (vs 2 in naive approach)
6. **End**: ESC key ends recording; all steps saved to database + PNG files
7. **Summary**: `DesignerSummaryScreen` displays recorded steps for review/editing

### Key Data Flow (Designer)

```
Action Detected → Wait for Screen Stability → Screenshot Capture
    ↓
Generate Smart BBox (edge detection + contours)
    ↓
Extract OCR Text + ResNet18 Features (512-dim vectors)
    ↓
Save to Database (DesignerStep record)
    ↓
Screenshot becomes PRE-screenshot for next step
```

### Screen Stability Detection

After each action, the system waits for the screen to stabilize before capturing:

```python
# In screenshot_handler.py
def wait_for_screen_stability(timeout_ms=3000, check_interval_ms=100):
    """Polls screen every 100ms; considers stable when pixel diff < 2%"""
```

This ensures animations/transitions complete before capture, resulting in cleaner images for matching.

## Database Schema

**Designer DB** (`designer.db`):

- `DesignerSession`: Top-level recording session
- `DesignerStep`: Individual action record
  - `action_type`: CLICK, DOUBLE_CLICK, INPUT, DRAG, SCROLL
  - `screenshot`: PNG image (post-action, binary)
  - `bbox`: Bounding box of target element (JSON string)
  - `ocr_text`: Text extracted from bbox region
  - `features`: ResNet18 512-dim feature vector (binary encoded)
  - DRAG-specific fields: `drag_end_bbox`, `drag_end_coordinates`, `drag_end_features`

See `src/app/core/database/models.py` for full schema.

## Important Architectural Patterns

### 1. Smart Screenshot Reuse Pattern

**Problem**: Naively, you need 2 screenshots per action (pre and post). That's 2x storage + 2x I/O overhead.

**Solution**: Post-action screenshot is reused as the pre-screenshot for the next action.

```
[Action 1] → [Screenshot S1] ← (used as PRE for Action 2)
[Action 2] → [Screenshot S2] ← (used as PRE for Action 3)
```

This is enforced by `ActionCapture._finalize_action()` → populating `buffer_screenshot` for the next step.

### 2. Global Hooks for Event Detection

The `ActionCapture` class uses `pynput` library to globally monitor mouse and keyboard events (even when Kivy window is minimized). This allows recording to continue without requiring focus on the app window.

```python
# From action_capture.py
self.mouse_listener = mouse.Listener(
    on_click=self._on_mouse_click,
    on_move=self._on_mouse_move,
    on_scroll=self._on_mouse_scroll
)
self.keyboard_listener = keyboard.Listener(on_press=self._on_key_press)
```

### 3. Click-Type Disambiguation

Since a double-click is actually two clicks, the system uses a 0.4s timer to disambiguate:
- If second click arrives within 0.4s → double-click
- If first click "matures" without second click → single-click

See `ActionCapture.click_decision_timer` logic.

### 4. Input Handling

Text input is aggregated until the user signals completion:
- **F9 key**: Explicitly end input, capture screenshot
- **ENTER**: End input, capture screenshot
- **Click**: End input (click is next step), capture screenshot

This is tracked by `ActionCapture.input_active` flag and `_finalize_input_action()`.

### 5. Scroll Debouncing

Consecutive scroll events are aggregated for 0.3s (configurable), then collapsed into a single SCROLL step with cumulative `dx` and `dy` deltas. Prevents database bloat from rapid scroll-wheel events.

## Mini UI System

The `MiniUI` class (in `mini_ui.py`) provides a small tkinter window overlay that displays:

- **Color feedback**:
  - 🔴 **Red**: Loading/saving (not ready for input)
  - 🟢 **Green**: Ready (user can proceed)
- **Text labels**: "DESIGNER" or "EXECUTOR" + status

This overlay is always-on-top, positioned bottom-left of the screen, and listens for ESC key to end the session.

### Keyboard Shortcuts

- **ESC**: End Designer/Executor, save all steps, go to Summary Screen
- **F9**: (Designer only) End current input, capture screenshot
- **ENTER**: (Designer only) End current input, capture screenshot

## Dependencies

**Core UI & Database**:
- `kivy >= 2.3.0` — GUI framework
- `sqlalchemy` — ORM for database
- `Pillow` — Image processing

**Designer**:
- `opencv-python` — Smart bbox generation (edge detection, contours)
- `pynput` — Global mouse/keyboard hooks
- `numpy` — Array operations

**Executor** (optional, install separately if building replay):
- `torch` — ResNet18 model
- `torchvision` — Pre-trained weights
- `scipy` — Cosine similarity for feature matching
- `easyocr` — OCR text extraction

## Key Classes & Files

### Designer Recording

| File | Class | Purpose |
|------|-------|---------|
| `main_designer.py` | `DesignerApp` | Orchestrates recording flow; manages DB, UI, action capture |
| `action_capture.py` | `ActionCapture` | Global event hooks; action type detection; debouncing |
| `screenshot_handler.py` | `ScreenshotHandler` | Screen capture; stability detection via pixel diff |
| `mini_ui.py` | `MiniUI` | Tkinter overlay for visual feedback + ESC/F9 handling |
| `_bbox_generator.py` | `BBoxGenerator` | Smart bounding box detection (edge detection, contours) |
| `_ocr_generator.py` | `OCRGenerator` | EasyOCR wrapper for text extraction |
| `_feature_generator.py` | `FeatureGenerator` | ResNet18 feature extraction & encoding |

### Kivy Screens (UI)

| File | Class | Purpose |
|------|-------|---------|
| `designer_create.py` | `DesignerCreateScreen` | Input form; launches recording subprocess |
| `designer_open.py` | `DesignerOpenScreen` | Load existing session from folder |
| `designer_summary.py` | `DesignerSummaryScreen` | Display recorded steps; allow edits |
| `executor_create.py` | `ExecutorCreateScreen` | Input form; start replay |
| `executor_open.py` | `ExecutorOpenScreen` | Load existing execution |

### Database

| File | Class | Purpose |
|------|-------|---------|
| `models.py` | `DesignerSession`, `DesignerStep` | SQLAlchemy ORM models |
| `designer_db.py` | `DesignerDatabase` | Connection + CRUD operations |

## Decision Records

### Why Screenshot Reuse?

**Older approach**: Capture pre-screenshot, execute action, capture post-screenshot → 2 screenshots per step.

**Current approach**: Capture only post-action screenshot, reuse for next step's pre-screenshot → 1 screenshot per step.

**Trade-offs**:
- ✅ 50% less I/O and storage
- ✅ Cleaner data (always post-stabilization)
- ✅ Simpler success verification (visual proof in the next step's pre-image)

### Why ResNet18 Features?

**For matching during replay**, the executor compares current screen region against stored reference using three methods:
1. **Template matching** (OpenCV)
2. **OCR text matching** (EasyOCR)
3. **Feature matching** (ResNet18 cosine similarity)

A voting system (2-of-3 agreement) makes matching robust to small visual variations.

### Why Global Hooks?

The Kivy window must minimize during recording to avoid obscuring the target application. Global hooks (pynput) allow capturing events even when Kivy window is minimized/not in focus.

### Why Mini UI?

Provides:
- Visual feedback (red = busy, green = ready)
- Single-button stop (ESC)
- Always-on-top, unobtrusive overlay

## Testing & Debugging

### Logging

Logging is configured in `src/app/core/designer/logging_config.py`. Adjust log level there.

```python
# Default: INFO level
# For verbose output, change to DEBUG
```

### Common Issues

| Issue | Root Cause | Solution |
|-------|-----------|----------|
| Actions not captured | Global hooks not active | Ensure `action_capture.start_recording()` is called after Mini UI ready |
| Screenshot blank | Monitor info incorrect | Verify `monitor_num` in `DesignerCreateScreen` matches target screen |
| Stability timeout | App has long animations | Increase `wait_for_screen_stability()` timeout_ms parameter |
| BBox too large/small | Edge detection sensitivity | Tune BBox generator thresholds in `_bbox_generator.py` |

## Implementation Notes for Executor

The **Executor** (replay engine) is planned but not yet implemented. When building it, refer to:

1. **PLAN.md** for detailed 3-stage matching algorithm
2. **Models**: Use `DesignerStep` records to read stored references
3. **Matching**: Implement `Matcher` class combining Template + OCR + ResNet (voting)
4. **Execution**: `ActionExecutor` class for click/drag/input/scroll operations
5. **Screen Recording**: Integration with ffmpeg for replay video

The executor will use the same database schema and follow the action replay flow described in PLAN.md.

## Future Enhancements

See **PLAN.md** for:
- Phase 1: Core engine setup (matching algorithms, feature extraction)
- Phase 2: Designer capture system (already in progress)
- Phase 3: Integration & UI polish
- Implementation phases with estimated effort

