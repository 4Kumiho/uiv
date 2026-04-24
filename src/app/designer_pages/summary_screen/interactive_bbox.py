"""Interactive bbox widget for editing bounding boxes on screenshots."""

import json
import numpy as np
from kivy.uix.image import Image
from kivy.uix.floatlayout import FloatLayout
from kivy.graphics import Line, Color
from kivy.properties import ObjectProperty, ListProperty, BooleanProperty
from kivy.core.window import Window


class BBoxRect:
    """Represents an editable bounding box."""
    def __init__(self, x, y, w, h, bbox_id=0):
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.id = bbox_id
        self.is_selected = False

    def contains_point(self, px, py):
        """Check if point is inside bbox."""
        return (self.x <= px <= self.x + self.w and
                self.y <= py <= self.y + self.h)

    def get_edge_type(self, px, py, threshold=10):
        """Detect which edge/corner is being dragged."""
        # Corners
        if abs(px - self.x) < threshold and abs(py - self.y) < threshold:
            return 'tl'  # top-left
        if abs(px - (self.x + self.w)) < threshold and abs(py - self.y) < threshold:
            return 'tr'  # top-right
        if abs(px - self.x) < threshold and abs(py - (self.y + self.h)) < threshold:
            return 'bl'  # bottom-left
        if abs(px - (self.x + self.w)) < threshold and abs(py - (self.y + self.h)) < threshold:
            return 'br'  # bottom-right

        # Edges
        if abs(px - self.x) < threshold and self.y <= py <= self.y + self.h:
            return 'l'  # left
        if abs(px - (self.x + self.w)) < threshold and self.y <= py <= self.y + self.h:
            return 'r'  # right
        if abs(py - self.y) < threshold and self.x <= px <= self.x + self.w:
            return 't'  # top
        if abs(py - (self.y + self.h)) < threshold and self.x <= px <= self.x + self.w:
            return 'b'  # bottom

        # Center (move)
        if self.contains_point(px, py):
            return 'move'

        return None

    def apply_drag(self, edge_type, dx, dy):
        """Apply drag operation to bbox."""
        if edge_type == 'move':
            self.x += dx
            self.y += dy
        elif edge_type == 'tl':
            self.x += dx
            self.y += dy
            self.w -= dx
            self.h -= dy
        elif edge_type == 'tr':
            self.y += dy
            self.w += dx
            self.h -= dy
        elif edge_type == 'bl':
            self.x += dx
            self.w -= dx
            self.h += dy
        elif edge_type == 'br':
            self.w += dx
            self.h += dy
        elif edge_type == 'l':
            self.x += dx
            self.w -= dx
        elif edge_type == 'r':
            self.w += dx
        elif edge_type == 't':
            self.y += dy
            self.h -= dy
        elif edge_type == 'b':
            self.h += dy

        # Clamp to minimum size
        if self.w < 10:
            self.w = 10
        if self.h < 10:
            self.h = 10

    def to_dict(self):
        """Convert to dict for storage."""
        return {
            "x": int(self.x),
            "y": int(self.y),
            "w": int(self.w),
            "h": int(self.h)
        }


