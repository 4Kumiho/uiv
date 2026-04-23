"""Main Designer - Recording orchestration."""

import sys
import os
import json
import cv2
import time

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'database'))

from screenshot_handler import ScreenshotHandler
from action_capture import ActionCapture
from mini_ui import MiniUI
from designer_db import DesignerDatabase
from models import DesignerStep
from bbox_generator import BBoxGenerator


class DesignerApp:
    def __init__(self, session_name: str, db_path: str, monitor_num: int = 0):
        self.session_name = session_name
        self.db = DesignerDatabase(db_path)
        self.session = None
        self.action_capture = None
        self.mini_ui = None
        self.step_count = 0
        self.should_stop = False
        self.monitor_num = monitor_num
        self.monitor_info = None
        self.screenshots_folder = None

    def start(self):
        """Avvia il designer."""
        print(f"[DESIGNER] Starting Designer: {self.session_name}", flush=True)
        import sys
        print(f"[DESIGNER] Python: {sys.executable}", flush=True)
        print(f"[DESIGNER] CWD: {os.getcwd()}", flush=True)

        # Crea session nel DB
        self.session = self.db.create_session(self.session_name)
        print(f"[DESIGNER] Created session ID: {self.session.id}", flush=True)

        time.sleep(0.5)

        # Ottieni info monitor
        try:
            from mss import mss
            with mss() as sct:
                monitors = sct.monitors[1:]
                if self.monitor_num < len(monitors):
                    self.monitor_info = monitors[self.monitor_num]
                    print(f"[DESIGNER] Using monitor: {self.monitor_info}", flush=True)
                else:
                    self.monitor_info = monitors[0]
                    print(f"[DESIGNER] Using default monitor: {self.monitor_info}", flush=True)
        except Exception as e:
            print(f"[DESIGNER] Error getting monitor info: {e}", flush=True)
            self.monitor_info = None

        # Sposta mouse al centro dello schermo scelto
        if self.monitor_info:
            center_x = self.monitor_info['left'] + self.monitor_info['width'] // 2
            center_y = self.monitor_info['top'] + self.monitor_info['height'] // 2
            from pynput.mouse import Controller
            mouse = Controller()
            mouse.position = (center_x, center_y)
            print(f"Mouse moved to center: ({center_x}, {center_y})")

        # Mostra Mini UI
        print("[DESIGNER] Creating Mini UI...", flush=True)
        self.mini_ui = MiniUI(
            mode='DESIGNER',
            on_end_callback=self._on_designer_end,
            on_input_end_callback=self._on_input_end,
            monitor_info=self.monitor_info
        )
        self.mini_ui.update()
        time.sleep(0.3)
        print("[DESIGNER] Mini UI created", flush=True)

        # Attendi stabilizzazione schermo iniziale
        screenshot_handler = ScreenshotHandler()
        print("[DESIGNER] Waiting for screen stability...", flush=True)
        initial_screenshot = screenshot_handler.wait_for_screen_stability()
        print("[DESIGNER] Screen stable! Ready to record.", flush=True)

        self.mini_ui.set_ready()

        # Avvia action capture
        print("[DESIGNER] Starting ActionCapture...", flush=True)
        self.action_capture = ActionCapture(
            on_action_callback=self._on_action_captured,
            on_input_end_callback=self._on_input_end,
            monitor_info=self.monitor_info,
            on_buffer_update_callback=self._on_buffer_updated,
            on_buffer_ready_callback=self._on_buffer_ready
        )
        self.action_capture.start_recording()
        print("[DESIGNER] ActionCapture started, waiting for actions...", flush=True)

        # Loop principale
        while not self.should_stop:
            try:
                self.mini_ui.update()
                time.sleep(0.1)
            except:
                break

        self._cleanup()

    def _on_action_captured(self, action_dict):
        """Callback quando azione è catturata."""
        print(f"\n[DESIGNER] Captured action: {action_dict['action_type']}", flush=True)
        self.mini_ui.set_saving()

        try:
            self.step_count += 1
            self.mini_ui.set_step(self.step_count)

            action_type = action_dict['action_type']

            # Estrai screenshot per salvare
            screenshot = action_dict.get('screenshot')
            screenshot_data = None
            screenshot_path = None
            if screenshot is not None:
                _, screenshot_data = cv2.imencode('.png', screenshot)
                # Salva come file PNG
                screenshot_filename = f"step_{self.step_count:03d}.png"
                screenshot_path = os.path.join(self.screenshots_folder, screenshot_filename)
                with open(screenshot_path, 'wb') as f:
                    f.write(screenshot_data.tobytes())

            # Genera bbox dalle coordinate per azioni che le hanno
            bbox_dict = {}
            bbox_image = None
            ocr_text = ""
            features = None

            if action_type in ('SINGLE_CLICK', 'DOUBLE_CLICK') and screenshot is not None:
                coords = action_dict.get('coordinates', {})
                x, y = coords.get('x', 0), coords.get('y', 0)
                print(f"[DESIGNER] Generating bbox from coordinates ({x}, {y})", flush=True)

                # Genera bbox intelligente
                bbox_dict = BBoxGenerator.generate_smart_bbox(screenshot, x, y)
                print(f"[DESIGNER] Generated bbox: {bbox_dict}", flush=True)

                # Estrai immagine dal bbox per OCR/ResNet
                bbox_image = BBoxGenerator.crop_image(screenshot, bbox_dict)

                # TODO: OCR - estrai testo dal bbox
                # ocr_text = self._extract_ocr(bbox_image)
                print(f"[DESIGNER] OCR placeholder (not implemented yet)", flush=True)

                # TODO: ResNet - estrai features dal bbox
                # features = self._extract_features(bbox_image)
                print(f"[DESIGNER] ResNet features placeholder (not implemented yet)", flush=True)

            # Crea step nel DB
            step = DesignerStep(
                session_id=self.session.id,
                step_number=self.step_count,
                action_type=action_type,
                screenshot=screenshot_data.tobytes() if screenshot_data is not None else None,
                screenshot_path=screenshot_path,
                coordinates=json.dumps(action_dict.get('coordinates', {})),
                bbox=json.dumps(bbox_dict),
                input_text=action_dict.get('input_text'),
                scroll_dx=action_dict.get('scroll_dx'),
                scroll_dy=action_dict.get('scroll_dy'),
                ocr_text=ocr_text,
                features=features,
            )
            self.db.add_step(self.session.id, step)

            print(f"[DESIGNER] Saved step #{self.step_count} to DB", flush=True)

        except Exception as e:
            print(f"[DESIGNER] Error saving action: {e}", flush=True)
            import traceback
            traceback.print_exc()

    def _on_input_end(self):
        """Callback quando INPUT termina."""
        print("[DESIGNER] Input ended", flush=True)

    def _on_buffer_updated(self, screenshot):
        """Callback quando buffer è aggiornato."""
        pass

    def _on_buffer_ready(self):
        """Callback quando buffer è pronto per il prossimo step."""
        print("[DESIGNER] Buffer ready - setting UI to ready", flush=True)
        self.mini_ui.set_ready()

    def _on_designer_end(self):
        """Callback quando Designer termina (ESC)."""
        print("\n[DESIGNER] Designer ended (ESC pressed)", flush=True)
        self.should_stop = True

    def _cleanup(self):
        """Pulisci e ferma."""
        if self.action_capture:
            self.action_capture.stop_recording()
        if self.mini_ui:
            self.mini_ui.close()
        if self.db:
            self.db.close()

        print(f"\nDesign session saved: {self.session_name}")
        print(f"Total steps: {self.step_count}")


