"""
DesignerSummaryScreen — shows recorded steps + annotated screenshots.
"""
import os
import sys
import json
import logging

import cv2
import numpy as np

from kivy.uix.screenmanager import Screen
from kivy.lang import Builder
from kivy.properties import StringProperty, NumericProperty, ListProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.graphics.texture import Texture
from kivy.clock import Clock

# Setup logging
logger = logging.getLogger(__name__)

Builder.load_file(os.path.join(os.path.dirname(__file__), "designer_summary.kv"))


# ---------------------------------------------------------------------------
# Action-type colour palette
# ---------------------------------------------------------------------------
# Red for all actions (matching designer bbox color)
RED_COLOR = (1.0, 0.0, 0.0, 1)

ACTION_COLORS = {
    "SINGLE_CLICK":  RED_COLOR,
    "DOUBLE_CLICK":  RED_COLOR,
    "RIGHT_CLICK":   RED_COLOR,
    "SCROLL":        RED_COLOR,
    "INPUT":         RED_COLOR,
    "DRAG_AND_DROP": RED_COLOR,
}
_DEFAULT_COLOR = RED_COLOR


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
    session_modified = ListProperty([False])  # For KV binding

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._steps = []
        self._step_rows = []
        self._selected_row = None
        self._session_modified = False
        self._modified_steps = set()  # Track which step indices were modified
        self._session_id = None
        self._db_path = None
        self._current_step = None
        self._current_screenshot_bgr = None
        self._bbox_dragging = None
        self._bbox_dragging_is_drag_end = False  # Track which bbox is being dragged
        self._drag_edge_type = None
        self._click_point_dragging = None  # Track if dragging a click point
        self._last_touch_pos = None

        # Initialize OCR and ResNet generators
        from src.app.core.designer._ocr_generator import OCRGenerator
        from src.app.core.designer._feature_generator import FeatureGenerator
        self.ocr_generator = OCRGenerator()
        self.feature_generator = FeatureGenerator()

    @property
    def button_color(self):
        """Button color based on modified state."""
        if self.session_modified and self.session_modified[0]:
            return (0.35, 0.85, 0.95, 1)
        return (0.35, 0.85, 0.95, 0.3)

    @property
    def button_bg_color(self):
        """Button background color based on modified state."""
        if self.session_modified and self.session_modified[0]:
            return (0.35, 0.53, 1.0, 1)
        return (0.35, 0.53, 1.0, 0.3)

    @property
    def button_border_color(self):
        """Button border color based on modified state."""
        if self.session_modified and self.session_modified[0]:
            return (0.50, 0.50, 0.60, 1)
        return (0.50, 0.50, 0.60, 0.3)

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
            from src.app.core.database.designer_db import DesignerDatabase
            db = DesignerDatabase(self._db_path)
            session_obj = db.get_session(self._session_id)
            self._steps = db.get_steps(self._session_id)
            db.close()

            if session_obj:
                self._session_label = (
                    f"Session: {session_obj.name}  "
                    f"({len(self._steps)} steps)"
                )
            else:
                self._session_label = f"Session {self._session_id} not found"
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

        # Find the step in the current list by step number (not using cached row._step)
        step_number = row._step.step_number if row._step else None
        step = None
        for s in self._steps:
            if s.step_number == step_number:
                step = s
                break

        if not step:
            return

        # Log step selection with bbox coordinates
        try:
            bbox = json.loads(step.bbox) if step.bbox else {}
            coords = f"({bbox.get('x', 0)}, {bbox.get('y', 0)}, {bbox.get('w', 0)}, {bbox.get('h', 0)})"

            if step.action_type == "DRAG_AND_DROP":
                drag_end_bbox = json.loads(step.drag_end_bbox) if step.drag_end_bbox else {}
                drag_coords = f"({drag_end_bbox.get('x', 0)}, {drag_end_bbox.get('y', 0)}, {drag_end_bbox.get('w', 0)}, {drag_end_bbox.get('h', 0)})"
                logger.info(f"Step {step.step_number} bbox detected: {coords} -> {drag_coords}")
            else:
                logger.info(f"Step {step.step_number} bbox detected: {coords}")
        except (json.JSONDecodeError, TypeError):
            pass

        self._show_step_image(step)

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

        # Store original screenshot and step for touch handling
        self._current_screenshot_bgr = bgr.copy()
        self._current_step = step
        self._bbox_dragging = None
        self._click_point_dragging = None
        self._drag_edge_type = None

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

        # Bind touch events for bbox manipulation
        img_widget.bind(on_touch_down=self._on_image_touch_down)
        img_widget.bind(on_touch_move=self._on_image_touch_move)
        img_widget.bind(on_touch_up=self._on_image_touch_up)

        # Schedule hover detection for cursor change
        Clock.schedule_interval(self._check_cursor_on_hover, 0.05)

        # Update OCR and ResNet metadata
        self._update_metadata(step)

    def _update_metadata(self, step):
        """Update OCR and ResNet labels with step metadata."""
        ocr_label = self.ids.ocr_text_label
        resnet_label = self.ids.resnet_label

        if step.action_type == "DRAG_AND_DROP":
            # For DRAG_AND_DROP, show both bboxes
            ocr_parts = []
            resnet_parts = []

            # Bbox 1 OCR
            if step.ocr_text:
                ocr_parts.append(f"[b]Bbox 1:[/b] {step.ocr_text[:50]}")
            else:
                ocr_parts.append("[b]Bbox 1:[/b] —")

            # Bbox 2 OCR
            if step.drag_end_ocr_text:
                ocr_parts.append(f"[b]Bbox 2:[/b] {step.drag_end_ocr_text[:50]}")
            else:
                ocr_parts.append("[b]Bbox 2:[/b] —")

            ocr_label.text = "\n".join(ocr_parts)

            # Bbox 1 ResNet
            if step.features:
                try:
                    features_array = np.frombuffer(step.features, dtype=np.float32)
                    resnet_parts.append(f"[b]Bbox 1:[/b] 512-dim ({len(features_array)})")
                except Exception:
                    resnet_parts.append("[b]Bbox 1:[/b] —")
            else:
                resnet_parts.append("[b]Bbox 1:[/b] —")

            # Bbox 2 ResNet
            if step.drag_end_features:
                try:
                    features_array = np.frombuffer(step.drag_end_features, dtype=np.float32)
                    resnet_parts.append(f"[b]Bbox 2:[/b] 512-dim ({len(features_array)})")
                except Exception:
                    resnet_parts.append("[b]Bbox 2:[/b] —")
            else:
                resnet_parts.append("[b]Bbox 2:[/b] —")

            resnet_label.text = "\n".join(resnet_parts)
        else:
            # For single-action steps, show only one bbox
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

    def _draw_overlays(self, bgr: np.ndarray, step, override_bbox=None) -> np.ndarray:
        """
        Draw on a copy of bgr with colored overlays:
        - Single actions: red bbox, colored dots
        - DRAG_AND_DROP: red start bbox, violet end bbox
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

        # Parse bbox (or use override if provided)
        bbox = override_bbox if override_bbox is not None else {}
        if not override_bbox and step.bbox:
            try:
                bbox = json.loads(step.bbox)
            except (json.JSONDecodeError, TypeError):
                pass

        # Color scheme:
        # Single actions: red rect, custom green click dot
        # DRAG_AND_DROP: red start, violet end
        if step.action_type == "DRAG_AND_DROP":
            rect_bgr = (0, 0, 255)  # Red for start bbox
            dot_bgr = (120, 200, 80)   # Custom green for start click
        else:
            rect_bgr = (0, 0, 255)  # Red for all single actions
            dot_bgr = (120, 200, 80)   # Custom green for all single action clicks

        # --- DRAG_AND_DROP: 2 bbox + 2 circles ---
        if step.action_type == "DRAG_AND_DROP":
            # First bbox (start point) - RED
            if bbox and all(k in bbox for k in ("x", "y", "w", "h")):
                bx, by, bw, bh = bbox["x"], bbox["y"], bbox["w"], bbox["h"]
                cv2.rectangle(out, (bx, by), (bx + bw, by + bh), (0, 0, 255), thickness=3)

            # Second bbox (end point) - VIOLET/PURPLE
            drag_end_bbox = {}
            if step.drag_end_bbox:
                try:
                    drag_end_bbox = json.loads(step.drag_end_bbox)
                except (json.JSONDecodeError, TypeError):
                    pass

            if drag_end_bbox and all(k in drag_end_bbox for k in ("x", "y", "w", "h")):
                bx2, by2, bw2, bh2 = drag_end_bbox["x"], drag_end_bbox["y"], drag_end_bbox["w"], drag_end_bbox["h"]
                cv2.rectangle(out, (bx2, by2), (bx2 + bw2, by2 + bh2), (200, 0, 150), thickness=3)

            # Start circle - GREEN
            if coords and "x" in coords and "y" in coords:
                cx, cy = int(coords["x"]), int(coords["y"])
                cv2.circle(out, (cx, cy), 8, (120, 200, 80), thickness=-1)
                cv2.circle(out, (cx, cy), 8, (255, 255, 255), thickness=2)
                cv2.circle(out, (cx, cy), 3, (0, 0, 0), thickness=-1)

            # End circle - YELLOW/ORANGE
            drag_end_coords = {}
            if step.drag_end_coordinates:
                try:
                    drag_end_coords = json.loads(step.drag_end_coordinates)
                except (json.JSONDecodeError, TypeError):
                    pass

            if drag_end_coords and "x" in drag_end_coords and "y" in drag_end_coords:
                cx2, cy2 = int(drag_end_coords["x"]), int(drag_end_coords["y"])
                cv2.circle(out, (cx2, cy2), 8, (0, 200, 255), thickness=-1)
                cv2.circle(out, (cx2, cy2), 8, (255, 255, 255), thickness=2)
                cv2.circle(out, (cx2, cy2), 3, (0, 0, 0), thickness=-1)

        # --- Regular click: 1 bbox + 1 circle ---
        else:
            # --- bbox rectangle ---
            if bbox and all(k in bbox for k in ("x", "y", "w", "h")):
                bx, by, bw, bh = bbox["x"], bbox["y"], bbox["w"], bbox["h"]
                cv2.rectangle(out, (bx, by), (bx + bw, by + bh), rect_bgr, thickness=3)

            # --- click dot / circle ---
            if coords and "x" in coords and "y" in coords:
                cx, cy = int(coords["x"]), int(coords["y"])
                cv2.circle(out, (cx, cy), 8, dot_bgr, thickness=-1)
                cv2.circle(out, (cx, cy), 8, (255, 255, 255), thickness=2)
                cv2.circle(out, (cx, cy), 3, (0, 0, 0), thickness=-1)

        return out

    def _clear_image(self):
        """Reset the image widget to a blank state."""
        img_widget = self.ids.step_image
        img_widget.texture = None
        img_widget.opacity = 0

    # ==================== CURSOR HOVER DETECTION ====================

    def _check_cursor_on_hover(self, _):
        """Check if cursor is over bbox and change cursor accordingly."""
        from kivy.core.window import Window

        if not self._current_step or self._current_screenshot_bgr is None:
            return True

        # Get mouse position
        mouse_x, mouse_y = Window.mouse_pos
        img_widget = self.ids.step_image

        # Check if mouse is within image bounds
        if not img_widget.collide_point(mouse_x, mouse_y):
            Window.set_system_cursor('arrow')
            return True

        # Convert mouse position to image coordinates
        img_x, img_y = self._widget_to_image_coords(mouse_x, mouse_y, img_widget)

        # If outside rendered image area, use default cursor
        if img_x < 0 or img_y < 0:
            Window.set_system_cursor('arrow')
            return True

        # Parse bbox
        bbox = None
        if self._current_step.bbox:
            try:
                bbox = json.loads(self._current_step.bbox)
            except (json.JSONDecodeError, TypeError):
                pass

        if bbox:
            # Check if mouse is over bbox (use larger threshold for hover)
            edge_type = self._detect_bbox_edge(img_x, img_y, bbox, threshold=20)
            if edge_type:
                # Change cursor based on edge type
                # Note: Only 'hand' and 'arrow' seem to work in Kivy
                cursor = 'hand' if edge_type else 'arrow'
                Window.set_system_cursor(cursor)
                return True

        # Default cursor
        Window.set_system_cursor('arrow')
        return True

    # ==================== COORDINATE CONVERSION (fit_mode: "contain") ====================

    def _get_image_rect_on_widget(self, widget):
        """Calculate actual position and size of image on widget (fit_mode: contain, centered)."""
        if self._current_screenshot_bgr is None:
            return 0, 0, widget.width, widget.height

        img_h, img_w = self._current_screenshot_bgr.shape[:2]

        # Calculate which dimension limits the fit
        img_aspect = img_w / img_h if img_h > 0 else 1
        widget_aspect = widget.width / widget.height if widget.height > 0 else 1

        if img_aspect > widget_aspect:
            # Image wider than widget aspect - fit by width
            rendered_width = widget.width
            rendered_height = widget.width / img_aspect
        else:
            # Image taller - fit by height
            rendered_height = widget.height
            rendered_width = rendered_height * img_aspect

        # Center the image (pos_hint: center_x/center_y)
        x_offset = (widget.width - rendered_width) / 2
        y_offset = (widget.height - rendered_height) / 2

        return x_offset, y_offset, rendered_width, rendered_height

    def _widget_to_image_coords(self, widget_x, widget_y, widget):
        """Convert screen touch coordinates to image coordinates."""
        x_offset, y_offset, rendered_width, rendered_height = self._get_image_rect_on_widget(widget)

        if self._current_screenshot_bgr is None:
            return 0, 0

        img_h, img_w = self._current_screenshot_bgr.shape[:2]

        # Convert from screen absolute coordinates to widget-relative coordinates
        widget_local_x = widget_x - widget.x
        widget_local_y = widget_y - widget.y

        # Remove the image offset inside the widget
        local_x = widget_local_x - x_offset
        local_y = widget_local_y - y_offset

        # Check if within rendered image bounds (not in offset areas)
        if local_x < 0 or local_x > rendered_width or local_y < 0 or local_y > rendered_height:
            # Outside rendered image area
            return -1, -1

        # Scale to image space
        img_x = (local_x / rendered_width) * img_w if rendered_width > 0 else 0
        img_y = img_h - (local_y / rendered_height) * img_h if rendered_height > 0 else 0

        return img_x, img_y

    # ==================== TOUCH HANDLING FOR BBOX MANIPULATION ====================

    def _on_image_touch_down(self, widget, touch):
        """Handle touch down on image - detect if clicking on a bbox."""
        if not self._current_step or self._current_screenshot_bgr is None:
            return False

        # Ignore scroll events
        if touch.button in ('scrollup', 'scrolldown', 'scrollleft', 'scrollright'):
            return False

        # Check if touch is within image bounds
        if not widget.collide_point(*touch.pos):
            return False

        # Convert touch position to image coordinates (accounting for fit_mode: contain)
        img_x, img_y = self._widget_to_image_coords(touch.x, touch.y, widget)

        # Check both bboxes and click points, select the closest one
        best_match = None
        best_distance = float('inf')

        # Check main click point
        if self._current_step.coordinates:
            try:
                coords = json.loads(self._current_step.coordinates)
                if coords and 'x' in coords and 'y' in coords:
                    click_x, click_y = coords['x'], coords['y']
                    distance = ((img_x - click_x) ** 2 + (img_y - click_y) ** 2) ** 0.5
                    if distance < 20:  # 20 pixel tolerance for click point
                        if distance < best_distance:
                            best_distance = distance
                            best_match = ('click_point', False, None)
            except (json.JSONDecodeError, TypeError):
                pass

        # Check drag_end click point
        if self._current_step.drag_end_coordinates:
            try:
                coords = json.loads(self._current_step.drag_end_coordinates)
                if coords and 'x' in coords and 'y' in coords:
                    click_x, click_y = coords['x'], coords['y']
                    distance = ((img_x - click_x) ** 2 + (img_y - click_y) ** 2) ** 0.5
                    if distance < 20:  # 20 pixel tolerance for click point
                        if distance < best_distance:
                            best_distance = distance
                            best_match = ('click_point', True, None)
            except (json.JSONDecodeError, TypeError):
                pass

        # Check main bbox
        if self._current_step.bbox:
            try:
                bbox = json.loads(self._current_step.bbox)
                if bbox and 'x' in bbox and 'y' in bbox:
                    edge_type = self._detect_bbox_edge(img_x, img_y, bbox)
                    if edge_type:
                        # Calculate distance to bbox edge
                        distance = self._distance_to_bbox_edge(img_x, img_y, bbox, edge_type)
                        if distance < best_distance:
                            best_distance = distance
                            best_match = (bbox, False, edge_type)
            except (json.JSONDecodeError, TypeError):
                pass

        # Check drag_end_bbox
        if self._current_step.drag_end_bbox:
            try:
                bbox = json.loads(self._current_step.drag_end_bbox)
                if bbox and 'x' in bbox and 'y' in bbox:
                    edge_type = self._detect_bbox_edge(img_x, img_y, bbox)
                    if edge_type:
                        # Calculate distance to bbox edge
                        distance = self._distance_to_bbox_edge(img_x, img_y, bbox, edge_type)
                        if distance < best_distance:
                            best_distance = distance
                            best_match = (bbox, True, edge_type)
            except (json.JSONDecodeError, TypeError):
                pass

        # Use the closest match
        if best_match:
            match_type, is_drag_end, edge_type = best_match
            if match_type == 'click_point':
                self._click_point_dragging = is_drag_end
                self._last_touch_pos = touch.pos
                return True
            else:
                bbox = best_match[0]
                self._bbox_dragging = bbox
                self._bbox_dragging_is_drag_end = is_drag_end
                self._drag_edge_type = edge_type
                self._last_touch_pos = touch.pos
                return True

        return False

    def _distance_to_bbox_edge(self, img_x, img_y, bbox, edge_type):
        """Calculate distance from point to bbox edge."""
        x, y, w, h = bbox['x'], bbox['y'], bbox['w'], bbox['h']

        if edge_type in ('tl', 'tr', 'bl', 'br'):
            # Corner - distance to corner point
            if edge_type == 'tl':
                cx, cy = x, y
            elif edge_type == 'tr':
                cx, cy = x + w, y
            elif edge_type == 'bl':
                cx, cy = x, y + h
            else:  # br
                cx, cy = x + w, y + h
            return ((img_x - cx) ** 2 + (img_y - cy) ** 2) ** 0.5

        elif edge_type in ('l', 'r', 't', 'b'):
            # Edge - distance to edge line
            if edge_type == 'l':
                return abs(img_x - x)
            elif edge_type == 'r':
                return abs(img_x - (x + w))
            elif edge_type == 't':
                return abs(img_y - y)
            else:  # b
                return abs(img_y - (y + h))

        else:  # move
            # Center - distance to center
            cx, cy = x + w / 2, y + h / 2
            return ((img_x - cx) ** 2 + (img_y - cy) ** 2) ** 0.5

    def _on_image_touch_move(self, widget, touch):
        """Handle touch move - drag bbox or click point."""
        if not self._last_touch_pos:
            return False

        if self._current_screenshot_bgr is None:
            return False

        # Get current and previous position in image coordinates
        curr_img_x, curr_img_y = self._widget_to_image_coords(touch.x, touch.y, widget)
        prev_img_x, prev_img_y = self._widget_to_image_coords(self._last_touch_pos[0], self._last_touch_pos[1], widget)

        # Handle click point drag
        if hasattr(self, '_click_point_dragging') and self._click_point_dragging is not None:
            if self._current_step:
                # Clamp to image bounds
                curr_img_x = max(0, min(curr_img_x, self._current_screenshot_bgr.shape[1]))
                curr_img_y = max(0, min(curr_img_y, self._current_screenshot_bgr.shape[0]))

                if self._click_point_dragging:
                    # Drag end click point
                    coords = json.loads(self._current_step.drag_end_coordinates) if self._current_step.drag_end_coordinates else {}
                    coords['x'] = int(curr_img_x)
                    coords['y'] = int(curr_img_y)
                    self._current_step.drag_end_coordinates = json.dumps(coords)
                else:
                    # Drag main click point
                    coords = json.loads(self._current_step.coordinates) if self._current_step.coordinates else {}
                    coords['x'] = int(curr_img_x)
                    coords['y'] = int(curr_img_y)
                    self._current_step.coordinates = json.dumps(coords)

                self._redraw_image_with_modified_bbox()
                self._last_touch_pos = touch.pos
                return True

        # Handle bbox drag
        if self._bbox_dragging and not self._last_touch_pos:
            return False

        if self._bbox_dragging:
            dx = curr_img_x - prev_img_x
            dy = curr_img_y - prev_img_y
            self._apply_bbox_drag(dx, dy, widget)
            self._last_touch_pos = touch.pos
            self._redraw_image_with_modified_bbox()
            return True

        return False

    def _on_image_touch_up(self, widget, touch):
        """Handle touch up - finalize drag."""
        # Finalize click point drag
        if hasattr(self, '_click_point_dragging') and self._click_point_dragging is not None and self._current_step:
            self._modified_steps.add(self._current_step)
            self._click_point_dragging = None
            return True

        # Save the modified bbox back to current_step
        if self._bbox_dragging and self._current_step:
            bbox = self._bbox_dragging
            bbox_num = 2 if self._bbox_dragging_is_drag_end else 1
            action_type = "moved" if self._drag_edge_type == 'move' else "resized"

            if self._bbox_dragging_is_drag_end:
                self._current_step.drag_end_bbox = json.dumps(self._bbox_dragging)
            else:
                self._current_step.bbox = json.dumps(self._bbox_dragging)

            logger.info(f"Bbox {bbox_num} {action_type}: ({bbox['x']}, {bbox['y']}, {bbox['w']}, {bbox['h']})")

            # Mark session as modified
            self._session_modified = True
            self.session_modified = [True]
            # Find step index by step number instead of object identity
            # (object identity changes after DB reload)
            if self._current_step:
                self._modified_steps.add(self._current_step)

        self._bbox_dragging = None
        self._bbox_dragging_is_drag_end = False
        self._click_point_dragging = None
        self._drag_edge_type = None
        self._last_touch_pos = None

        # Redraw to show final bbox positions
        if self._current_screenshot_bgr is not None and self._current_step:
            bgr = self._draw_overlays(self._current_screenshot_bgr.copy(), self._current_step)
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            rgb = cv2.flip(rgb, 0)
            h, w, _ = rgb.shape
            texture = Texture.create(size=(w, h), colorfmt='rgb')
            texture.blit_buffer(rgb.tobytes(), colorfmt='rgb', bufferfmt='ubyte')
            img_widget = self.ids.step_image
            img_widget.texture = texture

        return True

    def _detect_bbox_edge(self, img_x, img_y, bbox, threshold=10):
        """Detect which edge/corner of bbox is being touched."""
        x, y, w, h = bbox['x'], bbox['y'], bbox['w'], bbox['h']

        # Check corners first
        if abs(img_x - x) < threshold and abs(img_y - y) < threshold:
            return 'tl'  # top-left
        if abs(img_x - (x + w)) < threshold and abs(img_y - y) < threshold:
            return 'tr'  # top-right
        if abs(img_x - x) < threshold and abs(img_y - (y + h)) < threshold:
            return 'bl'  # bottom-left
        if abs(img_x - (x + w)) < threshold and abs(img_y - (y + h)) < threshold:
            return 'br'  # bottom-right

        # Check edges
        if abs(img_x - x) < threshold and y <= img_y <= y + h:
            return 'l'  # left
        if abs(img_x - (x + w)) < threshold and y <= img_y <= y + h:
            return 'r'  # right
        if abs(img_y - y) < threshold and x <= img_x <= x + w:
            return 't'  # top
        if abs(img_y - (y + h)) < threshold and x <= img_x <= x + w:
            return 'b'  # bottom

        # Check if within bbox (move)
        if x <= img_x <= x + w and y <= img_y <= y + h:
            return 'move'

        return None

    def _apply_bbox_drag(self, dx, dy, widget):
        """Apply drag operation to bbox."""
        if not self._bbox_dragging:
            return

        if self._current_screenshot_bgr is None:
            return

        img_h, img_w = self._current_screenshot_bgr.shape[:2]
        bbox = self._bbox_dragging
        dx = int(dx)
        dy = int(dy)

        # Clamp dx, dy BEFORE applying to keep bbox attached to edges
        if self._drag_edge_type == 'move':
            # Clamp movement within image bounds
            if bbox['x'] + dx < 0:
                dx = -bbox['x']
            if bbox['x'] + dx + bbox['w'] > img_w:
                dx = img_w - bbox['x'] - bbox['w']
            if bbox['y'] + dy < 0:
                dy = -bbox['y']
            if bbox['y'] + dy + bbox['h'] > img_h:
                dy = img_h - bbox['y'] - bbox['h']

            bbox['x'] += dx
            bbox['y'] += dy

        elif self._drag_edge_type == 'tl':
            # Clamp so x doesn't go below 0 and w stays >= 10
            if bbox['x'] + dx < 0:
                dx = -bbox['x']
            if bbox['w'] - dx < 10:
                dx = bbox['w'] - 10
            # Clamp so y doesn't go below 0 and h stays >= 10
            if bbox['y'] + dy < 0:
                dy = -bbox['y']
            if bbox['h'] - dy < 10:
                dy = bbox['h'] - 10

            bbox['x'] += dx
            bbox['y'] += dy
            bbox['w'] -= dx
            bbox['h'] -= dy

        elif self._drag_edge_type == 'tr':
            # Clamp so x + w doesn't exceed img_w and w stays >= 10
            if bbox['x'] + bbox['w'] + dx > img_w:
                dx = img_w - bbox['x'] - bbox['w']
            # If already at right limit, don't shrink
            if bbox['x'] + bbox['w'] >= img_w and dx < 0:
                dx = 0
            if bbox['w'] + dx < 10:
                dx = 10 - bbox['w']
            # Clamp so y doesn't go below 0 and h stays >= 10
            if bbox['y'] + dy < 0:
                dy = -bbox['y']
            if bbox['h'] - dy < 10:
                dy = bbox['h'] - 10

            bbox['y'] += dy
            bbox['w'] += dx
            bbox['h'] -= dy

        elif self._drag_edge_type == 'bl':
            # Clamp so x doesn't go below 0 and w stays >= 10
            if bbox['x'] + dx < 0:
                dx = -bbox['x']
            # If already at left limit, don't shrink
            if bbox['x'] <= 0 and dx > 0:
                dx = 0
            if bbox['w'] - dx < 10:
                dx = bbox['w'] - 10
            # Clamp so y + h doesn't exceed img_h and h stays >= 10
            if bbox['y'] + bbox['h'] + dy > img_h:
                dy = img_h - bbox['y'] - bbox['h']
            # If already at bottom limit, don't shrink
            if bbox['y'] + bbox['h'] >= img_h and dy < 0:
                dy = 0
            if bbox['h'] + dy < 10:
                dy = 10 - bbox['h']

            bbox['x'] += dx
            bbox['w'] -= dx
            bbox['h'] += dy

        elif self._drag_edge_type == 'br':
            # Clamp so x + w doesn't exceed img_w and w stays >= 10
            if bbox['x'] + bbox['w'] + dx > img_w:
                dx = img_w - bbox['x'] - bbox['w']
            # If already at right limit, don't shrink
            if bbox['x'] + bbox['w'] >= img_w and dx < 0:
                dx = 0
            if bbox['w'] + dx < 10:
                dx = 10 - bbox['w']
            # Clamp so y + h doesn't exceed img_h and h stays >= 10
            if bbox['y'] + bbox['h'] + dy > img_h:
                dy = img_h - bbox['y'] - bbox['h']
            # If already at bottom limit, don't shrink
            if bbox['y'] + bbox['h'] >= img_h and dy < 0:
                dy = 0
            if bbox['h'] + dy < 10:
                dy = 10 - bbox['h']

            bbox['w'] += dx
            bbox['h'] += dy

        elif self._drag_edge_type == 'l':
            # Clamp so x doesn't go below 0 and w stays >= 10
            if bbox['x'] + dx < 0:
                dx = -bbox['x']
            if bbox['w'] - dx < 10:
                dx = bbox['w'] - 10

            bbox['x'] += dx
            bbox['w'] -= dx

        elif self._drag_edge_type == 'r':
            # Clamp so x + w doesn't exceed img_w and w stays >= 10
            if bbox['x'] + bbox['w'] + dx > img_w:
                dx = img_w - bbox['x'] - bbox['w']
            # If already at right limit, don't shrink
            if bbox['x'] + bbox['w'] >= img_w and dx < 0:
                dx = 0
            if bbox['w'] + dx < 10:
                dx = 10 - bbox['w']

            bbox['w'] += dx

        elif self._drag_edge_type == 't':
            # Clamp so y doesn't go below 0 and h stays >= 10
            if bbox['y'] + dy < 0:
                dy = -bbox['y']
            if bbox['h'] - dy < 10:
                dy = bbox['h'] - 10

            bbox['y'] += dy
            bbox['h'] -= dy

        elif self._drag_edge_type == 'b':
            # Clamp so y + h doesn't exceed img_h and h stays >= 10
            if bbox['y'] + bbox['h'] + dy > img_h:
                dy = img_h - bbox['y'] - bbox['h']
            # If already at bottom limit, don't shrink
            if bbox['y'] + bbox['h'] >= img_h and dy < 0:
                dy = 0
            if bbox['h'] + dy < 10:
                dy = 10 - bbox['h']

            bbox['h'] += dy

    def _redraw_image_with_modified_bbox(self):
        """Redraw the image with the modified bbox."""
        if self._current_screenshot_bgr is None or not self._current_step:
            return

        # Create a temporary step with both bboxes updated
        temp_step = self._current_step
        if self._bbox_dragging:
            # Update the appropriate bbox in the step
            if self._bbox_dragging_is_drag_end:
                temp_step.drag_end_bbox = json.dumps(self._bbox_dragging)
            else:
                temp_step.bbox = json.dumps(self._bbox_dragging)

        bgr = self._draw_overlays(self._current_screenshot_bgr.copy(), temp_step)

        # Convert and display
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        rgb = cv2.flip(rgb, 0)

        h, w, _ = rgb.shape
        texture = Texture.create(size=(w, h), colorfmt='rgb')
        texture.blit_buffer(rgb.tobytes(), colorfmt='rgb', bufferfmt='ubyte')

        img_widget = self.ids.step_image
        img_widget.texture = texture

    def save_session(self):
        """Save modified bboxes: recalculate OCR and ResNet, save to DB."""
        if not self._session_modified or not self._steps:
            return

        logger.info("Saving modified steps...")
        import subprocess
        import tempfile

        # Recalculate OCR and ResNet for modified steps
        for step in self._modified_steps:
            logger.debug(f"Processing step index {step.step_number}")

            # Decode screenshot to temp file
            img_bytes = step.screenshot
            if img_bytes is None:
                continue

            nparr = np.frombuffer(img_bytes, dtype=np.uint8)
            bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if bgr is None:
                continue

            # Save screenshot to temp file
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                cv2.imwrite(tmp.name, bgr)
                temp_screenshot_path = tmp.name

            try:
                # Process main bbox
                if step.bbox:
                    try:
                        bbox = json.loads(step.bbox)
                        if bbox and 'x' in bbox:
                            # Launch OCR/ResNet worker process
                            worker_path = os.path.join(os.path.dirname(__file__), '..', '..', 'core', 'designer', '_ocr_feature_update.py')
                            try:
                                # Use temp files instead of pipe (capture_output=True) to avoid easyocr crash
                                import tempfile
                                with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt') as stdout_file:
                                    stdout_path = stdout_file.name
                                with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt') as stderr_file:
                                    stderr_path = stderr_file.name

                                try:
                                    with open(stdout_path, 'w') as stdout_f, open(stderr_path, 'w') as stderr_f:
                                        result = subprocess.run(
                                            [sys.executable, worker_path, temp_screenshot_path, step.bbox],
                                            stdout=stdout_f,
                                            stderr=stderr_f,
                                            timeout=600  # 10 minutes for model download on first run
                                        )

                                    # Read output from files
                                    with open(stdout_path, 'r') as f:
                                        stdout_content = f.read()
                                    with open(stderr_path, 'r') as f:
                                        stderr_content = f.read()

                                    # Clean up temp files
                                    os.unlink(stdout_path)
                                    os.unlink(stderr_path)

                                    if result.returncode == 0 and stdout_content:
                                        try:
                                            # Find the first { to skip any logs before JSON
                                            json_start = stdout_content.find('{')
                                            if json_start >= 0:
                                                json_str = stdout_content[json_start:]
                                                output = json.loads(json_str)
                                            else:
                                                logger.error(f"No JSON found in worker output: {stdout_content[:200]}")
                                                output = {"error": "No JSON in worker output"}
                                        except json.JSONDecodeError as e:
                                            logger.error(f"JSON parse error from worker: {e}, stdout: {stdout_content[:200]}")
                                            output = {"error": "Invalid JSON from worker"}

                                        if "error" not in output:
                                            step.ocr_text = output.get("ocr_text", "")
                                            # Convert hex string back to bytes
                                            features_hex = output.get("features")
                                            step.features = bytes.fromhex(features_hex) if isinstance(features_hex, str) else features_hex
                                            logger.info(f"Step {step.step_number} bbox 1: OCR/ResNet updated")
                                        else:
                                            logger.warning(f"Step {step.step_number} bbox 1 error: {output['error']}")
                                    else:
                                        logger.error(f"Worker failed with returncode {result.returncode}")
                                        logger.error(f"Worker stderr: {stderr_content[:500]}")
                                        logger.error(f"Worker stdout: {stdout_content[:500]}")
                                finally:
                                    try:
                                        os.unlink(stdout_path)
                                        os.unlink(stderr_path)
                                    except:
                                        pass

                            except subprocess.TimeoutExpired:
                                logger.error(f"Worker timeout (>600s) - model download issue?")
                            except Exception as e:
                                logger.error(f"Worker subprocess error: {e}")
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.error(f"Error processing step {step.step_number}: {e}")

                # Process drag_end_bbox if DRAG_AND_DROP
                if step.action_type == "DRAG_AND_DROP" and step.drag_end_bbox:
                    try:
                        bbox = json.loads(step.drag_end_bbox)
                        if bbox and 'x' in bbox:
                            # Launch OCR/ResNet worker process
                            worker_path = os.path.join(os.path.dirname(__file__), '..', '..', 'core', 'designer', '_ocr_feature_update.py')
                            try:
                                # Use temp files instead of pipe (capture_output=True) to avoid easyocr crash
                                import tempfile
                                with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt') as stdout_file:
                                    stdout_path = stdout_file.name
                                with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt') as stderr_file:
                                    stderr_path = stderr_file.name

                                try:
                                    with open(stdout_path, 'w') as stdout_f, open(stderr_path, 'w') as stderr_f:
                                        result = subprocess.run(
                                            [sys.executable, worker_path, temp_screenshot_path, step.drag_end_bbox],
                                            stdout=stdout_f,
                                            stderr=stderr_f,
                                            timeout=30
                                        )

                                    # Read output from files
                                    with open(stdout_path, 'r') as f:
                                        stdout_content = f.read()
                                    with open(stderr_path, 'r') as f:
                                        stderr_content = f.read()

                                    # Clean up temp files
                                    os.unlink(stdout_path)
                                    os.unlink(stderr_path)

                                    if result.returncode == 0 and stdout_content:
                                        try:
                                            # Find the first { to skip any logs before JSON
                                            json_start = stdout_content.find('{')
                                            if json_start >= 0:
                                                json_str = stdout_content[json_start:]
                                                output = json.loads(json_str)
                                            else:
                                                logger.error(f"No JSON found in worker output: {stdout_content[:200]}")
                                                output = {"error": "No JSON in worker output"}
                                        except json.JSONDecodeError as e:
                                            logger.error(f"JSON parse error from worker: {e}, stdout: {stdout_content[:200]}")
                                            output = {"error": "Invalid JSON from worker"}

                                        if "error" not in output:
                                            step.drag_end_ocr_text = output.get("ocr_text", "")
                                            # Convert hex string back to bytes
                                            features_hex = output.get("features")
                                            step.drag_end_features = bytes.fromhex(features_hex) if isinstance(features_hex, str) else features_hex
                                            logger.info(f"Step {step.step_number} bbox 2: OCR/ResNet updated")
                                        else:
                                            logger.warning(f"Step {step.step_number} bbox 2 error: {output['error']}")
                                    else:
                                        logger.error(f"Worker failed with returncode {result.returncode}")
                                        logger.error(f"Worker stderr: {stderr_content[:500]}")
                                        logger.error(f"Worker stdout: {stdout_content[:500]}")
                                finally:
                                    try:
                                        os.unlink(stdout_path)
                                        os.unlink(stderr_path)
                                    except:
                                        pass
                            except subprocess.TimeoutExpired:
                                logger.error(f"Worker timeout (>30s)")
                            except Exception as e:
                                logger.error(f"Worker subprocess error: {e}")
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.error(f"Error processing step {step.step_number}: {e}")
            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_screenshot_path)
                except:
                    pass

        # Save all steps to DB
        try:
            from src.app.core.database.designer_db import DesignerDatabase
            db = DesignerDatabase(self._db_path)
            for step in self._steps:
                db.update_step(self._session_id, step)
            db.close()
            logger.info("Session saved to database")

            # Reload steps from DB to avoid SQLAlchemy detached instance errors
            # Remember which step was being viewed
            current_step_number = self._current_step.step_number if self._current_step else None

            db = DesignerDatabase(self._db_path)
            self._steps = db.get_steps(self._session_id)
            db.close()

            # Find and restore the current step
            if current_step_number is not None:
                for step in self._steps:
                    if step.step_number == current_step_number:
                        self._current_step = step
                        # Redraw the image with updated features
                        self._show_step_image(step)
                        break
            else:
                self._current_step = self._steps[0] if self._steps else None
        except Exception as e:
            logger.error(f"Error saving to database: {e}")

        # Reset modified state
        self._session_modified = False
        self.session_modified = [False]
        self._modified_steps.clear()

    def go_back(self):
        """Navigate back to main screen."""
        self._clear_image()
        self.manager.transition.direction = "right"
        self.manager.current = "main"
