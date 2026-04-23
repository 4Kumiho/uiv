"""Screenshot capture e screen stability detection."""

import time
import cv2
import numpy as np
from PIL import ImageGrab


class ScreenshotHandler:
    def capture_full_screen(self) -> np.ndarray:
        """Cattura screenshot full-screen come BGR numpy array."""
        img = ImageGrab.grab()
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    def wait_for_screen_stability(self, timeout_ms=3000, check_interval_ms=100) -> np.ndarray:
        """
        Aspetta che schermo si stabilizzi (pixel diff < 2%).
        Ritorna screenshot stabile.
        """
        start_time = time.time()
        prev_screenshot = None

        while (time.time() - start_time) < (timeout_ms / 1000):
            current = self.capture_full_screen()

            if prev_screenshot is not None:
                # Confronta pixel
                diff = cv2.absdiff(prev_screenshot, current)
                changed_pixels = np.count_nonzero(diff) / diff.size

                if changed_pixels < 0.02:  # < 2% cambiamento
                    return current

            prev_screenshot = current
            time.sleep(check_interval_ms / 1000)

        # Timeout: ritorna ultimo screenshot
        return current
