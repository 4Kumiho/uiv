"""Smart BBox generation - edge detection + contour finding."""

import cv2
import numpy as np
import json


class BBoxGenerator:
    @staticmethod
    def generate_smart_bbox(screenshot: np.ndarray, click_x: int, click_y: int,
                            min_size=5, max_size=1000) -> dict:
        """
        Genera bbox intelligente attorno al click.
        REGOLE: 1) SEMPRE contiene il click point
                2) PIÙ PICCOLA POSSIBILE che lo contiene

        Ritorna: {"x": int, "y": int, "w": int, "h": int}
        """
        h, w = screenshot.shape[:2]
        gray = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)

        # Metodo 1: Canny edge detection
        edges = cv2.Canny(gray, 5, 30)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        morph = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
        dilated = cv2.dilate(morph, kernel, iterations=4)

        # Metodo 2: Adaptive threshold
        adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                        cv2.THRESH_BINARY, 15, 5)
        kernel2 = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        adaptive_dilated = cv2.dilate(adaptive, kernel2, iterations=3)

        # Metodo 3: Binary thresholds
        _, bin_dark = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY)
        _, bin_light = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
        binary_combined = cv2.bitwise_or(bin_dark, bin_light)
        binary_dilated = cv2.dilate(binary_combined, kernel2, iterations=2)

        # Combina tutti i metodi
        combined = cv2.bitwise_or(dilated, adaptive_dilated)
        combined = cv2.bitwise_or(combined, binary_dilated)

        # Trova contours
        contours, _ = cv2.findContours(combined, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        # REGOLA 1: Priorità ai contours che CONTENGONO il click
        containing_contours = []
        for contour in contours:
            x, y, cw, ch = cv2.boundingRect(contour)
            # Controlla se il click è dentro il bbox
            if x <= click_x <= x + cw and y <= click_y <= y + ch:
                # Filtra per size
                if cw >= min_size and ch >= min_size and cw <= max_size and ch <= max_size:
                    # Preferisci forme rettangolari/regolari
                    contour_area = cv2.contourArea(contour)
                    bbox_area = cw * ch
                    if bbox_area > 0:
                        fill_ratio = contour_area / bbox_area
                        # Preferisci contours che riempiono bene il bbox (non troppo sparsi)
                        if fill_ratio > 0.3:  # Almeno 30% di fill
                            area = cw * ch
                            containing_contours.append((x, y, cw, ch, area))

        if containing_contours:
            # REGOLA 2: Seleziona il più PICCOLO (minima area)
            best_contour = min(containing_contours, key=lambda b: b[4])
            x, y, cw, ch, _ = best_contour
        else:
            # Nessun contour contiene il click → corner detection
            corners = cv2.cornerHarris(gray, 2, 3, 0.04)
            corner_points = np.where(corners > 0.02 * corners.max())

            if len(corner_points[0]) > 0:
                cy, cx = corner_points
                # Filtra corners vicini al click (max 60 pixels)
                distances = (cx - click_x) ** 2 + (cy - click_y) ** 2
                nearby_idx = np.where(distances < 3600)[0]  # 60 pixels

                if len(nearby_idx) > 0:
                    nearby_cx = cx[nearby_idx]
                    nearby_cy = cy[nearby_idx]
                    x_min, x_max = nearby_cx.min(), nearby_cx.max()
                    y_min, y_max = nearby_cy.min(), nearby_cy.max()

                    # Padding minimo
                    pad = 3
                    x_min = max(0, x_min - pad)
                    y_min = max(0, y_min - pad)
                    x_max = min(w, x_max + pad)
                    y_max = min(h, y_max + pad)

                    cw = x_max - x_min
                    ch = y_max - y_min

                    if cw >= min_size and ch >= min_size:
                        x, y = x_min, y_min
                    else:
                        x, y, cw, ch = BBoxGenerator._fallback_bbox(click_x, click_y, w, h, size=25)
                else:
                    x, y, cw, ch = BBoxGenerator._fallback_bbox(click_x, click_y, w, h, size=25)
            else:
                x, y, cw, ch = BBoxGenerator._fallback_bbox(click_x, click_y, w, h, size=25)

        # Sanity check: il click DEVE essere dentro la bbox
        if not (x <= click_x <= x + cw and y <= click_y <= y + ch):
            # Se il click non è dentro, espandi il bbox per includerlo
            x_min = min(x, click_x - 10)
            x_max = max(x + cw, click_x + 10)
            y_min = min(y, click_y - 10)
            y_max = max(y + ch, click_y + 10)

            # Clamp ai bordi dell'immagine
            x_min = max(0, x_min)
            y_min = max(0, y_min)
            x_max = min(w, x_max)
            y_max = min(h, y_max)

            x = x_min
            y = y_min
            cw = x_max - x_min
            ch = y_max - y_min

        return {
            "x": int(x),
            "y": int(y),
            "w": int(cw),
            "h": int(ch)
        }

    @staticmethod
    def _fallback_bbox(click_x, click_y, w, h, size=45):
        """Fallback: bbox quadrato attorno al click."""
        x = max(0, click_x - size)
        y = max(0, click_y - size)
        cw = min(w - x, size * 2)
        ch = min(h - y, size * 2)
        return (x, y, cw, ch)

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
