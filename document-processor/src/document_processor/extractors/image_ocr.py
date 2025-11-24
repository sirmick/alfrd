"""Image text extraction using Claude Vision API."""

import anthropic
import base64
from pathlib import Path
from typing import Dict
import sys

# Add parent directories to path for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from shared.constants import DEFAULT_MODEL, MAX_TOKENS


class ClaudeVisionExtractor:
    """Extract text from images using Claude Vision API."""
    
    def __init__(self, api_key: str):
        """
        Initialize the Claude Vision extractor.
        
        Args:
            api_key: Anthropic API key
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = DEFAULT_MODEL
    
    async def extract_text(self, image_path: Path) -> Dict:
        """
        Extract text from image using Claude vision.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Dictionary with extracted_text, confidence, and metadata
        """
        # Read and encode image
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
        
        # Determine media type
        suffix = image_path.suffix.lower()
        media_type_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp"
        }
        media_type = media_type_map.get(suffix, "image/jpeg")
        
        try:
            # Call Claude vision API
            message = self.client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_data
                                }
                            },
                            {
                                "type": "text",
                                "text": """Extract all text from this document image.

Provide:
1. The complete extracted text (maintain formatting/structure)
2. Document type (bill, receipt, form, letter, etc.)
3. Key information visible (amounts, dates, company names)
4. Any damage/quality issues affecting readability

Format as JSON with keys: extracted_text, document_type, key_info, quality_notes"""
                            }
                        ]
                    }
                ]
            )
            
            # Parse response
            response_text = message.content[0].text
            
            # For MVP, return simple structure
            # TODO: Parse JSON response in future iteration
            return {
                "extracted_text": response_text,
                "confidence": 0.9,  # Claude is generally high confidence
                "metadata": {
                    "model": self.model,
                    "image_format": media_type,
                    "tokens_used": message.usage.input_tokens + message.usage.output_tokens
                }
            }
            
        except Exception as e:
            return {
                "extracted_text": "",
                "confidence": 0.0,
                "metadata": {
                    "error": str(e),
                    "model": self.model,
                    "image_format": media_type
                }
            }