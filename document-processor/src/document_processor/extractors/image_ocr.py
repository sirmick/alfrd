"""Image OCR extraction using Claude Vision API."""

import anthropic
import base64
from pathlib import Path
from typing import Dict
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from shared.constants import CLAUDE_VISION_MODEL, CLAUDE_MAX_TOKENS, MIME_TYPE_MAP


class ClaudeVisionExtractor:
    """Extract text from images using Claude Vision API."""
    
    def __init__(self, api_key: str):
        """
        Initialize the Claude Vision extractor.
        
        Args:
            api_key: Anthropic API key
        """
        self.client = anthropic.Anthropic(api_key=api_key)
    
    async def extract_text(self, image_path: Path) -> Dict:
        """
        Extract text from an image using Claude Vision.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Dictionary containing:
                - extracted_text: str - The extracted text content
                - confidence: float - Confidence score (0-1)
                - metadata: dict - Additional metadata
        """
        # Read and encode image
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
        
        # Determine media type
        suffix = image_path.suffix.lower()
        media_type = MIME_TYPE_MAP.get(suffix, "image/jpeg")
        
        # Call Claude Vision API
        try:
            message = self.client.messages.create(
                model=CLAUDE_VISION_MODEL,
                max_tokens=CLAUDE_MAX_TOKENS,
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

Format your response as a structured extraction, starting with the full text content."""
                            }
                        ]
                    }
                ]
            )
            
            # Parse response
            response_text = message.content[0].text
            
            # For MVP, return simple structure
            return {
                "extracted_text": response_text,
                "confidence": 0.9,  # Claude is generally high confidence
                "metadata": {
                    "model": CLAUDE_VISION_MODEL,
                    "image_format": media_type,
                    "image_size": image_path.stat().st_size,
                    "tokens_used": message.usage.input_tokens + message.usage.output_tokens
                }
            }
            
        except anthropic.APIError as e:
            raise RuntimeError(f"Claude API error: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to extract text from image: {e}") from e