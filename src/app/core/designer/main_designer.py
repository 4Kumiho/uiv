"""Main Designer - Recording orchestration."""

import sys
import os
import json
import cv2
import time
import logging

# Add project root to path for absolute imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'database'))

from screenshot_handler import ScreenshotHandler
from action_capture import ActionCapture
from mini_ui import MiniUI
from src.app.core.database.designer_db import DesignerDatabase
from src.app.core.database.models import DesignerStep
from _bbox_generator import BBoxGenerator
from _ocr_generator import OCRGenerator
from _feature_generator import FeatureGenerator
from logging_config import setup_logging


class DesignerApp:
    def __init__(self, session_name: str, db_path: str, monitor_num: int = 0):
        self.session_name = session_name
        self.db = DesignerDatabase(db_path)
        self.session = None
        self.action_capture = None
        self.mini_ui = None
        self.step_count = 1
        self.should_stop = False
        self.monitor_num = monitor_num
        self.monitor_info = None
        self.screenshots_folder = None
        self.logger = logging.getLogger(__name__)
        self.ocr_generator = OCRGenerator()
        self.feature_generator = FeatureGenerator()

    # ==================== MAIN FLOW ====================

    def start(self):
        """Avvia il designer."""
        self.logger.info(f"Starting Designer: {self.session_name}")

        # Crea session nel DB
        self.session = self.db.create_session(self.session_name)

        time.sleep(0.5)

        # Ottieni info monitor
        try:
            from mss import mss
            with mss() as sct:
                monitors = sct.monitors[1:]
                if self.monitor_num < len(monitors):
                    self.monitor_info = monitors[self.monitor_num]
                else:
                    self.monitor_info = monitors[0]
        except Exception as e:
            self.logger.error(f"Error getting monitor info: {e}")
            self.monitor_info = None

        # Sposta mouse al centro dello schermo scelto
        if self.monitor_info:
            center_x = self.monitor_info['left'] + self.monitor_info['width'] // 2
            center_y = self.monitor_info['top'] + self.monitor_info['height'] // 2
            from pynput.mouse import Controller
            mouse = Controller()
            mouse.position = (center_x, center_y)

        # Mostra Mini UI
        self.logger.info("Creating Mini UI...")
        self.mini_ui = MiniUI(
            mode='DESIGNER',
            on_end_callback=self._on_designer_end,
            on_input_end_callback=self._on_input_end,
            monitor_info=self.monitor_info
        )
        self.mini_ui.update()
        time.sleep(0.3)
        self.logger.info("Mini UI created")

        # Attendi stabilizzazione schermo iniziale
        screenshot_handler = ScreenshotHandler()
        self.logger.info("Waiting for screen stability...")
        initial_screenshot = screenshot_handler.wait_for_screen_stability()
        self.logger.info("Screen stable! Ready to record.")

        # Mostra caricamento modelli
        self.mini_ui.set_loading()

        # Avvia action capture
        self.logger.info("Starting ActionCapture...")
        self.action_capture = ActionCapture(
            on_action_callback=self._on_action_captured,
            on_input_end_callback=self._on_input_end,
            monitor_info=self.monitor_info,
            on_buffer_update_callback=self._on_buffer_updated,
            on_buffer_ready_callback=self._on_buffer_ready
        )
        self.action_capture.start_recording()
        self.logger.info("=" * 60)
        self.logger.info("RECORDING STARTED - Downloading and initializing models...")
        self.logger.info("=" * 60)

        # Preload models BEFORE recording (blocking)
        self._preload_models()
        self.logger.info("Models ready! Recording can begin.")

        # Loop principale
        while not self.should_stop:
            try:
                self.mini_ui.update()
                time.sleep(0.1)
            except:
                break

        self._cleanup()

    # ==================== EXTRACTION METHODS ====================

    def _preload_models(self):
        """Precaria EasyOCR e ResNet in background."""
        try:
            import numpy as np
            dummy_image = np.zeros((224, 224, 3), dtype=np.uint8)
            self.logger.info("Preloading models...")
            self._extract_ocr(dummy_image)
            self._extract_resnet(dummy_image)
            self.logger.info("Models preloaded successfully!")
            self.mini_ui.set_ready()
        except Exception as e:
            self.logger.debug(f"Model preload in background: {e}")
            self.mini_ui.set_ready()

    def _extract_bbox(self, x, y, screenshot):
        """Genera bbox intelligente dalle coordinate."""
        self.logger.debug(f"Generating bbox from coordinates ({x}, {y})")
        bbox_dict = BBoxGenerator.generate_smart_bbox(screenshot, x, y)
        self.logger.debug(f"Generated bbox: {bbox_dict}")
        return bbox_dict

    def _extract_ocr(self, bbox_image):
        """Estrae testo dal bbox usando OCRGenerator."""
        return self.ocr_generator.extract(bbox_image)

    def _extract_resnet(self, bbox_image):
        """Estrae 512-dim feature vector usando FeatureGenerator."""
        return self.feature_generator.extract(bbox_image)

    # ==================== SAVE/UPDATE METHODS ====================

    def _save_screenshot(self, screenshot):
        """Salva screenshot come PNG."""
        screenshot_data = None
        screenshot_path = None
        if screenshot is not None:
            _, screenshot_data = cv2.imencode('.png', screenshot)
            screenshot_filename = f"step_{self.step_count:03d}.png"
            screenshot_path = os.path.join(self.screenshots_folder, screenshot_filename)
            with open(screenshot_path, 'wb') as f:
                f.write(screenshot_data.tobytes())
            self.logger.info(f"✓ Screenshot saved: {screenshot_filename}")
        return screenshot_data, screenshot_path

    def _update_screenshot_buffer(self):
        """Aggiorna il buffer screenshot con il nuovo screenshot stabile."""
        pass

    def _save_step_to_db(self, action_dict, action_type, screenshot_data, screenshot_path, result):
        """Salva uno step nel database."""
        step = DesignerStep(
            session_id=self.session.id,
            step_number=self.step_count,
            action_type=action_type,
            screenshot=screenshot_data.tobytes() if screenshot_data is not None else None,
            screenshot_path=screenshot_path,
            coordinates=json.dumps(action_dict.get('coordinates', {})),
            bbox=json.dumps(result.get('bbox', {})),
            input_text=action_dict.get('input_text'),
            scroll_dx=action_dict.get('scroll_dx'),
            scroll_dy=action_dict.get('scroll_dy'),
            ocr_text=result.get('ocr_text', ''),
            features=result.get('features'),
            drag_end_coordinates=json.dumps(action_dict.get('drag_end_coordinates', {})),
            drag_end_bbox=json.dumps(result.get('drag_end_bbox', {})),
            drag_end_ocr_text=result.get('drag_end_ocr_text', ''),
            drag_end_features=result.get('drag_end_features'),
        )
        self.db.add_step(self.session.id, step)
        self.logger.info(f"✓ Saved to DB: step #{self.step_count}")

    # ==================== UI METHODS ====================

    def _set_ui_red(self):
        """Setta UI a rosso (salvataggio in corso)."""
        self.mini_ui.set_saving()

    def _set_ui_green(self):
        """Setta UI a verde (pronto per prossima azione)."""
        self.mini_ui.set_ready()

    # ==================== ACTION HANDLERS ====================

    def _on_action_captured(self, action_dict):
        """Dispatcher per le azioni catturate."""
        action_type = action_dict['action_type']
        self.logger.info(f"{'='*60} ACTION: {action_type} {'='*60}")
        self._set_ui_red()

        try:
            # Salva screenshot
            screenshot = action_dict.get('screenshot')
            screenshot_data, screenshot_path = self._save_screenshot(screenshot)

            # Chiama handler specifico
            if action_type == 'SINGLE_CLICK':
                result = self._on_single_click(action_dict, screenshot)
            elif action_type == 'DOUBLE_CLICK':
                result = self._on_double_click(action_dict, screenshot)
            elif action_type == 'RIGHT_CLICK':
                result = self._on_right_click(action_dict, screenshot)
            elif action_type == 'DRAG_AND_DROP':
                result = self._on_drag_and_drop(action_dict, screenshot)
            elif action_type == 'INPUT':
                result = self._on_input(action_dict, screenshot)
            elif action_type == 'SCROLL':
                result = self._on_scroll(action_dict, screenshot)
            else:
                result = {}

            # Salva nel DB (con il numero corrente)
            self._save_step_to_db(action_dict, action_type, screenshot_data, screenshot_path, result)

            # Dopo salvataggio, incrementa per il prossimo step
            self.step_count += 1
            self.mini_ui.set_step(self.step_count)

        except Exception as e:
            self.logger.error(f"Error saving action: {e}")
            import traceback
            traceback.print_exc(file=sys.stderr)

    def _save_screenshot(self, screenshot):
        """Salva screenshot come PNG e ritorna i dati e il percorso."""
        screenshot_data = None
        screenshot_path = None
        if screenshot is not None:
            _, screenshot_data = cv2.imencode('.png', screenshot)
            screenshot_filename = f"step_{self.step_count:03d}.png"
            screenshot_path = os.path.join(self.screenshots_folder, screenshot_filename)
            with open(screenshot_path, 'wb') as f:
                f.write(screenshot_data.tobytes())
            self.logger.info(f"✓ Screenshot saved: {screenshot_filename}")
        return screenshot_data, screenshot_path

    def _on_single_click(self, action_dict, screenshot):
        """Handler per SINGLE_CLICK."""
        if screenshot is None:
            return {}
        coords = action_dict.get('coordinates', {})
        x, y = coords.get('x', 0), coords.get('y', 0)
        return self._process_click_action(x, y, screenshot)

    def _on_double_click(self, action_dict, screenshot):
        """Handler per DOUBLE_CLICK."""
        if screenshot is None:
            return {}
        coords = action_dict.get('coordinates', {})
        x, y = coords.get('x', 0), coords.get('y', 0)
        return self._process_click_action(x, y, screenshot)

    def _on_right_click(self, action_dict, screenshot):
        """Handler per RIGHT_CLICK."""
        if screenshot is None:
            return {}
        coords = action_dict.get('coordinates', {})
        x, y = coords.get('x', 0), coords.get('y', 0)
        return self._process_click_action(x, y, screenshot)

    def _process_click_action(self, x, y, screenshot):
        """Logica comune per click actions (SINGLE, DOUBLE, RIGHT)."""
        bbox_dict = self._extract_bbox(x, y, screenshot)
        bbox_image = BBoxGenerator.crop_image(screenshot, bbox_dict)

        ocr_text = self._extract_ocr(bbox_image)
        if ocr_text:
            self.logger.info(f"✓ OCR text: '{ocr_text[:50]}...'")
        else:
            self.logger.info("✓ OCR extraction completed (no text)")

        features = self._extract_resnet(bbox_image)
        if features:
            self.logger.info("✓ ResNet features extracted")

        return {
            'bbox': bbox_dict,
            'ocr_text': ocr_text,
            'features': features
        }

    def _on_drag_and_drop(self, action_dict, screenshot):
        """Handler per DRAG_AND_DROP."""
        self.logger.info(f"DRAG_AND_DROP: screenshot is {'None' if screenshot is None else f'{screenshot.shape}'}")
        if screenshot is None:
            self.logger.error("ERROR: DRAG_AND_DROP screenshot is None! Cannot extract bbox/ocr")
            return {}

        coords = action_dict.get('coordinates', {})
        x1, y1 = coords.get('x', 0), coords.get('y', 0)

        drag_end_coords = action_dict.get('drag_end_coordinates', {})
        x2, y2 = drag_end_coords.get('x', 0), drag_end_coords.get('y', 0)

        # Start point
        bbox_dict = self._extract_bbox(x1, y1, screenshot)
        bbox_image = BBoxGenerator.crop_image(screenshot, bbox_dict)

        ocr_text = self._extract_ocr(bbox_image)
        if ocr_text:
            self.logger.info(f"✓ DRAG start OCR: '{ocr_text[:50]}...'")
        else:
            self.logger.info("✓ DRAG start OCR extraction completed (no text)")

        features = self._extract_resnet(bbox_image)
        if features:
            self.logger.info("✓ DRAG start ResNet features extracted")

        # End point
        drag_end_bbox = self._extract_bbox(x2, y2, screenshot)
        drag_end_bbox_image = BBoxGenerator.crop_image(screenshot, drag_end_bbox)

        drag_end_ocr_text = self._extract_ocr(drag_end_bbox_image)
        if drag_end_ocr_text:
            self.logger.info(f"✓ DRAG end OCR: '{drag_end_ocr_text[:50]}...'")
        else:
            self.logger.info("✓ DRAG end OCR extraction completed (no text)")

        drag_end_features = self._extract_resnet(drag_end_bbox_image)
        if drag_end_features:
            self.logger.info("✓ DRAG end ResNet features extracted")

        return {
            'bbox': bbox_dict,
            'ocr_text': ocr_text,
            'features': features,
            'drag_end_bbox': drag_end_bbox,
            'drag_end_ocr_text': drag_end_ocr_text,
            'drag_end_features': drag_end_features
        }

    def _on_input(self, action_dict, _screenshot):
        """Handler per INPUT."""
        self.logger.info(f"✓ INPUT text: '{action_dict.get('input_text', '')}'")
        return {}

    def _on_scroll(self, action_dict, _screenshot):
        """Handler per SCROLL."""
        dx = action_dict.get('scroll_dx', 0)
        dy = action_dict.get('scroll_dy', 0)
        self.logger.info(f"✓ SCROLL: dx={dx}, dy={dy}")
        return {}

    # ==================== CALLBACKS ====================

    def _on_input_end(self):
        """Callback quando INPUT termina."""
        self.logger.info("Input ended")

    def _on_buffer_updated(self, _screenshot):
        """Callback quando buffer è aggiornato."""
        self.logger.debug("Buffer updated with new screenshot")

    def _on_buffer_ready(self):
        """Callback quando buffer è pronto per il prossimo step."""
        self.logger.debug("Buffer ready - setting UI to ready")
        self._set_ui_green()

    # ==================== CLEANUP ====================

    def _on_designer_end(self):
        """Callback quando Designer termina (ESC)."""
        self.logger.info("Designer ended (ESC pressed)")
        self.should_stop = True

    def _cleanup(self):
        """Pulisci e ferma."""
        if self.action_capture:
            self.action_capture.stop_recording()
        if self.mini_ui:
            self.mini_ui.close()
        if self.db:
            self.db.close()

        self.logger.info(f"Design session saved: {self.session_name}")
        self.logger.info(f"Total steps: {self.step_count}")


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

        # Configure logging with colored output
        setup_logging()
        logger = logging.getLogger(__name__)

        logger.info(f"Project folder: {project_folder}")
        logger.info(f"DB path: {db_path}")
        logger.info(f"Screenshots folder: {screenshots_folder}")

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
        logger.info(f"Session completed: session_id={app.session.id}")
    else:
        import tempfile
        temp_dir = tempfile.gettempdir()
        db_path = os.path.join(temp_dir, "ui_validator_designer.db")

        # Configure logging with colored output
        setup_logging()

        app = DesignerApp("test_session", db_path)
        app.start()
