"""Video recording using OpenCV VideoWriter."""

import os
import sys
import time
import cv2
import logging
import threading
import numpy as np

try:
    from mss import mss
    HAS_MSS = True
except ImportError:
    from PIL import ImageGrab
    HAS_MSS = False

logger = logging.getLogger(__name__)


class VideoRecorder:
    """Screen recorder using OpenCV VideoWriter."""

    def __init__(self, output_path: str, monitor_info: dict):
        """
        Initialize video recorder.

        Args:
            output_path: Full path to output .mp4 file
            monitor_info: Dict with keys: 'left', 'top', 'width', 'height'
        """
        self._output = output_path
        self._monitor = monitor_info
        self._writer = None
        self._start_time = None
        self._running = False
        self._thread = None
        self._frame_count = 0

    def start(self):
        """Start recording in background thread."""
        try:
            logger.info(f"Starting video recording to {self._output}")

            # Ensure output directory exists
            os.makedirs(os.path.dirname(self._output), exist_ok=True)

            # Initialize VideoWriter
            width = self._monitor['width']
            height = self._monitor['height']
            fps = 10
            # Use MJPEG codec which is more widely supported
            fourcc = cv2.VideoWriter_fourcc(*'MJPG')

            self._writer = cv2.VideoWriter(
                self._output,
                fourcc,
                fps,
                (width, height)
            )

            if not self._writer.isOpened():
                raise RuntimeError("Failed to open VideoWriter")

            self._start_time = time.time()
            self._running = True
            self._frame_count = 0

            # Start capture thread
            self._thread = threading.Thread(target=self._capture_frames, daemon=True)
            self._thread.start()

            logger.info("Video recording started")
        except Exception as e:
            logger.error(f"Failed to start video recording: {e}")
            raise

    def _capture_frames(self):
        """Capture frames from screen in loop."""
        try:
            if HAS_MSS:
                self._capture_frames_mss()
            else:
                self._capture_frames_pil()
        except Exception as e:
            logger.error(f"Capture thread error: {e}")
        finally:
            logger.debug(f"Capture thread exiting after {self._frame_count} frames")

    def _capture_frames_mss(self):
        """Capture frames using mss (supports multi-monitor with offsets)."""
        with mss() as sct:
            # Create monitor dict compatible with mss
            mon = {
                'left': self._monitor['left'],
                'top': self._monitor['top'],
                'width': self._monitor['width'],
                'height': self._monitor['height']
            }

            while self._running:
                try:
                    screenshot = sct.grab(mon)
                    # mss returns BGRA, convert to BGR
                    frame_bgr = np.array(screenshot)[:, :, :3]
                    self._writer.write(frame_bgr)
                    self._frame_count += 1
                    time.sleep(0.1)
                except Exception as e:
                    logger.warning(f"Frame capture error (mss): {e}")
                    time.sleep(0.1)

    def _capture_frames_pil(self):
        """Capture frames using PIL ImageGrab (fallback for single monitor)."""
        while self._running:
            try:
                left = self._monitor['left']
                top = self._monitor['top']
                width = self._monitor['width']
                height = self._monitor['height']

                bbox = (left, top, left + width, top + height)
                frame_pil = ImageGrab.grab(bbox=bbox)

                frame_np = np.array(frame_pil)
                frame_bgr = cv2.cvtColor(frame_np, cv2.COLOR_RGB2BGR)

                self._writer.write(frame_bgr)
                self._frame_count += 1

                time.sleep(0.1)
            except Exception as e:
                logger.warning(f"Frame capture error (PIL): {e}")
                time.sleep(0.1)

    def get_timestamp(self) -> float:
        """Get seconds elapsed since recording start."""
        if self._start_time is None:
            return 0.0
        return time.time() - self._start_time

    def stop(self):
        """Stop recording gracefully."""
        if not self._running:
            logger.warning("Video recorder not running")
            return

        try:
            logger.info("Stopping video recording")
            self._running = False

            # Wait for capture thread to finish
            if self._thread:
                self._thread.join(timeout=5)

            # Release writer
            if self._writer:
                self._writer.release()

            logger.info(f"Video saved to {self._output} ({self._frame_count} frames)")
        except Exception as e:
            logger.error(f"Error stopping video recording: {e}")