class InteractiveBBoxWidget(FloatLayout):
    """Widget that displays an image with interactive bboxes."""

    has_modifications = BooleanProperty(False)

    def __init__(self, screenshot_rgb, bboxes_list, **kwargs):
        super().__init__(**kwargs)
        self.screenshot_rgb = screenshot_rgb
        self.bboxes = [BBoxRect(b['x'], b['y'], b['w'], b['h'], i)
                       for i, b in enumerate(bboxes_list)]

        self.dragging_bbox = None
        self.drag_edge_type = None
        self.last_touch = None

        # Store original state for undo
        self.original_bboxes = [BBoxRect(b.x, b.y, b.w, b.h, b.id) for b in self.bboxes]

        # Draw the image
        self._create_image()
        self.bind(size=self._on_size)

    def _create_image(self):
        """Create and display the screenshot image."""
        h, w = self.screenshot_rgb.shape[:2]
        from kivy.graphics.texture import Texture
        texture = Texture.create(size=(w, h), colorfmt='rgb')
        texture.blit_buffer(self.screenshot_rgb.tobytes(), colorfmt='rgb', bufferfmt='ubyte')

        self.img = Image(texture=texture, size_hint=(1, 1))
        self.add_widget(self.img)

    def _on_size(self, *args):
        """Redraw when size changes."""
        self._redraw_bboxes()

    def _redraw_bboxes(self):
        """Redraw bbox rectangles."""
        self.canvas.after.clear()

        if not self.bboxes:
            return

        # Get scaling factors
        img_h, img_w = self.screenshot_rgb.shape[:2]
        scale_x = self.width / img_w if img_w > 0 else 1
        scale_y = self.height / img_h if img_h > 0 else 1

        with self.canvas.after:
            for bbox in self.bboxes:
                # Calculate screen coordinates
                sx = bbox.x * scale_x
                sy = self.height - (bbox.y + bbox.h) * scale_y
                sw = bbox.w * scale_x
                sh = bbox.h * scale_y

                # Draw rectangle
                color = (0, 1, 0, 1) if bbox.is_selected else (1, 0, 0, 0.7)
                Color(*color)
                Line(rectangle=(sx, sy, sw, sh), width=2)

                # Draw corner handles if selected
                if bbox.is_selected:
                    Color(1, 1, 0, 1)
                    handle_size = 8
                    # TL, TR, BL, BR
                    for hx, hy in [(sx, sy + sh), (sx + sw, sy + sh),
                                    (sx, sy), (sx + sw, sy)]:
                        Line(rectangle=(hx - handle_size/2, hy - handle_size/2,
                                       handle_size, handle_size), width=1)

    def on_touch_down(self, touch):
        """Handle touch down."""
        if not self.collide_point(*touch.pos):
            return False

        # Get scaling factors
        img_h, img_w = self.screenshot_rgb.shape[:2]
        scale_x = img_w / self.width if self.width > 0 else 1
        scale_y = img_h / self.height if self.height > 0 else 1

        # Convert touch position to image coordinates
        local_x = touch.x - self.x
        local_y = touch.y - self.y
        img_x = local_x * scale_x
        img_y = img_h - (local_y * scale_y)

        # Find which bbox was clicked
        for bbox in reversed(self.bboxes):  # Check from top to bottom
            edge_type = bbox.get_edge_type(img_x, img_y)
            if edge_type:
                # Deselect others
                for b in self.bboxes:
                    b.is_selected = False
                bbox.is_selected = True
                self.dragging_bbox = bbox
                self.drag_edge_type = edge_type
                self.last_touch = touch.pos
                self._redraw_bboxes()
                return True

        # No bbox clicked
        for b in self.bboxes:
            b.is_selected = False
        self._redraw_bboxes()
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        """Handle touch move."""
        if self.dragging_bbox is None or self.last_touch is None:
            return False

        # Calculate delta in image coordinates
        img_h, img_w = self.screenshot_rgb.shape[:2]
        scale_x = img_w / self.width if self.width > 0 else 1
        scale_y = img_h / self.height if self.height > 0 else 1

        dx = (touch.x - self.last_touch[0]) * scale_x
        dy = -(touch.y - self.last_touch[1]) * scale_y  # Invert Y

        self.dragging_bbox.apply_drag(self.drag_edge_type, dx, dy)
        if not self.has_modifications:
            self.has_modifications = True
        self.last_touch = touch.pos

        self._redraw_bboxes()
        return True

    def on_touch_up(self, touch):
        """Handle touch up."""
        self.dragging_bbox = None
        self.drag_edge_type = None
        self.last_touch = None
        return True

    def get_modified_bboxes(self):
        """Return modified bboxes."""
        return [b.to_dict() for b in self.bboxes]
