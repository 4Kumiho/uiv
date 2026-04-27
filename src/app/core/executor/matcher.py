"""2-stage element matching algorithm: Template + OCR + ResNet."""

import os
import sys
import json
import cv2
import numpy as np
import logging

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

logger = logging.getLogger(__name__)

# Lazy imports
_feature_gen = None
_ocr_instance = None


class Matcher:
    """2-stage element matching using template, OCR, and ResNet features."""

    STAGE1_THRESHOLD = 0.70
    STAGE2_THRESHOLD = 0.60
    SEARCH_MARGIN = 150  # ±150px around original bbox in Stage 1

    def __init__(self):
        """Initialize matcher with lazy-loaded models."""
        self._feature_gen = None
        self._ocr_instance = None

    def find(self, designer_step, current_screenshot) -> dict:
        """
        Find element in current screenshot using 2-stage matching.

        Args:
            designer_step: DesignerStep object with bbox, bbox_screenshot, ocr_text, features
            current_screenshot: OpenCV image (BGR) of current screen

        Returns:
            {
                'found': bool,
                'bbox': {'x': int, 'y': int, 'w': int, 'h': int},
                'score': float (0-1),
                'stage': int (1 or 2),
                'error': str or None
            }
        """
        try:
            # Parse reference bbox and screenshot
            if not designer_step.bbox or not designer_step.bbox_screenshot:
                return {
                    'found': False,
                    'bbox': None,
                    'score': 0.0,
                    'stage': None,
                    'error': 'Missing bbox or bbox_screenshot in designer_step'
                }

            bbox_ref = json.loads(designer_step.bbox)
            crop_ref = cv2.imdecode(np.frombuffer(designer_step.bbox_screenshot, np.uint8), cv2.IMREAD_COLOR)

            if crop_ref is None or crop_ref.size == 0:
                return {
                    'found': False,
                    'bbox': None,
                    'score': 0.0,
                    'stage': None,
                    'error': 'Invalid bbox_screenshot'
                }

            # --- Stage 1: Search near original position ---
            logger.info(f"Stage 1: Searching near original bbox {bbox_ref}")
            result = self._stage1(current_screenshot, crop_ref, bbox_ref,
                                  designer_step.ocr_text, designer_step.features)
            if result['found']:
                result['stage'] = 1
                logger.info(f"Stage 1 match found at {result['bbox']} with score {result['score']:.2f}")
                return result

            # --- Stage 2: Full-screen search ---
            logger.info("Stage 1 failed, attempting Stage 2 (full-screen)")
            result = self._stage2(current_screenshot, crop_ref,
                                  designer_step.ocr_text, designer_step.features)
            result['stage'] = 2
            if result['found']:
                logger.info(f"Stage 2 match found at {result['bbox']} with score {result['score']:.2f}")
            else:
                logger.info(f"Stage 2 failed, best score: {result['score']:.2f}")
            return result

        except Exception as e:
            logger.error(f"Matcher error: {e}", exc_info=True)
            return {
                'found': False,
                'bbox': None,
                'score': 0.0,
                'stage': None,
                'error': str(e)
            }

    def _stage1(self, screen, crop_ref, bbox_orig, ocr_ref, features_ref) -> dict:
        """
        Stage 1: Template match in region ±150px around original bbox.
        Threshold: 0.70
        """
        # Extract search region
        x = max(0, bbox_orig['x'] - self.SEARCH_MARGIN)
        y = max(0, bbox_orig['y'] - self.SEARCH_MARGIN)
        w = min(screen.shape[1], bbox_orig['x'] + bbox_orig['w'] + self.SEARCH_MARGIN) - x
        h = min(screen.shape[0], bbox_orig['y'] + bbox_orig['h'] + self.SEARCH_MARGIN) - y

        region = screen[y:y+h, x:x+w]

        logger.debug(f"  Stage1 region: ({x},{y}) size=({w}x{h}), crop_ref size=({crop_ref.shape[1]}x{crop_ref.shape[0]})")

        # Template match in region
        result = self._template_match(region, crop_ref)
        if result is None:
            logger.debug(f"  Stage1: Template match failed (crop too large?)")
            return {'found': False, 'bbox': None, 'score': 0.0, 'error': 'Template match failed'}

        match_x, match_y, template_score = result
        logger.debug(f"  Stage1: Template score={template_score:.3f} at ({match_x},{match_y})")

        # Absolute coordinates
        abs_x = x + match_x
        abs_y = y + match_y

        # Full scoring
        screen_region = screen[abs_y:abs_y+crop_ref.shape[0], abs_x:abs_x+crop_ref.shape[1]]
        if screen_region.size == 0:
            return {'found': False, 'bbox': None, 'score': 0.0, 'error': 'Invalid region'}

        total_score = self._vote(screen_region, crop_ref, ocr_ref, features_ref, template_score)
        logger.debug(f"  Stage1: Total vote={total_score:.3f} (threshold={self.STAGE1_THRESHOLD})")

        if total_score >= self.STAGE1_THRESHOLD:
            return {
                'found': True,
                'bbox': {'x': abs_x, 'y': abs_y, 'w': crop_ref.shape[1], 'h': crop_ref.shape[0]},
                'score': total_score,
                'error': None
            }

        return {'found': False, 'bbox': None, 'score': total_score, 'error': None}

    def _stage2(self, screen, crop_ref, ocr_ref, features_ref) -> dict:
        """
        Stage 2: Full-screen template match.
        Threshold: 0.60
        """
        # Template match on full screen
        result = self._template_match(screen, crop_ref)
        if result is None:
            return {'found': False, 'bbox': None, 'score': 0.0, 'error': 'Template match failed'}

        match_x, match_y, template_score = result

        # Full scoring
        screen_region = screen[match_y:match_y+crop_ref.shape[0], match_x:match_x+crop_ref.shape[1]]
        if screen_region.size == 0:
            return {'found': False, 'bbox': None, 'score': 0.0, 'error': 'Invalid region'}

        total_score = self._vote(screen_region, crop_ref, ocr_ref, features_ref, template_score)

        if total_score >= self.STAGE2_THRESHOLD:
            return {
                'found': True,
                'bbox': {'x': match_x, 'y': match_y, 'w': crop_ref.shape[1], 'h': crop_ref.shape[0]},
                'score': total_score,
                'error': None
            }

        return {'found': False, 'bbox': None, 'score': total_score, 'error': None}

    def _template_match(self, screen, crop_ref):
        """
        Template matching using OpenCV.

        Returns:
            (x, y, score) or None if no match
        """
        try:
            if crop_ref.shape[0] > screen.shape[0] or crop_ref.shape[1] > screen.shape[1]:
                return None

            result = cv2.matchTemplate(screen, crop_ref, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

            return (max_loc[0], max_loc[1], max_val)
        except Exception as e:
            logger.error(f"Template match error: {e}")
            return None

    def _vote(self, screen_region, crop_ref, ocr_ref, features_ref, template_score) -> float:
        """
        Weighted voting: Template (0.4) + OCR (0.3) + ResNet (0.3).
        """
        # Template score (already normalized 0-1)
        t_score = template_score

        # OCR score
        o_score = self._ocr_score(screen_region, ocr_ref)

        # ResNet score
        r_score = self._resnet_score(screen_region, features_ref)

        total = 0.4 * t_score + 0.3 * o_score + 0.3 * r_score
        logger.debug(f"    Vote: template={t_score:.3f}(0.4) + ocr={o_score:.3f}(0.3) + resnet={r_score:.3f}(0.3) = {total:.3f}")
        return min(1.0, max(0.0, total))

    def _ocr_score(self, screen_region, ocr_ref) -> float:
        """
        OCR-based similarity score.

        Returns:
            0.0-1.0, or 0.0 if ocr_ref is empty
        """
        if not ocr_ref or ocr_ref.strip() == '':
            return 0.0

        try:
            # Lazy load EasyOCR
            global _ocr_instance
            if _ocr_instance is None:
                try:
                    import easyocr
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        _ocr_instance = easyocr.Reader(['en'], gpu=False, verbose=False)
                except Exception as e:
                    logger.warning(f"EasyOCR not available: {e}")
                    return 0.0

            reader = _ocr_instance
            results = reader.readtext(screen_region)
            detected_text = ' '.join([detection[1] for detection in results]).strip()

            if not detected_text:
                return 0.0

            # Simple similarity: check if reference text is contained or vice versa
            ref_lower = ocr_ref.lower()
            det_lower = detected_text.lower()

            if ref_lower in det_lower or det_lower in ref_lower:
                return 0.9

            # Word overlap
            ref_words = set(ref_lower.split())
            det_words = set(det_lower.split())
            if ref_words and det_words:
                overlap = len(ref_words & det_words) / len(ref_words | det_words)
                return overlap

            return 0.0

        except Exception as e:
            logger.warning(f"OCR scoring error: {e}")
            return 0.0

    def _resnet_score(self, screen_region, features_ref) -> float:
        """
        ResNet feature similarity using cosine distance.

        Returns:
            0.0-1.0
        """
        if features_ref is None:
            logger.debug(f"      ResNet: features_ref is None")
            return 0.0

        try:
            # Lazy load FeatureGenerator
            global _feature_gen
            if _feature_gen is None:
                try:
                    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'designer'))
                    from _feature_generator import FeatureGenerator
                    _feature_gen = FeatureGenerator()
                    logger.debug(f"      ResNet: Loaded FeatureGenerator")
                except Exception as e:
                    logger.warning(f"FeatureGenerator not available: {e}")
                    return 0.0

            # Extract features from screen region
            features_screen = _feature_gen.extract(screen_region)
            if features_screen is None:
                logger.debug(f"      ResNet: extract() returned None")
                return 0.0

            logger.debug(f"      ResNet: extracted {type(features_screen)} shape={getattr(features_screen, 'shape', 'N/A')}")

            # Convert features_screen to numpy array (it may come as bytes or ndarray)
            if isinstance(features_screen, bytes):
                features_screen = np.frombuffer(features_screen, dtype=np.float32).flatten()
            elif isinstance(features_screen, np.ndarray):
                features_screen = features_screen.flatten().astype(np.float32)
            else:
                logger.debug(f"      ResNet: unknown type {type(features_screen)}")
                return 0.0

            # Decode reference features
            if isinstance(features_ref, bytes):
                features_ref = np.frombuffer(features_ref, dtype=np.float32).flatten()
            elif isinstance(features_ref, np.ndarray):
                features_ref = features_ref.flatten().astype(np.float32)
            else:
                return 0.0

            # Ensure same length
            if len(features_screen) != len(features_ref):
                return 0.0

            # Cosine similarity
            dot_product = np.dot(features_screen, features_ref)
            magnitude_screen = np.linalg.norm(features_screen)
            magnitude_ref = np.linalg.norm(features_ref)

            if magnitude_screen == 0 or magnitude_ref == 0:
                return 0.0

            cosine_sim = dot_product / (magnitude_screen * magnitude_ref)
            # Map [-1, 1] to [0, 1]
            return (cosine_sim + 1.0) / 2.0

        except Exception as e:
            logger.warning(f"ResNet scoring error: {e}")
            return 0.0
