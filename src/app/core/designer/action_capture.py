"""Action capture system - cattura automatica azioni."""

import time
import json
from pynput import mouse, keyboard
from screenshot_handler import ScreenshotHandler
from bbox_generator import BBoxGenerator


class ActionCapture:
    def __init__(self, on_action_callback=None, on_input_end_callback=None):
        """
        on_action_callback: (action_dict) -> chiamato quando azione catturata
        on_input_end_callback: () -> chiamato quando INPUT termina
        """
        self.on_action_callback = on_action_callback
        self.on_input_end_callback = on_input_end_callback

        self.screenshot_handler = ScreenshotHandler()
        self.bbox_generator = BBoxGenerator()

        self.input_active = False
        self.input_text = ""
        self.input_start_time = None

        self.mouse_listener = None
        self.keyboard_listener = None

    def start_recording(self):
        """Attiva global hooks per mouse e tastiera."""
        self.mouse_listener = mouse.Listener(
            on_click=self._on_mouse_click,
            on_move=self._on_mouse_move,
            on_scroll=self._on_mouse_scroll
        )
        self.keyboard_listener = keyboard.Listener(
            on_press=self._on_key_press
        )

        self.mouse_listener.start()
        self.keyboard_listener.start()

    def stop_recording(self):
        """Ferma global hooks."""
        if self.mouse_listener:
            self.mouse_listener.stop()
        if self.keyboard_listener:
            self.keyboard_listener.stop()

    def _on_mouse_click(self, x, y, button, pressed):
        """Cattura mouse click."""
        if not pressed:
            return

        # Se INPUT attivo, termina INPUT
        if self.input_active:
            self._finalize_input_action()

        # Cattura CLICK
        try:
            screenshot = self.screenshot_handler.wait_for_screen_stability()
            bbox = self.bbox_generator.generate_smart_bbox(screenshot, x, y)

            action = {
                'action_type': 'DOUBLE_CLICK' if button == mouse.Button.left else 'CLICK',
                'coordinates': {"x": int(x), "y": int(y)},
                'bbox': bbox,
                'screenshot': screenshot,
                'timestamp': time.time()
            }

            if self.on_action_callback:
                self.on_action_callback(action)
        except Exception as e:
            print(f"Error capturing click: {e}")

    def _on_mouse_move(self, x, y):
        """Mouse move - non cattura."""
        pass

    def _on_mouse_scroll(self, x, y, dx, dy):
        """Cattura scroll."""
        try:
            screenshot = self.screenshot_handler.wait_for_screen_stability()

            action = {
                'action_type': 'SCROLL',
                'scroll_dx': int(dx),
                'scroll_dy': int(dy),
                'coordinates': {"x": int(x), "y": int(y)},
                'screenshot': screenshot,
                'timestamp': time.time()
            }

            if self.on_action_callback:
                self.on_action_callback(action)
        except Exception as e:
            print(f"Error capturing scroll: {e}")

    def _on_key_press(self, key):
        """Cattura tasti."""
        try:
            # F9 o ENTER = Fine INPUT
            if key == keyboard.Key.f9 or key == keyboard.Key.enter:
                if self.input_active:
                    self._finalize_input_action()
                    if self.on_input_end_callback:
                        self.on_input_end_callback()

            # Caratteri normali
            elif hasattr(key, 'char') and key.char:
                self.input_active = True
                self.input_text += key.char
                if self.input_start_time is None:
                    self.input_start_time = time.time()

        except Exception as e:
            print(f"Error capturing key: {e}")

    def _finalize_input_action(self):
        """Salva INPUT action."""
        if not self.input_active or not self.input_text:
            return

        try:
            screenshot = self.screenshot_handler.wait_for_screen_stability()

            action = {
                'action_type': 'INPUT',
                'input_text': self.input_text,
                'screenshot': screenshot,
                'timestamp': time.time()
            }

            if self.on_action_callback:
                self.on_action_callback(action)

            self.input_active = False
            self.input_text = ""
            self.input_start_time = None

        except Exception as e:
            print(f"Error finalizing input: {e}")
