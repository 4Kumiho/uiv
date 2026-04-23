"""Action capture system - cattura automatica azioni."""

import time
import json
import sys
import threading
import numpy as np
from pynput import mouse, keyboard
from screenshot_handler import ScreenshotHandler
from bbox_generator import BBoxGenerator


class ActionCapture:
    def __init__(self, on_action_callback=None, on_input_end_callback=None, monitor_info=None, on_buffer_update_callback=None, on_buffer_ready_callback=None):
        """
        on_action_callback: (action_dict) -> chiamato quando azione catturata
        on_input_end_callback: () -> chiamato quando INPUT termina
        monitor_info: dict con left, top, width, height per catturare il monitor corretto
        on_buffer_update_callback: (screenshot) -> chiamato quando buffer screenshot è aggiornato
        on_buffer_ready_callback: () -> chiamato quando buffer è pronto per il prossimo step
        """
        self.on_action_callback = on_action_callback
        self.on_input_end_callback = on_input_end_callback
        self.on_buffer_update_callback = on_buffer_update_callback
        self.on_buffer_ready_callback = on_buffer_ready_callback
        self.monitor_info = monitor_info

        self.screenshot_handler = ScreenshotHandler(monitor_info=monitor_info)
        self.bbox_generator = BBoxGenerator()

        # Buffer screenshot - usato per il prossimo step
        self.buffer_screenshot = None

        self.input_active = False
        self.input_text = ""
        self.input_start_time = None

        self.mouse_listener = None
        self.keyboard_listener = None
        self.last_click_time = 0
        self.double_click_threshold = 0.3

        print("[ActionCapture] Initialized", file=sys.stderr, flush=True)

    def start_recording(self):
        """Attiva global hooks per mouse e tastiera. Cattura screenshot iniziale nel buffer."""
        print("[ActionCapture] Starting recording...", file=sys.stderr, flush=True)

        # Cattura screenshot iniziale nel buffer
        try:
            self.buffer_screenshot = self.screenshot_handler.capture_full_screen()
            if self.on_buffer_update_callback:
                self.on_buffer_update_callback(self.buffer_screenshot)
            print("[ActionCapture] Initial screenshot captured in buffer", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"[ActionCapture] Error capturing initial screenshot: {e}", file=sys.stderr, flush=True)

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
        print("[ActionCapture] Listeners started", file=sys.stderr, flush=True)

    def stop_recording(self):
        """Ferma global hooks."""
        print("[ActionCapture] Stopping recording...", file=sys.stderr, flush=True)
        if self.mouse_listener:
            self.mouse_listener.stop()
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        print("[ActionCapture] Listeners stopped", file=sys.stderr, flush=True)

    def _on_mouse_click(self, x, y, button, pressed):
        """Cattura mouse click."""
        if not pressed:
            return

        print(f"[ActionCapture] Mouse click detected: ({x}, {y}), button={button}", file=sys.stderr, flush=True)

        # Se INPUT attivo, termina INPUT
        if self.input_active:
            self._finalize_input_action()

        # Cattura CLICK in background thread per non bloccare listener
        thread = threading.Thread(target=self._process_click, args=(x, y, button), daemon=True)
        thread.start()

    def _process_click(self, x, y, button):
        """Processa il click in un thread separato."""
        try:
            print(f"[ActionCapture] Processing click at ({x}, {y})", file=sys.stderr, flush=True)

            # Converti coordinate globali a coordinate relative al monitor
            if self.monitor_info:
                x_rel = x - self.monitor_info['left']
                y_rel = y - self.monitor_info['top']
            else:
                x_rel, y_rel = x, y

            # Rileva single vs double click
            current_time = time.time()
            if current_time - self.last_click_time < self.double_click_threshold:
                action_type = 'DOUBLE_CLICK'
            else:
                action_type = 'SINGLE_CLICK'
            self.last_click_time = current_time

            # PASSO 1: Crea action con screenshot dal buffer
            action = {
                'action_type': action_type,
                'coordinates': {"x": int(x_rel), "y": int(y_rel)},
                'screenshot': self.buffer_screenshot,  # Usa buffer
                'timestamp': time.time()
            }

            print(f"[ActionCapture] Action created: {action_type}", file=sys.stderr, flush=True)

            # PASSO 2: Genera bbox dall'azione (sarà fatto in main_designer dopo il callback)
            # PASSO 3: OCR + ResNet (sarà fatto in main_designer in background)
            # PASSO 4: Salva nel DB (fatto in main_designer)

            # PASSO 5: Chiama callback per salvare lo step
            if self.on_action_callback:
                self.on_action_callback(action)
                print(f"[ActionCapture] Callback executed", file=sys.stderr, flush=True)

            # PASSO 6: Aspetta stabilizzazione schermo
            self.screenshot_handler.wait_for_screen_stability()
            print(f"[ActionCapture] Screen stabilized", file=sys.stderr, flush=True)

            # PASSO 7: Cattura nuovo screenshot nel buffer
            self.buffer_screenshot = self.screenshot_handler.capture_full_screen()
            if self.on_buffer_update_callback:
                self.on_buffer_update_callback(self.buffer_screenshot)
            print(f"[ActionCapture] New buffer screenshot captured", file=sys.stderr, flush=True)

            # PASSO 8: Notifica che il buffer è pronto
            if self.on_buffer_ready_callback:
                self.on_buffer_ready_callback()
            print(f"[ActionCapture] Buffer ready for next step", file=sys.stderr, flush=True)

        except Exception as e:
            print(f"[ActionCapture] Error capturing click: {e}", file=sys.stderr, flush=True)
            import traceback
            traceback.print_exc(file=sys.stderr)

    def _on_mouse_move(self, x, y):
        """Mouse move - non cattura."""
        pass

    def _on_mouse_scroll(self, x, y, dx, dy):
        """Cattura scroll."""
        print(f"[ActionCapture] Scroll detected: ({x}, {y}), d=({dx}, {dy})", file=sys.stderr, flush=True)

        # Se INPUT attivo, termina INPUT
        if self.input_active:
            self._finalize_input_action()

        # Processa scroll in background thread
        thread = threading.Thread(target=self._process_scroll, args=(x, y, dx, dy), daemon=True)
        thread.start()

    def _process_scroll(self, x, y, dx, dy):
        """Processa scroll in thread separato."""
        try:
            print(f"[ActionCapture] Processing scroll", file=sys.stderr, flush=True)

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
                print(f"[ActionCapture] Scroll callback executed", file=sys.stderr, flush=True)

            # Cattura nuovo screenshot nel buffer dopo SCROLL
            self.buffer_screenshot = self.screenshot_handler.capture_full_screen()
            if self.on_buffer_update_callback:
                self.on_buffer_update_callback(self.buffer_screenshot)
            print(f"[ActionCapture] New buffer screenshot captured after SCROLL", file=sys.stderr, flush=True)

            # Notifica che il buffer è pronto
            if self.on_buffer_ready_callback:
                self.on_buffer_ready_callback()
            print(f"[ActionCapture] Buffer ready for next step", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"[ActionCapture] Error capturing scroll: {e}", file=sys.stderr, flush=True)
            import traceback
            traceback.print_exc(file=sys.stderr)

    def _on_key_press(self, key):
        """Cattura tasti."""
        try:
            # CTRL = Cattura screenshot manuale per sostituire buffer
            if key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
                print(f"[ActionCapture] CTRL detected - capturing manual screenshot", file=sys.stderr, flush=True)
                try:
                    self.buffer_screenshot = self.screenshot_handler.capture_full_screen()
                    if self.on_buffer_update_callback:
                        self.on_buffer_update_callback(self.buffer_screenshot)
                    print(f"[ActionCapture] Manual screenshot captured and buffered", file=sys.stderr, flush=True)
                except Exception as e:
                    print(f"[ActionCapture] Error capturing manual screenshot: {e}", file=sys.stderr, flush=True)
                return

            # F9 o ENTER = Fine INPUT
            if key == keyboard.Key.f9 or key == keyboard.Key.enter:
                print(f"[ActionCapture] F9/ENTER detected", file=sys.stderr, flush=True)
                if self.input_active:
                    self._finalize_input_action()
                    if self.on_input_end_callback:
                        self.on_input_end_callback()

            # Caratteri normali
            elif hasattr(key, 'char') and key.char:
                print(f"[ActionCapture] Char detected: '{key.char}'", file=sys.stderr, flush=True)
                self.input_active = True
                self.input_text += key.char
                if self.input_start_time is None:
                    self.input_start_time = time.time()
            else:
                print(f"[ActionCapture] Key detected: {key}", file=sys.stderr, flush=True)

        except Exception as e:
            print(f"[ActionCapture] Error capturing key: {e}", file=sys.stderr, flush=True)
            import traceback
            traceback.print_exc(file=sys.stderr)

    def _finalize_input_action(self):
        """Salva INPUT action."""
        if not self.input_active or not self.input_text:
            print(f"[ActionCapture] Input action not active or empty, skipping", file=sys.stderr, flush=True)
            return

        print(f"[ActionCapture] Finalizing input: '{self.input_text}'", file=sys.stderr, flush=True)

        # Processa in background thread
        thread = threading.Thread(target=self._process_input_action, daemon=True)
        thread.start()

    def _process_input_action(self):
        """Processa INPUT action in thread separato."""
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
                print(f"[ActionCapture] Input callback executed", file=sys.stderr, flush=True)

            # Cattura nuovo screenshot nel buffer dopo INPUT
            self.buffer_screenshot = self.screenshot_handler.capture_full_screen()
            if self.on_buffer_update_callback:
                self.on_buffer_update_callback(self.buffer_screenshot)
            print(f"[ActionCapture] New buffer screenshot captured after INPUT", file=sys.stderr, flush=True)

            # Notifica che il buffer è pronto
            if self.on_buffer_ready_callback:
                self.on_buffer_ready_callback()
            print(f"[ActionCapture] Buffer ready for next step", file=sys.stderr, flush=True)

            self.input_active = False
            self.input_text = ""
            self.input_start_time = None

        except Exception as e:
            print(f"[ActionCapture] Error finalizing input: {e}", file=sys.stderr, flush=True)
            import traceback
            traceback.print_exc(file=sys.stderr)
