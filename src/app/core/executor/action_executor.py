"""Action execution using pynput for mouse and keyboard control."""

import json
import time
import logging
from pynput import mouse, keyboard

logger = logging.getLogger(__name__)


class ActionExecutor:
    """Executes designer actions (click, input, drag, scroll) on target element."""

    def __init__(self, monitor_info: dict):
        """
        Initialize action executor.

        Args:
            monitor_info: Dict with keys: 'left', 'top', 'width', 'height', 'index'
        """
        self._monitor = monitor_info
        self._mouse = mouse.Controller()
        self._keyboard = keyboard.Controller()

    def execute(self, designer_step, found_bbox: dict, wait_time: float = 2.0):
        """
        Execute action on found element.

        Args:
            designer_step: DesignerStep with action details
            found_bbox: {'x': int, 'y': int, 'w': int, 'h': int} in screen coordinates
            wait_time: Seconds to wait after action before proceeding (UI stabilization)
        """
        try:
            action = designer_step.action_type

            if action in ('SINGLE_CLICK', 'RIGHT_CLICK', 'DOUBLE_CLICK'):
                self._execute_click(designer_step, found_bbox, action)
            elif action == 'INPUT':
                self._execute_input(designer_step)
            elif action == 'DRAG_AND_DROP':
                self._execute_drag(designer_step, found_bbox)
            elif action == 'SCROLL':
                self._execute_scroll(designer_step, found_bbox)
            else:
                logger.warning(f"Unknown action type: {action}")

            # Wait for screen to stabilize after action
            logger.debug(f"Waiting {wait_time}s for screen stabilization after {action}")
            time.sleep(wait_time)

        except Exception as e:
            logger.error(f"Action execution failed: {e}", exc_info=True)
            raise

    def _execute_click(self, designer_step, found_bbox: dict, action_type: str):
        """Execute click action."""
        # Calculate click position
        x, y = self._calculate_click_position(designer_step, found_bbox)

        logger.info(f"{action_type} at ({x}, {y})")

        # Move mouse to position first
        self._mouse.position = (x, y)

        if action_type == 'SINGLE_CLICK':
            self._mouse.click(button=mouse.Button.left, count=1)
        elif action_type == 'RIGHT_CLICK':
            self._mouse.click(button=mouse.Button.right, count=1)
        elif action_type == 'DOUBLE_CLICK':
            self._mouse.click(button=mouse.Button.left, count=2)

        # Check for press_enter_after
        if designer_step.press_enter_after:
            logger.debug("Pressing Enter after click")
            time.sleep(0.2)
            self._keyboard.press(keyboard.Key.enter)
            self._keyboard.release(keyboard.Key.enter)

    def _execute_input(self, designer_step):
        """Execute text input action."""
        text = designer_step.input_text or ""
        logger.info(f"Typing: {text[:50]}..." if len(text) > 50 else f"Typing: {text}")

        self._keyboard.type(text)

        if designer_step.press_enter_after:
            logger.debug("Pressing Enter after input")
            time.sleep(0.2)
            self._keyboard.press(keyboard.Key.enter)
            self._keyboard.release(keyboard.Key.enter)

    def _execute_drag(self, designer_step, found_bbox: dict):
        """Execute drag and drop action."""
        # Start position
        start_x, start_y = self._calculate_click_position(designer_step, found_bbox)

        # End position (drag_end_bbox)
        if not designer_step.drag_end_bbox:
            logger.error("Missing drag_end_bbox")
            return

        drag_end_bbox = json.loads(designer_step.drag_end_bbox)
        drag_end_rel = json.loads(designer_step.drag_end_coordinates_rel or '{"x":0,"y":0}')
        end_x = drag_end_bbox['x'] + drag_end_rel['x'] + self._monitor['left']
        end_y = drag_end_bbox['y'] + drag_end_rel['y'] + self._monitor['top']

        logger.info(f"Dragging from ({start_x}, {start_y}) to ({end_x}, {end_y})")

        # Move to start
        self._mouse.position = (start_x, start_y)
        time.sleep(0.1)

        # Drag to end
        self._mouse.press(mouse.Button.left)
        self._mouse.position = (end_x, end_y)
        self._mouse.release(mouse.Button.left)

    def _execute_scroll(self, designer_step, found_bbox: dict):
        """Execute scroll action."""
        scroll_x = designer_step.scroll_dx or 0
        scroll_y = designer_step.scroll_dy or 0

        # Move to element center for scrolling
        center_x = found_bbox['x'] + found_bbox['w'] // 2 + self._monitor['left']
        center_y = found_bbox['y'] + found_bbox['h'] // 2 + self._monitor['top']

        logger.info(f"Scrolling at ({center_x}, {center_y}): dx={scroll_x}, dy={scroll_y}")

        self._mouse.position = (center_x, center_y)
        time.sleep(0.1)

        # Scroll
        self._mouse.scroll(scroll_x, scroll_y)

    def _calculate_click_position(self, designer_step, found_bbox: dict) -> tuple:
        """
        Calculate absolute click position from found bbox and relative coordinates.

        Returns:
            (x, y) in absolute screen coordinates
        """
        # Relative coordinates within the bbox
        if designer_step.coordinates_rel:
            rel = json.loads(designer_step.coordinates_rel)
            rel_x = rel.get('x', 0)
            rel_y = rel.get('y', 0)
        else:
            rel_x = found_bbox['w'] // 2
            rel_y = found_bbox['h'] // 2

        # Absolute position: bbox position + relative offset + monitor offset
        x = found_bbox['x'] + rel_x + self._monitor['left']
        y = found_bbox['y'] + rel_y + self._monitor['top']

        return (x, y)
