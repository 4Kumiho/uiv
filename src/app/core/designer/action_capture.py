"""Action capture system - cattura automatica azioni."""

import time
import json
import sys
import logging
import threading
import numpy as np
from pynput import mouse, keyboard
from screenshot_handler import ScreenshotHandler
from _bbox_generator import BBoxGenerator

logger = logging.getLogger(__name__)


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
        self.double_click_threshold = 0.4

        # DRAG_AND_DROP tracking
        self.drag_active = False
        self.drag_start_pos = None
        self.drag_start_screenshot = None

        # Click waiting system: dopo un click, aspetta 0.4s per decidere il tipo
        self.click_awaiting = None  # (x, y, button) del click in attesa
        self.click_decision_timer = None

        # Scroll debouncing - aggrega scroll consecutivi in un singolo step
        self.scroll_timer = None
        self.scroll_pending = {'x': 0, 'y': 0, 'dx': 0, 'dy': 0}
        self.scroll_debounce = 0.3  # aggregazione per 0.3 secondi

        logger.debug("ActionCapture initialized")

    def start_recording(self):
        """Attiva global hooks per mouse e tastiera. Cattura screenshot iniziale nel buffer."""
        logger.debug("Starting recording...")

        # Cattura screenshot iniziale nel buffer
        try:
            self.buffer_screenshot = self.screenshot_handler.capture_full_screen()
            if self.on_buffer_update_callback:
                self.on_buffer_update_callback(self.buffer_screenshot)
            logger.debug("Initial screenshot captured in buffer")
        except Exception as e:
            logger.error(f"Error capturing initial screenshot: {e}")

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
        logger.debug("Listeners started")

    def stop_recording(self):
        """Ferma global hooks."""
        logger.debug("Stopping recording...")
        if self.mouse_listener:
            self.mouse_listener.stop()
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        logger.debug("Listeners stopped")

    def _on_mouse_click(self, x, y, button, pressed):
        """Cattura mouse click (left, right) o inizio/fine DRAG."""
        if not pressed:
            # Button release - potrebbe essere fine DRAG o fine di un click
            if button == mouse.Button.left:
                if self.drag_active:
                    self._on_mouse_release(x, y)
                elif self.click_awaiting is not None:
                    # Mouse release senza movimento significativo
                    logger.debug(f"✓ Button RELEASED without movement at ({x}, {y}) - awaiting 0.4s for SINGLE_CLICK confirmation")
                    # Il timer deciderà se è SINGLE_CLICK o DOUBLE_CLICK
            return

        logger.debug(f"CLICK detected: pos=({x}, {y}), button={button}, pressed={True}")

        # Se INPUT attivo, termina INPUT
        if self.input_active:
            logger.info("INPUT was active, finalizing...")
            self._finalize_input_action()

        # LEFT CLICK
        if button == mouse.Button.left:
            logger.info(f"✓ LEFT CLICK PRESSED at ({x}, {y}) - button held down, awaiting 0.4s...")

            # Se c'era già un click in attesa, questo è un DOUBLE_CLICK!
            if self.click_awaiting is not None:
                logger.info(f"✓ DOUBLE_CLICK detected! (2nd click within 0.4s threshold)")
                self.click_decision_timer.cancel()
                thread = threading.Thread(target=self._process_click, args=(x, y, button, 'DOUBLE_CLICK'), daemon=True)
                thread.start()
                self.click_awaiting = None
                self.click_decision_timer = None
                return

            # Primo click - mettilo in attesa
            self.click_awaiting = (x, y, button)
            self.drag_active = False
            self.drag_start_pos = (x, y)
            self.drag_start_screenshot = self.buffer_screenshot

            # Avvia il timer di 0.4 secondi per decidere il tipo di click
            self.click_decision_timer = threading.Timer(
                self.double_click_threshold,
                self._decide_click_type
            )
            self.click_decision_timer.start()

        elif button == mouse.Button.right:
            # RIGHT CLICK - non dragga, registra subito
            logger.info("✓ RIGHT CLICK")
            thread = threading.Thread(target=self._process_click, args=(x, y, button), daemon=True)
            thread.start()
        else:
            logger.warning(f"Unknown button: {button}")

    def _decide_click_type(self):
        """Timer scaduto (0.4s) - decidi il tipo di click."""
        # Se è ancora in attesa (non è stato registrato un DRAG o DOUBLE_CLICK)
        if self.click_awaiting is not None and not self.drag_active:
            x, y, button = self.click_awaiting
            logger.info("✓ 0.4s timeout - no movement, no 2nd click → registering as SINGLE_CLICK")
            thread = threading.Thread(target=self._process_click, args=(x, y, button, 'SINGLE_CLICK'), daemon=True)
            thread.start()
            self.click_awaiting = None
            self.click_decision_timer = None
        elif self.drag_active:
            # È stato registrato come drag nel frattempo, il drag è già stato processato
            logger.info("  0.4s timeout - was detected as DRAG (already processed)")
            self.click_awaiting = None
            self.click_decision_timer = None

    def _process_click(self, x, y, button, forced_action_type=None):
        """Processa il click in un thread separato."""
        try:
            logger.debug(f"Processing click at ({x}, {y}), button={button}")

            # Converti coordinate globali a coordinate relative al monitor
            if self.monitor_info:
                x_rel = x - self.monitor_info['left']
                y_rel = y - self.monitor_info['top']
            else:
                x_rel, y_rel = x, y

            # Rileva action type in base al button
            if forced_action_type:
                action_type = forced_action_type
            elif button == mouse.Button.right:
                action_type = 'RIGHT_CLICK'
            else:
                action_type = 'SINGLE_CLICK'

            # PASSO 1: Crea action con screenshot dal buffer
            action = {
                'action_type': action_type,
                'coordinates': {"x": int(x_rel), "y": int(y_rel)},
                'screenshot': self.buffer_screenshot,  # Usa buffer
                'timestamp': time.time()
            }

            logger.info(f"✓ {action_type} action created at ({int(x_rel)}, {int(y_rel)})")

            # PASSO 2: Genera bbox dall'azione (sarà fatto in main_designer dopo il callback)
            # PASSO 3: OCR + ResNet (sarà fatto in main_designer in background)
            # PASSO 4: Salva nel DB (fatto in main_designer)

            # PASSO 5: Chiama callback per salvare lo step
            if self.on_action_callback:
                self.on_action_callback(action)

            # PASSO 6: Aspetta stabilizzazione schermo
            self.screenshot_handler.wait_for_screen_stability()
            logger.debug("Screen stabilized")

            # PASSO 7: Cattura nuovo screenshot nel buffer
            self.buffer_screenshot = self.screenshot_handler.capture_full_screen()
            if self.on_buffer_update_callback:
                self.on_buffer_update_callback(self.buffer_screenshot)
            logger.debug(f"✓ Screenshot updated in buffer (post-{action_type})")

            # PASSO 8: Notifica che il buffer è pronto
            if self.on_buffer_ready_callback:
                self.on_buffer_ready_callback()
            logger.debug("✓ Buffer ready for next action")

        except Exception as e:
            logger.error(f"Error capturing click: {e}")
            import traceback
            traceback.print_exc(file=sys.stderr)

    def _on_mouse_move(self, x, y):
        """Traccia mouse movement per rilevare DRAG."""
        if self.drag_start_pos is None or self.click_awaiting is None:
            return

        # Rileva se è un drag (movimento significativo)
        dx = abs(x - self.drag_start_pos[0])
        dy = abs(y - self.drag_start_pos[1])
        min_drag_distance = 5  # pixel

        if (dx > min_drag_distance or dy > min_drag_distance) and not self.drag_active:
            self.drag_active = True
            # Cancella il timer della decisione del click - è un drag!
            if self.click_decision_timer:
                self.click_decision_timer.cancel()
            self.click_awaiting = None
            self.click_decision_timer = None
            logger.info(f"✓ DRAG DETECTED - button STILL PRESSED: start=({self.drag_start_pos[0]}, {self.drag_start_pos[1]}), current=({x}, {y})")

    def _on_mouse_release(self, x, y):
        """Processa il release del mouse - solo per DRAG_AND_DROP."""
        # Se era un DRAG, processa il DRAG_AND_DROP
        if self.drag_active and self.drag_start_pos is not None:
            logger.info(f"✓ DRAG_AND_DROP COMPLETED - button RELEASED at ({x}, {y}): from ({self.drag_start_pos[0]}, {self.drag_start_pos[1]})")

            # Cattura i valori PRIMA di resettare
            start_x, start_y = self.drag_start_pos[0], self.drag_start_pos[1]
            screenshot = self.drag_start_screenshot

            # Processa in background thread
            thread = threading.Thread(
                target=self._process_drag,
                args=(start_x, start_y, x, y, screenshot),
                daemon=True
            )
            thread.start()

            # Reset drag state
            self.drag_start_pos = None
            self.drag_start_screenshot = None
            self.drag_active = False

            # Cancella il timer di click decision se esiste (era in attesa per doppio click)
            if self.click_decision_timer:
                self.click_decision_timer.cancel()
            self.click_awaiting = None
            self.click_decision_timer = None

        # Per click senza drag, il timer di 0.4s gestirà automaticamente la decisione
        # Non è necessario fare nulla qui

    def _process_drag(self, x1, y1, x2, y2, screenshot=None):
        """Processa DRAG_AND_DROP in thread separato."""
        try:
            logger.debug(f"Processing DRAG: from ({x1}, {y1}) to ({x2}, {y2})")
            logger.debug(f"DRAG screenshot: {type(screenshot)} - {screenshot.shape if hasattr(screenshot, 'shape') else 'None/no shape'}")

            # Converti coordinate globali a relative al monitor
            if self.monitor_info:
                x1_rel = x1 - self.monitor_info['left']
                y1_rel = y1 - self.monitor_info['top']
                x2_rel = x2 - self.monitor_info['left']
                y2_rel = y2 - self.monitor_info['top']
            else:
                x1_rel, y1_rel, x2_rel, y2_rel = x1, y1, x2, y2

            # PASSO 1: Usa screenshot passato come parametro
            action = {
                'action_type': 'DRAG_AND_DROP',
                'coordinates': {"x": int(x1_rel), "y": int(y1_rel)},  # Inizio drag
                'drag_end_coordinates': {"x": int(x2_rel), "y": int(y2_rel)},  # Fine drag
                'screenshot': screenshot,  # Stato PRIMA del drag
                'timestamp': time.time()
            }

            logger.info("✓ DRAG_AND_DROP action created")

            # PASSO 2: Chiama callback per salvare lo step
            if self.on_action_callback:
                self.on_action_callback(action)
                logger.debug("DRAG_AND_DROP callback executed")

            # PASSO 3: Aspetta stabilizzazione schermo
            self.screenshot_handler.wait_for_screen_stability()
            logger.debug("Screen stabilized after DRAG")

            # PASSO 4: Cattura nuovo screenshot nel buffer per stato DOPO drag
            self.buffer_screenshot = self.screenshot_handler.capture_full_screen()
            if self.on_buffer_update_callback:
                self.on_buffer_update_callback(self.buffer_screenshot)
            logger.info("✓ New buffer screenshot captured after DRAG")

            # PASSO 5: Notifica che il buffer è pronto
            if self.on_buffer_ready_callback:
                self.on_buffer_ready_callback()
            logger.debug("✓ Buffer ready for next step")

        except Exception as e:
            logger.error(f"Error processing DRAG: {e}")
            import traceback
            traceback.print_exc(file=sys.stderr)

    def _on_mouse_scroll(self, x, y, dx, dy):
        """Cattura scroll - aggrega scroll consecutivi."""
        logger.debug(f"Scroll detected: ({x}, {y}), d=({dx}, {dy})")

        # Se INPUT attivo, termina INPUT
        if self.input_active:
            self._finalize_input_action()

        # Accumula questo evento di scroll
        self.scroll_pending['x'] = x
        self.scroll_pending['y'] = y
        self.scroll_pending['dx'] += dx
        self.scroll_pending['dy'] += dy

        # Se c'è un timer già attivo, cancellalo
        if self.scroll_timer is not None:
            self.scroll_timer.cancel()

        # Avvia (o riavvia) il timer di debounce
        self.scroll_timer = threading.Timer(self.scroll_debounce, self._finalize_scroll)
        self.scroll_timer.start()

    def _finalize_scroll(self):
        """Processa lo scroll aggregato quando il timer scade."""
        # Prendi i valori accumulati
        x = self.scroll_pending['x']
        y = self.scroll_pending['y']
        dx = self.scroll_pending['dx']
        dy = self.scroll_pending['dy']

        # Resetta lo stato di scroll
        self.scroll_timer = None
        self.scroll_pending = {'x': 0, 'y': 0, 'dx': 0, 'dy': 0}

        # Processa lo scroll aggregato in background thread
        thread = threading.Thread(target=self._process_scroll, args=(x, y, dx, dy), daemon=True)
        thread.start()

    def _process_scroll(self, x, y, dx, dy):
        """Processa scroll in thread separato."""
        try:
            logger.info("✓ SCROLL detected")

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
                logger.debug("Scroll callback executed")

            # Cattura nuovo screenshot nel buffer dopo SCROLL
            self.buffer_screenshot = self.screenshot_handler.capture_full_screen()
            if self.on_buffer_update_callback:
                self.on_buffer_update_callback(self.buffer_screenshot)
            logger.debug("✓ Screenshot updated in buffer (post-SCROLL)")

            # Notifica che il buffer è pronto
            if self.on_buffer_ready_callback:
                self.on_buffer_ready_callback()
            logger.debug("✓ Buffer ready for next action")
        except Exception as e:
            logger.error(f"Error capturing scroll: {e}")
            import traceback
            traceback.print_exc(file=sys.stderr)

    def _on_key_press(self, key):
        """Cattura tasti."""
        try:
            # CTRL = Cattura screenshot manuale per sostituire buffer
            if key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
                logger.info("✓ CTRL pressed - manual screenshot")
                try:
                    self.buffer_screenshot = self.screenshot_handler.capture_full_screen()
                    if self.on_buffer_update_callback:
                        self.on_buffer_update_callback(self.buffer_screenshot)
                    logger.debug("✓ Screenshot updated in buffer (CTRL)")
                except Exception as e:
                    logger.error(f"Error capturing manual screenshot: {e}")
                return

            # F9 = Fine INPUT (salva azione)
            if key == keyboard.Key.f9:
                logger.info("✓ F9 detected - finalizing INPUT")
                if self.input_active:
                    self._finalize_input_action()
                    if self.on_input_end_callback:
                        self.on_input_end_callback()

            # ENTER = Newline (continua INPUT, aggiunge newline)
            elif key == keyboard.Key.enter:
                logger.info("✓ ENTER detected - adding newline")
                if self.input_active:
                    self.input_text += '\n'
                    logger.debug("Newline added to input")

            # Caratteri normali
            elif hasattr(key, 'char') and key.char:
                logger.debug(f"Char detected: '{key.char}'")
                self.input_active = True
                self.input_text += key.char
                if self.input_start_time is None:
                    self.input_start_time = time.time()
            else:
                logger.debug(f"Key detected: {key}")

        except Exception as e:
            logger.error(f"Error capturing key: {e}")
            import traceback
            traceback.print_exc(file=sys.stderr)

    def _finalize_input_action(self):
        """Salva INPUT action."""
        if not self.input_active or not self.input_text:
            logger.debug("Input action not active or empty, skipping")
            return

        logger.info(f"✓ Finalizing INPUT: '{self.input_text}'")

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
                logger.debug("Input callback executed")

            # Cattura nuovo screenshot nel buffer dopo INPUT
            self.buffer_screenshot = self.screenshot_handler.capture_full_screen()
            if self.on_buffer_update_callback:
                self.on_buffer_update_callback(self.buffer_screenshot)
            logger.debug("✓ Screenshot updated in buffer (post-INPUT)")

            # Notifica che il buffer è pronto
            if self.on_buffer_ready_callback:
                self.on_buffer_ready_callback()
            logger.debug("✓ Buffer ready for next action")

            self.input_active = False
            self.input_text = ""
            self.input_start_time = None

        except Exception as e:
            logger.error(f"Error finalizing input: {e}")
            import traceback
            traceback.print_exc(file=sys.stderr)
