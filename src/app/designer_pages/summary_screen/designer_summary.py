"""
DesignerSummaryScreen — shows recorded steps + annotated screenshots.
"""
import os
import json
import sys
import io

import cv2
import numpy as np

from kivy.uix.screenmanager import Screen
from kivy.lang import Builder
from kivy.properties import StringProperty, NumericProperty, ListProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.graphics.texture import Texture
from kivy.clock import Clock

Builder.load_file(os.path.join(os.path.dirname(__file__), "designer_summary.kv"))


# ---------------------------------------------------------------------------
# Action-type colour palette
# ---------------------------------------------------------------------------
ACTION_COLORS = {
    "SINGLE_CLICK":  (0.25, 0.55, 0.95, 1),
    "DOUBLE_CLICK":  (0.55, 0.25, 0.95, 1),
    "SCROLL":        (0.16, 0.75, 0.47, 1),
    "INPUT":         (1.00, 0.65, 0.35, 1),
    "DRAG":          (0.91, 0.30, 0.24, 1),
}
_DEFAULT_COLOR = (0.40, 0.40, 0.60, 1)


def action_color(action_type: str):
    return ACTION_COLORS.get(action_type, _DEFAULT_COLOR)


# ---------------------------------------------------------------------------
# StepRow — one row widget in the left panel list
# ---------------------------------------------------------------------------
class StepRow(BoxLayout):
    """Custom widget for a single step entry in the left list."""
    step_number   = NumericProperty(0)
    action_label  = StringProperty("")
    badge_color   = ListProperty([0.40, 0.40, 0.60, 1])
    is_selected   = ListProperty([0.09, 0.09, 0.18, 1])

    def __init__(self, step, on_select_callback, **kwargs):
        super().__init__(**kwargs)
        self._step = step
        self._on_select_callback = on_select_callback
        self.step_number  = step.step_number
        self.action_label = step.action_type
        r, g, b, a        = action_color(step.action_type)
        self.badge_color   = [r, g, b, a]

    def select(self):
        self.is_selected = [0.15, 0.15, 0.28, 1]

    def deselect(self):
        self.is_selected = [0.09, 0.09, 0.18, 1]

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self._on_select_callback(self)
            return True
        return super().on_touch_down(touch)