if __name__ == "__main__":
    if len(sys.argv) >= 4:
        session_name = sys.argv[1]
        output_folder = sys.argv[2]
        monitor_num = int(sys.argv[3])

        # Create project folder structure
        project_folder = os.path.join(output_folder, session_name)
        os.makedirs(project_folder, exist_ok=True)

        # Create screenshots folder
        screenshots_folder = os.path.join(project_folder, 'screenshots')
        os.makedirs(screenshots_folder, exist_ok=True)

        db_path = os.path.join(project_folder, f"{session_name}.db")

        print(f"[DESIGNER] Project folder: {project_folder}", flush=True)
        print(f"[DESIGNER] DB path: {db_path}", flush=True)
        print(f"[DESIGNER] Screenshots folder: {screenshots_folder}", flush=True)

        app = DesignerApp(session_name, db_path, monitor_num)
        app.screenshots_folder = screenshots_folder
        app.start()

        # Signal to Kivy that the session is done
        signal_path = os.path.join(project_folder, "session_done.json")
        with open(signal_path, 'w') as f:
            json.dump({
                "session_id": app.session.id,
                "db_path": db_path,
                "monitor_info": app.monitor_info
            }, f)
        print(f"[DESIGNER] Wrote session_done.json: session_id={app.session.id}", flush=True)
    else:
        import tempfile
        temp_dir = tempfile.gettempdir()
        db_path = os.path.join(temp_dir, "ui_validator_designer.db")
        app = DesignerApp("test_session", db_path)
        app.start()
