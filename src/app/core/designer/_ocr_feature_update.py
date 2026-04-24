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

from _ocr_generator import OCRGenerator
from _feature_generator import FeatureGenerator
from _bbox_generator import BBoxGenerator
from logging_config import setup_logging

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


def process_bbox(screenshot_path: str, bbox_json: str):
    """Process a bbox: extract OCR and ResNet features."""
    try:
        # Load image
        bgr = cv2.imread(screenshot_path)
        if bgr is None:
            logger.error("Could not load image")
            return json.dumps({"error": "Could not load image"})

        # Parse bbox
        bbox = json.loads(bbox_json)
        if not bbox or 'x' not in bbox:
            logger.error("Invalid bbox")
            return json.dumps({"error": "Invalid bbox"})

        # Crop to bbox
        bbox_image = BBoxGenerator.crop_image(bgr, bbox)
        if bbox_image is None or bbox_image.size == 0:
            logger.error("Could not crop bbox")
            return json.dumps({"error": "Could not crop bbox"})

        # Extract OCR
        logger.debug("Extracting OCR...")
        ocr_gen = OCRGenerator()
        ocr_text = ocr_gen.extract(bbox_image)

        # Extract ResNet features
        logger.debug("Extracting ResNet features...")
        feature_gen = FeatureGenerator()
        features = feature_gen.extract(bbox_image)

        # Return results
        # Handle different feature formats
        if isinstance(features, np.ndarray):
            features_out = features.astype(np.float32).tobytes().hex()
        elif isinstance(features, bytes):
            features_out = features.hex()  # Convert bytes to hex string
        else:
            features_out = features

        result = {
            "ocr_text": ocr_text or "",
            "features": features_out
        }
        logger.info("OCR/ResNet extraction completed")
        return json.dumps(result)

    except Exception as e:
        logger.error(f"Exception in process_bbox: {e}")
        return json.dumps({"error": str(e)})


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        screenshot_path = sys.argv[1]
        bbox_json = sys.argv[2]
        result = process_bbox(screenshot_path, bbox_json)
        print(result)
    else:
        print(json.dumps({"error": "Missing arguments"}))
