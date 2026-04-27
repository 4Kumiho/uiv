"""OCR and ResNet worker process - runs OCR and ResNet on a bbox region."""

import sys
import os
import json
import cv2
import numpy as np
import logging

# Setup path for imports
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

# Lazy imports
FeatureGenerator = None
BBoxGenerator = None

# Setup logging
try:
    from logging_config import setup_logging
    setup_logging()
except:
    pass

logger = logging.getLogger(__name__)


def process_bbox(screenshot_path: str, bbox_json: str):
    """Process a bbox: extract OCR and ResNet features."""
    try:
        # Load image
        bgr = cv2.imread(screenshot_path)
        if bgr is None:
            print(json.dumps({"error": "Could not load image"}), flush=True)
            return

        # Parse bbox
        bbox = json.loads(bbox_json)
        if not bbox or 'x' not in bbox:
            print(json.dumps({"error": "Invalid bbox"}), flush=True)
            return

        # Crop to bbox
        if BBoxGenerator is None:
            from _bbox_generator import BBoxGenerator as BBoxGen
            globals()['BBoxGenerator'] = BBoxGen
        bbox_image = BBoxGenerator.crop_image(bgr, bbox)
        if bbox_image is None or bbox_image.size == 0:
            print(json.dumps({"error": "Could not crop bbox"}), flush=True)
            return

        # Extract OCR
        ocr_text = ""
        try:
            import easyocr
            if not hasattr(easyocr, '_ocr_instance'):
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    easyocr._ocr_instance = easyocr.Reader(['en'], gpu=False, verbose=False)
            reader = easyocr._ocr_instance
            results = reader.readtext(bbox_image)
            ocr_text = ' '.join([detection[1] for detection in results]).strip()
        except Exception as ocr_err:
            logger.error(f"OCR extraction failed: {ocr_err}")
            ocr_text = ""

        # Extract ResNet features
        features = None
        try:
            if not hasattr(process_bbox, '_feature_gen'):
                if FeatureGenerator is None:
                    from _feature_generator import FeatureGenerator as FG
                    globals()['FeatureGenerator'] = FG
                process_bbox._feature_gen = FeatureGenerator()
            features = process_bbox._feature_gen.extract(bbox_image)
        except Exception as feat_err:
            logger.error(f"ResNet extraction failed: {feat_err}")
            features = None

        # Encode bbox crop as PNG hex for JSON transport
        bbox_screenshot_hex = ""
        try:
            _, buf = cv2.imencode('.png', bbox_image)
            bbox_screenshot_hex = buf.tobytes().hex()
        except Exception as e:
            logger.error(f"Failed to encode bbox_screenshot: {e}")

        # Return results
        if isinstance(features, np.ndarray):
            features_out = features.astype(np.float32).tobytes().hex()
        elif isinstance(features, bytes):
            features_out = features.hex()
        else:
            features_out = features

        result = {
            "ocr_text": ocr_text or "",
            "features": features_out,
            "bbox_screenshot": bbox_screenshot_hex
        }
        output_json = json.dumps(result)
        print(output_json, flush=True)
        sys.stdout.flush()

    except Exception as e:
        logger.error(f"Exception in process_bbox: {e}")
        error_json = json.dumps({"error": str(e)})
        print(error_json, flush=True)
        sys.stdout.flush()


if __name__ == "__main__":
    try:
        if len(sys.argv) >= 3:
            screenshot_path = sys.argv[1]
            bbox_json = sys.argv[2]
            process_bbox(screenshot_path, bbox_json)
        else:
            print(json.dumps({"error": "Missing arguments"}), flush=True)
    except Exception as e:
        print(json.dumps({"error": f"Subprocess error: {str(e)}"}), flush=True)
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
