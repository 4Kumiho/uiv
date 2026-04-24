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
        Usa edge detection, adaptive thresholding, e corner detection.

        Ritorna: {"x": int, "y": int, "w": int, "h": int}
        """
        h, w = screenshot.shape[:2]

        # Converte a grayscale
        gray = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)

        # Metodo 1: Canny ultra-sensibile per bordi
        edges = cv2.Canny(gray, 5, 30)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        morph = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
        dilated = cv2.dilate(morph, kernel, iterations=4)

        # Metodo 2: Adaptive threshold (sensibile ai contrasti locali)
        adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                        cv2.THRESH_BINARY, 15, 5)
        kernel2 = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        adaptive_dilated = cv2.dilate(adaptive, kernel2, iterations=3)

        # Metodo 3: Multiple binary thresholds
        _, bin_dark = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY)
        _, bin_light = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
        binary_combined = cv2.bitwise_or(bin_dark, bin_light)
        binary_dilated = cv2.dilate(binary_combined, kernel2, iterations=2)

        # Combina tutti i metodi
        combined = cv2.bitwise_or(dilated, adaptive_dilated)
        combined = cv2.bitwise_or(combined, binary_dilated)

        # Trova contours
        contours, _ = cv2.findContours(combined, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        # Passo 1: trova bbox che contengono il click
        containing_contours = []
        for contour in contours:
            x, y, cw, ch = cv2.boundingRect(contour)
            if x <= click_x <= x + cw and y <= click_y <= y + ch:
                if cw >= min_size and ch >= min_size and cw <= max_size and ch <= max_size:
                    containing_contours.append((x, y, cw, ch))

        if containing_contours:
            best_contour = min(containing_contours, key=lambda b: b[2] * b[3])
        else:
            # Passo 2: cerca il contorno più vicino (senza restrizioni di size)
            closest_contour = None
            min_distance = float('inf')

            for contour in contours:
                x, y, cw, ch = cv2.boundingRect(contour)
                if cw < 3 or ch < 3:  # Molto permissivo
                    continue

                bbox_cx = x + cw // 2
                bbox_cy = y + ch // 2
                distance = (bbox_cx - click_x) ** 2 + (bbox_cy - click_y) ** 2

                if distance < min_distance:
                    min_distance = distance
                    closest_contour = (x, y, cw, ch)

            if closest_contour and min_distance < 10000:  # Max distance ~100 pixels
                best_contour = closest_contour
            else:
                # Passo 3: corner detection (Harris corners) - molto restrittivo
                corners = cv2.cornerHarris(gray, 2, 3, 0.04)
                corner_points = np.where(corners > 0.02 * corners.max())  # Soglia più alta

                if len(corner_points[0]) > 0:
                    cy, cx = corner_points
                    # Filtra corners MOLTO vicini al click (max 50 pixels)
                    distances = (cx - click_x) ** 2 + (cy - click_y) ** 2
                    nearby_idx = np.where(distances < 2500)[0]  # 50 pixels max

                    if len(nearby_idx) > 0:
                        nearby_cx = cx[nearby_idx]
                        nearby_cy = cy[nearby_idx]
                        x_min, x_max = nearby_cx.min(), nearby_cx.max()
                        y_min, y_max = nearby_cy.min(), nearby_cy.max()

                        # Padding minimo per mantenere bbox tight
                        pad = 2
                        x_min = max(0, x_min - pad)
                        y_min = max(0, y_min - pad)
                        x_max = min(w, x_max + pad)
                        y_max = min(h, y_max + pad)

                        cw = x_max - x_min
                        ch = y_max - y_min

                        if cw > min_size and ch > min_size:
                            best_contour = (x_min, y_min, cw, ch)
                        else:
                            best_contour = BBoxGenerator._fallback_bbox(click_x, click_y, w, h)
                    else:
                        best_contour = BBoxGenerator._fallback_bbox(click_x, click_y, w, h)
                else:
                    # Passo 4: fallback
                    best_contour = BBoxGenerator._fallback_bbox(click_x, click_y, w, h)

        x, y, cw, ch = best_contour

        # Sanity check: se il bbox è troppo grande (>40% dello schermo), usa fallback
        bbox_area = cw * ch
        screen_area = h * w
        if bbox_area > 0.4 * screen_area:
            x, y, cw, ch = BBoxGenerator._fallback_bbox(click_x, click_y, w, h)

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