# ---------------------------------------------------------------------------
# Main screen
# ---------------------------------------------------------------------------
class DesignerSummaryScreen(Screen):
    SCREEN_NAME = "designer_summary"
    _session_label = StringProperty("—")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._steps = []
        self._step_rows = []
        self._selected_row = None
        self._session_id = None
        self._db_path = None

    def load_session(self, session_id: int, db_path: str):
        """Load a session from DB; safe to call from the main thread."""
        self._session_id = session_id
        self._db_path    = db_path
        self._pending_load = True

    def on_enter(self):
        if getattr(self, '_pending_load', False):
            self._pending_load = False
            Clock.schedule_once(self._populate, 0)

    def _populate(self, _=None):
        """Query the DB and build the left-panel list."""
        try:
            # Import here to avoid circular imports
            db_dir = os.path.abspath(os.path.join(
                os.path.dirname(__file__), '..', '..', 'core', 'database'
            ))
            if db_dir not in sys.path:
                sys.path.insert(0, db_dir)

            from designer_db import DesignerDatabase
            db = DesignerDatabase(self._db_path)
            session_obj = db.get_session(self._session_id)
            self._steps = db.get_steps(self._session_id)
            db.close()

            if session_obj:
                self._session_label = (
                    f"Session: {session_obj.name}  "
                    f"({len(self._steps)} steps)"
                )
        except Exception as ex:
            self._session_label = f"Error loading session: {ex}"
            self._steps = []

        self._build_step_list()

    def _build_step_list(self):
        """Clear and repopulate the ScrollView's list container."""
        container = self.ids.step_list_container
        container.clear_widgets()
        self._step_rows = []
        self._selected_row = None
        self._clear_image()

        for step in self._steps:
            row = StepRow(
                step=step,
                on_select_callback=self._on_step_selected,
                size_hint_y=None,
                height=52
            )
            container.add_widget(row)
            self._step_rows.append(row)

        # Select first step by default if it exists
        if self._step_rows:
            self._on_step_selected(self._step_rows[0])

    def _on_step_selected(self, row: StepRow):
        """Step list item clicked."""
        if self._selected_row and self._selected_row is not row:
            self._selected_row.deselect()

        row.select()
        self._selected_row = row
        self._show_step_image(row._step)

    def _show_step_image(self, step):
        """Decode screenshot bytes, draw overlays with OpenCV, push to Kivy texture."""
        img_bytes = step.screenshot
        if img_bytes is None:
            self._clear_image()
            return

        # Decode PNG bytes → BGR numpy array
        nparr = np.frombuffer(img_bytes, dtype=np.uint8)
        bgr   = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if bgr is None:
            self._clear_image()
            return

        # Draw overlays
        bgr = self._draw_overlays(bgr, step)

        # Convert BGR → RGB (Kivy expects RGB)
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

        # Flip vertically: OpenCV origin is top-left, Kivy is bottom-left
        rgb = cv2.flip(rgb, 0)

        h, w, _ = rgb.shape
        texture  = Texture.create(size=(w, h), colorfmt='rgb')
        texture.blit_buffer(rgb.tobytes(), colorfmt='rgb', bufferfmt='ubyte')

        img_widget = self.ids.step_image
        img_widget.texture = texture
        img_widget.opacity = 1

        # Update OCR and ResNet metadata
        self._update_metadata(step)

    def _update_metadata(self, step):
        """Update OCR and ResNet labels with step metadata."""
        ocr_label = self.ids.ocr_text_label
        resnet_label = self.ids.resnet_label

        # OCR text
        if step.ocr_text:
            ocr_label.text = step.ocr_text[:100]  # Limit to 100 chars
        else:
            ocr_label.text = "[color=888888]—[/color]"

        # ResNet features
        if step.features:
            # Features are stored as bytes, show dimension info
            try:
                features_array = np.frombuffer(step.features, dtype=np.float32)
                resnet_label.text = f"[color=888888]512-dim vector ({len(features_array)} values)[/color]"
            except Exception:
                resnet_label.text = "[color=888888]—[/color]"
        else:
            resnet_label.text = "[color=888888]—[/color]"

    def _draw_overlays(self, bgr: np.ndarray, step) -> np.ndarray:
        """
        Draw on a copy of bgr:
          - A filled circle at click coordinates
          - A coloured rectangle over the bbox
        Returns the annotated array.
        """
        out = bgr.copy()

        # Parse coordinates
        coords = {}
        if step.coordinates:
            try:
                coords = json.loads(step.coordinates)
            except (json.JSONDecodeError, TypeError):
                pass

        # Parse bbox
        bbox = {}
        if step.bbox:
            try:
                bbox = json.loads(step.bbox)
            except (json.JSONDecodeError, TypeError):
                pass

        # --- bbox rectangle ---
        if bbox and all(k in bbox for k in ("x", "y", "w", "h")):
            bx, by, bw, bh = bbox["x"], bbox["y"], bbox["w"], bbox["h"]
            # Rectangle colour: match action type (BGR order for OpenCV)
            rect_color_map = {
                "SINGLE_CLICK":  (242, 140,  64),
                "DOUBLE_CLICK":  (242,  64, 140),
                "SCROLL":        (120, 191,  41),
                "INPUT":         ( 89, 165, 255),
                "DRAG":          ( 61,  77, 232),
            }
            rect_bgr = rect_color_map.get(step.action_type, (180, 100, 100))
            cv2.rectangle(out, (bx, by), (bx + bw, by + bh), rect_bgr, thickness=3)

        # --- click dot / circle ---
        if coords and "x" in coords and "y" in coords:
            cx, cy = int(coords["x"]), int(coords["y"])
            if step.action_type in ("SINGLE_CLICK", "DOUBLE_CLICK", "DRAG"):
                dot_bgr = (50, 205,  50)
            else:
                dot_bgr = (64, 140, 242)

            # Filled circle
            cv2.circle(out, (cx, cy), 12, dot_bgr, thickness=-1)
            # White border for visibility
            cv2.circle(out, (cx, cy), 12, (255, 255, 255), thickness=2)
            # Small centre dot
            cv2.circle(out, (cx, cy),  3, (0, 0, 0),       thickness=-1)

        return out

    def _clear_image(self):
        """Reset the image widget to a blank state."""
        img_widget = self.ids.step_image
        img_widget.texture = None
        img_widget.opacity = 0

    def go_back(self):
        """Navigate back to main screen."""
        self._clear_image()
        self.manager.transition.direction = "right"
        self.manager.current = "main"
