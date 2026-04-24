"""OCR text extraction using EasyOCR."""

import logging

logger = logging.getLogger(__name__)


class OCRGenerator:
    """Estrae testo dal bbox usando EasyOCR."""

    def __init__(self):
        self._ocr_reader = None

    def extract(self, bbox_image):
        """Estrae testo dal bbox image."""
        try:
            import easyocr

            if self._ocr_reader is None:
                logger.info("Initializing EasyOCR reader...")
                self._ocr_reader = easyocr.Reader(['en'], gpu=False)

            results = self._ocr_reader.readtext(bbox_image)
            text = ' '.join([detection[1] for detection in results])
            return text.strip() if text else ""
        except Exception as e:
            logger.error(f"OCR error: {e}")
            return ""
