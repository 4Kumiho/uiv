"""Screenshot capture e screen stability detection."""

import time
import cv2
import numpy as np
from PIL import ImageGrab


class ScreenshotHandler:
    def __init__(self, monitor_info=None):
        """
        monitor_info: dict con left, top, width, height (da mss)
                     Se None, cattura lo schermo primario
        """
        self.monitor_info = monitor_info

    def capture_full_screen(self) -> np.ndarray:
        """Cattura screenshot full-screen come BGR numpy array."""
        if self.monitor_info:
            # Usa mss per catturare il monitor specifico
            try:
                from mss import mss
                with mss() as sct:
                    screenshot = sct.grab(self.monitor_info)
                    # screenshot.rgb contiene i dati RGB come bytes
                    h, w = screenshot.height, screenshot.width
                    img_rgb = np.frombuffer(screenshot.rgb, dtype=np.uint8).reshape((h, w, 3))
                    # Converti RGB → BGR per OpenCV (flip canali)
                    img_bgr = img_rgb[:, :, ::-1]
                    return img_bgr
            except Exception:
                # Fallback a ImageGrab se mss non disponibile
                img = ImageGrab.grab()
                return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        else:
            # Default: schermo primario con ImageGrab
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
