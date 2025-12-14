"""Tesseract OCR extraction for documents.

Local OCR using Tesseract - no API costs, works offline.

Requires:
    - tesseract-ocr: apt install tesseract-ocr
    - pytesseract: pip install pytesseract
    - pillow: pip install Pillow

Usage:
    from document_processor.extractors.tesseract_ocr import TesseractExtractor

    extractor = TesseractExtractor()
    result = await extractor.extract_text(Path("document.png"))

    print(result['extracted_text'])
    print(result['confidence'])
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional
import hashlib
import json

from shared.config import Settings

logger = logging.getLogger(__name__)


class TesseractExtractor:
    """Extract text from images using Tesseract OCR.

    Local OCR - no API costs, works offline.
    """

    def __init__(
        self,
        tesseract_cmd: Optional[str] = None,
        lang: Optional[str] = None,
        enable_cache: Optional[bool] = None
    ):
        """Initialize Tesseract extractor.

        Args:
            tesseract_cmd: Path to tesseract binary (optional)
            lang: Language model to use (default: "eng")
            enable_cache: Enable result caching (uses config default if None)
        """
        settings = Settings()

        # Set tesseract command path if specified
        self.tesseract_cmd = tesseract_cmd or settings.tesseract_cmd
        self.lang = lang or settings.tesseract_lang

        # Cache settings
        if enable_cache is None:
            enable_cache = settings.aws_cache_enabled
        self._cache_enabled = enable_cache
        self._cache_dir = settings.documents_path.parent / "cache" / "tesseract"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        # Import and configure pytesseract
        try:
            import pytesseract
            self._pytesseract = pytesseract

            if self.tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd

            logger.info(f"TesseractExtractor initialized (lang: {self.lang}, cache: {enable_cache})")

        except ImportError:
            raise ImportError(
                "pytesseract is required for Tesseract OCR. "
                "Install with: pip install pytesseract pillow"
            )

    def _get_cached(self, image_hash: str) -> Optional[Dict]:
        """Get cached result if available."""
        if not self._cache_enabled:
            return None

        cache_file = self._cache_dir / f"{image_hash}.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                logger.debug(f"Tesseract cache hit: {image_hash[:8]}")
                return data
            except Exception as e:
                logger.debug(f"Cache read error: {e}")
                cache_file.unlink(missing_ok=True)
        return None

    def _set_cached(self, image_hash: str, result: Dict) -> None:
        """Cache a result."""
        if not self._cache_enabled:
            return

        cache_file = self._cache_dir / f"{image_hash}.json"
        try:
            with open(cache_file, 'w') as f:
                json.dump(result, f, indent=2)
            logger.debug(f"Tesseract cache save: {image_hash[:8]}")
        except Exception as e:
            logger.debug(f"Cache write error: {e}")

    async def extract_text(self, image_path: Path) -> Dict[str, Any]:
        """Extract text from an image using Tesseract.

        Args:
            image_path: Path to the image file

        Returns:
            Dictionary containing:
                - extracted_text: str - The extracted text content
                - confidence: float - Average confidence score (0-1)
                - blocks: dict - Empty (Tesseract doesn't provide block data in simple mode)
                - metadata: dict - Additional metadata
                - cached: bool - Whether response was from cache
        """
        try:
            from PIL import Image

            # Read image and compute hash for caching
            with open(image_path, 'rb') as f:
                image_bytes = f.read()
            image_hash = hashlib.sha256(image_bytes).hexdigest()

            # Check cache
            if self._cache_enabled:
                cached = self._get_cached(image_hash)
                if cached:
                    cached['cached'] = True
                    return cached

            # Open image with PIL
            image = Image.open(image_path)

            # Get detailed OCR data with confidence scores
            ocr_data = self._pytesseract.image_to_data(
                image,
                lang=self.lang,
                output_type=self._pytesseract.Output.DICT
            )

            # Extract text (simple method for clean output)
            extracted_text = self._pytesseract.image_to_string(
                image,
                lang=self.lang
            )

            # Calculate average confidence from word-level data
            confidences = [
                c for c in ocr_data['conf']
                if isinstance(c, (int, float)) and c >= 0
            ]
            avg_confidence = (sum(confidences) / len(confidences) / 100) if confidences else 0

            # Count words and lines
            word_count = len([w for w in ocr_data['text'] if w.strip()])
            line_count = len(set(ocr_data['line_num'])) if ocr_data['line_num'] else 0

            result = {
                'extracted_text': extracted_text.strip(),
                'confidence': avg_confidence,
                'blocks': {'PAGE': [], 'LINE': [], 'WORD': []},  # Simplified - no block data
                'metadata': {
                    'extractor': 'tesseract',
                    'language': self.lang,
                    'pages': 1,
                    'lines_detected': line_count,
                    'words_detected': word_count,
                    'file_size': len(image_bytes),
                    'image_format': image_path.suffix.lower(),
                    'image_size': f"{image.width}x{image.height}"
                },
                'cached': False
            }

            # Cache result
            if self._cache_enabled:
                self._set_cached(image_hash, result)

            logger.info(
                f"Tesseract OCR complete: {word_count} words, "
                f"{avg_confidence:.1%} confidence"
            )

            return result

        except Exception as e:
            logger.error(f"Tesseract OCR failed: {e}")
            raise RuntimeError(f"Failed to extract text with Tesseract: {e}") from e

    def validate_installation(self) -> bool:
        """Check if Tesseract is properly installed.

        Returns:
            True if Tesseract is available, False otherwise
        """
        try:
            version = self._pytesseract.get_tesseract_version()
            logger.info(f"Tesseract version: {version}")
            return True
        except Exception as e:
            logger.error(f"Tesseract not available: {e}")
            return False
