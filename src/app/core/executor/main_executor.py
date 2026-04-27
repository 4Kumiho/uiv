"""Main Executor - Execution orchestration."""

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
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'designer'))

from src.app.core.designer.screenshot_handler import ScreenshotHandler
from src.app.core.executor.matcher import Matcher
from src.app.core.executor.action_executor import ActionExecutor
from src.app.core.executor.video_recorder import VideoRecorder
from src.app.core.designer.mini_ui import MiniUI
from src.app.core.database.executor_db import ExecutorDatabase
from src.app.core.database.designer_db import DesignerDatabase
from src.app.core.database.models import ExecutionStep
from src.app.core.utils.logging_config import setup_logging

# Setup logging
try:
    setup_logging(mode='EXECUTOR')
except:
    pass

logger = logging.getLogger(__name__)


class ExecutorApp:
    def __init__(self, session_name: str, designer_db_path: str, output_folder: str, monitor_num: int = 0):
        self.session_name = session_name
        self.designer_db_path = designer_db_path
        self.output_folder = output_folder
        self.monitor_num = monitor_num

        # Derived paths
        self.session_folder = os.path.join(output_folder, session_name)
        self.executor_db_path = os.path.join(self.session_folder, "execution.db")
        self.video_path = os.path.join(self.session_folder, "execution.mp4")
        self.done_signal_path = os.path.join(self.session_folder, "execution_done.json")

        # State
        self.designer_db = None
        self.executor_db = None
        self.session = None
        self.mini_ui = None
        self.should_stop = False
        self.monitor_info = None
        self.screenshot_handler = None
        self.matcher = None
        self.action_executor = None
        self.video_recorder = None
        self.designer_session = None
        self.designer_steps = None

        self.logger = logger

    def start(self):
        """Avvia l'executor."""
        try:
            self.logger.info(f"Starting session: {self.session_name}")

            # 1. Create session folder
            os.makedirs(self.session_folder, exist_ok=True)

            # 2. Load designer DB and session
            self.designer_db = DesignerDatabase(self.designer_db_path)
            designer_db_obj = self.designer_db.get_session(1)
            if not designer_db_obj:
                raise RuntimeError("No designer session found in DB")

            self.designer_session = designer_db_obj
            self.designer_steps = self.designer_db.get_steps(designer_db_obj.id)
            self.logger.debug(f"Loaded {len(self.designer_steps)} designer steps")

            # 3. Create executor DB and session
            self.executor_db = ExecutorDatabase(self.executor_db_path)
            self.session = self.executor_db.create_session(
                self.session_name,
                designer_db_path=self.designer_db_path,
                designer_session_id=designer_db_obj.id
            )
            self.logger.debug(f"Session ID: {self.session.id}")

            # 4. Get monitor info
            self._get_monitor_info()

            # 5. Setup components
            self.screenshot_handler = ScreenshotHandler(self.monitor_info)
            self.matcher = Matcher()
            self.action_executor = ActionExecutor(self.monitor_info)
            self.video_recorder = VideoRecorder(self.video_path, self.monitor_info)

            # 6. Show Mini UI
            self.mini_ui = MiniUI(
                mode='EXECUTOR',
                on_end_callback=self._on_stop,
                monitor_info=self.monitor_info
            )
            self.mini_ui.update()
            time.sleep(0.3)

            # 7. Preload models
            self._preload_models()

            # 8. Start video recording
            self.video_recorder.start()

            # Set ready state
            self.mini_ui.set_ready()
            self.logger.info("Ready - Beginning execution")

            # 9. Main execution loop
            self._execute_steps()

            # 10. Finalize
            self._finalize()

        except Exception as e:
            self.logger.error(f"Executor error: {e}", exc_info=True)
            self._write_done_signal('FAILED')
            sys.exit(1)

    def _get_monitor_info(self):
        """Get monitor information."""
        try:
            from mss import mss
            with mss() as sct:
                monitors = sct.monitors[1:]  # Skip meta-monitor
                if self.monitor_num < len(monitors):
                    self.monitor_info = monitors[self.monitor_num]
                else:
                    self.monitor_info = monitors[0]
                    self.logger.warning(f"Monitor {self.monitor_num} not found, using monitor 0")

            self.logger.info(f"Monitor: {self.monitor_info['width']}x{self.monitor_info['height']} "
                           f"@ ({self.monitor_info['left']}, {self.monitor_info['top']})")

            # Move mouse to center of chosen monitor
            center_x = self.monitor_info['left'] + self.monitor_info['width'] // 2
            center_y = self.monitor_info['top'] + self.monitor_info['height'] // 2
            from pynput.mouse import Controller
            mouse = Controller()
            mouse.position = (center_x, center_y)
            self.logger.info(f"Moved mouse to center of monitor: ({center_x}, {center_y})")
        except Exception as e:
            self.logger.error(f"Error getting monitor info: {e}")
            raise

    def _preload_models(self):
        """Preload OCR and ResNet models."""
        try:
            # Force lazy-load in matcher
            _ = self.matcher._ocr_score(cv2.imread(os.devnull) or cv2.cvtColor(__import__('numpy').zeros((10, 10, 3), dtype='uint8'), cv2.COLOR_BGR2RGB), "test")
        except:
            pass  # OCR may not be available

        try:
            # Trigger ResNet lazy-load
            dummy = cv2.cvtColor(__import__('numpy').zeros((100, 100, 3), dtype='uint8'), cv2.COLOR_BGR2RGB)
            _ = self.matcher._resnet_score(dummy, None)
        except:
            pass  # ResNet may not be available

    def _execute_steps(self):
        """Main execution loop."""
        for i, designer_step in enumerate(self.designer_steps):
            step_num = i + 1
            total_steps = len(self.designer_steps)
            self.mini_ui.set_step(step_num)

            if self.should_stop:
                self.logger.info(f"Step {step_num}/{total_steps}: STOPPED")
                self._save_step(designer_step, 'STOPPED', error_msg="Stopped by user")
                continue

            try:
                self.logger.info(f"Step {step_num}/{total_steps}: {designer_step.action_type}")
                self.mini_ui.set_saving()

                # 1. Capture current screenshot
                screenshot = self.screenshot_handler.capture_full_screen()

                # 2. Match element
                match = self.matcher.find(designer_step, screenshot)

                if match['found']:
                    self.logger.info(f"  ✓ Match found (stage {match['stage']}, score {match['score']:.2f})")

                    # 3. Execute action
                    try:
                        self.action_executor.execute(designer_step, match['bbox'])

                        # 4. Wait for screen to stabilize (5 seconds timeout for UI changes)
                        screenshot_after = self.screenshot_handler.wait_for_screen_stability(timeout_ms=5000)

                        # 5. Save step as PASS
                        _, buf = cv2.imencode('.png', screenshot_after)
                        self._save_step(
                            designer_step,
                            'PASS',
                            match_score=match['score'],
                            match_stage=match['stage'],
                            matched_bbox=match['bbox'],
                            screenshot_after=buf.tobytes(),
                            video_timestamp=self.video_recorder.get_timestamp()
                        )
                        self.logger.info(f"  SUCCESS")
                    except Exception as e:
                        self.logger.error(f"  ✗ Action execution failed: {e}")
                        self._save_step(
                            designer_step,
                            'FAIL',
                            match_score=match['score'],
                            match_stage=match['stage'],
                            matched_bbox=match['bbox'],
                            error_msg=f"Action execution failed: {str(e)}",
                            video_timestamp=self.video_recorder.get_timestamp()
                        )
                        self.logger.info(f"  FAIL")
                else:
                    self.logger.info(f"  ✗ No match found (score {match['score']:.2f})")
                    self._save_step(
                        designer_step,
                        'FAIL',
                        match_score=match['score'],
                        error_msg=match['error'] or "Element not found",
                        video_timestamp=self.video_recorder.get_timestamp()
                    )
                    self.logger.info(f"  FAIL")

                self.mini_ui.set_ready()

            except Exception as e:
                self.logger.error(f"Step {step_num}/{total_steps} error: {e}", exc_info=True)
                self._save_step(designer_step, 'FAIL', error_msg=str(e))
                self.logger.info(f"  FAIL")
                self.mini_ui.set_ready()

    def _save_step(self, designer_step, status: str, match_score=None, match_stage=None,
                   matched_bbox=None, screenshot_after=None, video_timestamp=None, error_msg=None):
        """Save execution step to DB."""
        try:
            step = ExecutionStep(
                designer_step_id=designer_step.id,
                step_number=designer_step.step_number,
                action_type=designer_step.action_type,
                status=status,
                match_score=match_score,
                match_stage=match_stage,
                matched_bbox=json.dumps(matched_bbox) if matched_bbox else None,
                screenshot_after=screenshot_after,
                video_timestamp=video_timestamp,
                error_msg=error_msg
            )
            self.executor_db.add_step(self.session.id, step)
        except Exception as e:
            self.logger.error(f"Error saving step: {e}")

    def _finalize(self):
        """Finalize execution."""
        # Stop video recording
        try:
            self.video_recorder.stop()
            self.logger.debug(f"Video saved to {self.video_path}")
        except Exception as e:
            self.logger.error(f"Error stopping video: {e}")

        # Update session status
        try:
            self.executor_db.update_session_status(
                self.session.id,
                'STOPPED' if self.should_stop else 'COMPLETED',
                video_path=self.video_path
            )
        except Exception as e:
            self.logger.error(f"Error updating session status: {e}")

        # Close databases
        try:
            self.executor_db.close()
            self.designer_db.close()
        except Exception as e:
            self.logger.error(f"Error closing databases: {e}")

        # Write done signal
        self._write_done_signal('STOPPED' if self.should_stop else 'COMPLETED')

    def _write_done_signal(self, status: str):
        """Write execution_done.json signal file."""
        try:
            os.makedirs(self.session_folder, exist_ok=True)
            signal = {
                "execution_id": self.session.id if self.session else None,
                "db_path": self.executor_db_path,
                "video_path": self.video_path,
                "status": status
            }
            with open(self.done_signal_path, 'w') as f:
                json.dump(signal, f, indent=2)
            self.logger.info(f"Signal written to {self.done_signal_path}")
        except Exception as e:
            self.logger.error(f"Error writing done signal: {e}")

    def _on_stop(self):
        """Callback when ESC is pressed."""
        self.logger.info("Stop signal received (ESC pressed)")
        self.should_stop = True


if __name__ == "__main__":
    if len(sys.argv) >= 4:
        session_name = sys.argv[1]
        designer_db_path = sys.argv[2]
        output_folder = sys.argv[3]
        monitor_num = int(sys.argv[4]) if len(sys.argv) > 4 else 0

        app = ExecutorApp(session_name, designer_db_path, output_folder, monitor_num)
        app.start()
    else:
        print("Usage: python main_executor.py <session_name> <designer_db_path> <output_folder> [monitor_num]")
        sys.exit(1)
