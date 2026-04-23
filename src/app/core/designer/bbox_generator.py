"""Smart BBox generation - edge detection + contour finding."""

import cv2
import numpy as np
import json


class BBoxGenerator:
    @staticmethod
    def generate_smart_bbox(screenshot: np.ndarray, click_x: int, click_y: int,
                            min_size=20, max_size=300) -> dict:
        """
        Genera bbox intelligente attorno al click.
        Usa edge detection per trovare i confini dell'elemento.

        Ritorna: {"x": int, "y": int, "w": int, "h": int}
        """
        h, w = screenshot.shape[:2]

        # Converte a grayscale
        gray = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)

        # Edge detection
        edges = cv2.Canny(gray, 100, 200)

        # Dilata per connettere edge vicini
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        dilated = cv2.dilate(edges, kernel, iterations=2)

        # Trova contours
        contours, _ = cv2.findContours(dilated, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        # Trova il contour più vicino al click point
        best_contour = None
        best_distance = float('inf')

        for contour in contours:
            x, y, cw, ch = cv2.boundingRect(contour)

            # Controlla se il click è dentro il bbox
            if x <= click_x <= x + cw and y <= click_y <= y + ch:
                if cw >= min_size and ch >= min_size and cw <= max_size and ch <= max_size:
                    best_contour = (x, y, cw, ch)
                    break

            # Altrimenti prendi il più vicino
            dist = ((x + cw/2 - click_x)**2 + (y + ch/2 - click_y)**2)**0.5
            if dist < best_distance and cw >= min_size and ch >= min_size and cw <= max_size and ch <= max_size:
                best_distance = dist
                best_contour = (x, y, cw, ch)

        # Se non trova con contours, crea un bbox generico attorno al click
        if best_contour is None:
            size = 50
            x = max(0, click_x - size)
            y = max(0, click_y - size)
            cw = min(w - x, size * 2)
            ch = min(h - y, size * 2)
            best_contour = (x, y, cw, ch)

        x, y, cw, ch = best_contour
        return {
            "x": int(x),
            "y": int(y),
            "w": int(cw),
            "h": int(ch)
        }

    @staticmethod
    def bbox_to_json(bbox: dict) -> str:
        """Converte bbox dict a JSON string."""
        return json.dumps(bbox)

    @staticmethod
    def json_to_bbox(json_str: str) -> dict:
        """Converte JSON string a bbox dict."""
        return json.loads(json_str)

    @staticmethod
    def crop_image(screenshot: np.ndarray, bbox: dict) -> np.ndarray:
        """Ritorna il crop dell'immagine secondo il bbox."""
        x, y, w, h = bbox["x"], bbox["y"], bbox["w"], bbox["h"]
        return screenshot[y:y+h, x:x+w]
