"""Main Designer - test per cattura azioni."""

import sys
import os
import json
import cv2

# Add paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'core', 'designer'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'core', 'database'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'core', 'utils'))

from screenshot_handler import ScreenshotHandler
from action_capture import ActionCapture
from mini_ui import MiniUI
from window_manager import WindowManager
from designer_db import DesignerDatabase
from models import DesignerStep
import time


class DesignerApp:
    def __init__(self, session_name: str, db_path: str):
        self.session_name = session_name
        self.db = DesignerDatabase(db_path)
        self.session = None
        self.action_capture = None
        self.mini_ui = None
        self.step_count = 0
        self.should_stop = False

    def start(self):
        """Avvia il designer."""
        print(f"Starting Designer: {self.session_name}")

        # Crea session nel DB
        self.session = self.db.create_session(self.session_name)
        print(f"Created session ID: {self.session.id}")

        # Minimizza finestra principale
        WindowManager.minimize_current_window()
        time.sleep(1)

        # Mostra Mini UI
        self.mini_ui = MiniUI(
            mode='DESIGNER',
            on_end_callback=self._on_designer_end,
            on_input_end_callback=self._on_input_end
        )

        # Attendi stabilizzazione schermo iniziale
        screenshot_handler = ScreenshotHandler()
        print("Waiting for screen stability...")
        initial_screenshot = screenshot_handler.wait_for_screen_stability()
        print("Screen stable! Ready to record.")

        self.mini_ui.set_ready()

        # Avvia action capture
        self.action_capture = ActionCapture(
            on_action_callback=self._on_action_captured,
            on_input_end_callback=self._on_input_end
        )
        self.action_capture.start_recording()

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
        print(f"\nCaptured action: {action_dict['action_type']}")
        self.mini_ui.set_saving()

        try:
            self.step_count += 1

            # Estrai screenshot per salvare
            screenshot = action_dict.get('screenshot')
            screenshot_data = None
            if screenshot is not None:
                _, screenshot_data = cv2.imencode('.png', screenshot)

            # Crea step nel DB
            step = DesignerStep(
                session_id=self.session.id,
                step_number=self.step_count,
                action_type=action_dict['action_type'],
                screenshot=screenshot_data.tobytes() if screenshot_data is not None else None,
                coordinates=json.dumps(action_dict.get('coordinates', {})),
                bbox=json.dumps(action_dict.get('bbox', {})),
                input_text=action_dict.get('input_text'),
                scroll_dx=action_dict.get('scroll_dx'),
                scroll_dy=action_dict.get('scroll_dy'),
            )
            self.db.add_step(self.session.id, step)

            print(f"Saved step #{self.step_count} to DB")

            time.sleep(0.5)
            self.mini_ui.set_ready()

        except Exception as e:
            print(f"Error saving action: {e}")
            self.mini_ui.set_ready()

    def _on_input_end(self):
        """Callback quando INPUT termina."""
        print("Input ended")

    def _on_designer_end(self):
        """Callback quando Designer termina (ESC)."""
        print("\nDesigner ended (ESC pressed)")
        self.should_stop = True

    def _cleanup(self):
        """Pulisci e ferma."""
        if self.action_capture:
            self.action_capture.stop_recording()
        if self.mini_ui:
            self.mini_ui.close()
        if self.db:
            self.db.close()

        # Massimizza finestra principale
        WindowManager.maximize_current_window()

        print(f"\nDesign session saved: {self.session_name}")
        print(f"Total steps: {self.step_count}")


if __name__ == "__main__":
    import tempfile

    # Crea DB in temp folder
    temp_dir = tempfile.gettempdir()
    db_path = os.path.join(temp_dir, "ui_validator_designer.db")

    app = DesignerApp("test_session", db_path)
    app.start()
