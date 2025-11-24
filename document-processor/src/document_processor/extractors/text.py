"""Plain text document extraction."""

from pathlib import Path
from typing import Dict
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))


class TextExtractor:
    """Extract content from plain text documents."""
    
    async def extract_text(self, text_path: Path) -> Dict:
        """
        Extract text from a plain text file.
        
        Args:
            text_path: Path to the text file
            
        Returns:
            Dictionary containing:
                - extracted_text: str - The text content
                - confidence: float - Always 1.0 for text files
                - metadata: dict - File metadata
        """
        try:
            # Read text file
            with open(text_path, "r", encoding="utf-8") as f:
                text = f.read()
            
            # Get file stats
            file_size = text_path.stat().st_size
            line_count = len(text.splitlines())
            char_count = len(text)
            
            return {
                'extracted_text': text,
                'confidence': 1.0,  # Text files have perfect "extraction"
                'metadata': {
                    'extractor': 'plain_text',
                    'file_size': file_size,
                    'line_count': line_count,
                    'char_count': char_count,
                    'encoding': 'utf-8'
                }
            }
            
        except UnicodeDecodeError as e:
            # Try with different encoding
            try:
                with open(text_path, "r", encoding="latin-1") as f:
                    text = f.read()
                
                return {
                    'extracted_text': text,
                    'confidence': 0.95,  # Slightly lower confidence for non-UTF-8
                    'metadata': {
                        'extractor': 'plain_text',
                        'file_size': text_path.stat().st_size,
                        'encoding': 'latin-1',
                        'encoding_warning': 'File was not UTF-8, used latin-1'
                    }
                }
            except Exception as fallback_error:
                raise RuntimeError(
                    f"Failed to read text file with both UTF-8 and latin-1: {fallback_error}"
                ) from e
        except Exception as e:
            raise RuntimeError(f"Failed to extract text from file: {e}") from e