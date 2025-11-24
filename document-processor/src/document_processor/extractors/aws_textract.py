"""AWS Textract OCR extraction for documents."""

import boto3
from pathlib import Path
from typing import Dict
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from shared.config import Settings
from shared.constants import TEXTRACT_MAX_SIZE, TEXTRACT_TIMEOUT


class TextractExtractor:
    """Extract text from images using AWS Textract."""
    
    def __init__(self, aws_access_key_id: str = None, aws_secret_access_key: str = None, region: str = None):
        """
        Initialize the Textract extractor.
        
        Args:
            aws_access_key_id: AWS access key (optional, can use env/IAM)
            aws_secret_access_key: AWS secret key (optional, can use env/IAM)
            region: AWS region (default: us-east-1)
        """
        settings = Settings()
        
        # Use provided credentials or fall back to settings
        self.textract = boto3.client(
            'textract',
            region_name=region or settings.aws_region,
            aws_access_key_id=aws_access_key_id or settings.aws_access_key_id or None,
            aws_secret_access_key=aws_secret_access_key or settings.aws_secret_access_key or None
        )
    
    async def extract_text(self, image_path: Path) -> Dict:
        """
        Extract text from an image using AWS Textract.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Dictionary containing:
                - extracted_text: str - The extracted text content
                - confidence: float - Average confidence score (0-1)
                - metadata: dict - Additional metadata
                
        Raises:
            RuntimeError: If extraction fails or file is too large
        """
        try:
            # Read image file
            with open(image_path, "rb") as f:
                image_bytes = f.read()
            
            # Check size limit for direct upload (5MB for Textract)
            file_size = len(image_bytes)
            if file_size > TEXTRACT_MAX_SIZE:
                raise RuntimeError(
                    f"Image too large ({file_size / 1024 / 1024:.2f}MB). "
                    f"Maximum size for direct upload is {TEXTRACT_MAX_SIZE / 1024 / 1024}MB. "
                    "S3 upload not yet implemented."
                )
            
            # Call Textract
            response = self.textract.detect_document_text(
                Document={'Bytes': image_bytes}
            )
            
            # Parse response blocks
            lines = []
            total_confidence = 0
            line_count = 0
            word_count = 0
            
            for block in response['Blocks']:
                if block['BlockType'] == 'LINE':
                    lines.append(block['Text'])
                    total_confidence += block.get('Confidence', 0)
                    line_count += 1
                elif block['BlockType'] == 'WORD':
                    word_count += 1
            
            # Join lines into full text
            extracted_text = '\n'.join(lines)
            
            # Calculate average confidence (convert from 0-100 to 0-1)
            avg_confidence = (total_confidence / line_count / 100) if line_count > 0 else 0
            
            # Get document metadata
            doc_metadata = response.get('DocumentMetadata', {})
            
            return {
                'extracted_text': extracted_text,
                'confidence': avg_confidence,
                'metadata': {
                    'extractor': 'aws_textract',
                    'pages': doc_metadata.get('Pages', 1),
                    'blocks_total': len(response['Blocks']),
                    'lines_detected': line_count,
                    'words_detected': word_count,
                    'file_size': file_size,
                    'image_format': image_path.suffix.lower()
                }
            }
            
        except boto3.exceptions.Boto3Error as e:
            raise RuntimeError(f"AWS Textract error: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to extract text from image: {e}") from e
    
    def validate_credentials(self) -> bool:
        """
        Validate AWS credentials by making a test call.
        
        Returns:
            True if credentials are valid, False otherwise
        """
        try:
            # Make a simple call to verify credentials
            # This doesn't actually process anything
            self.textract.meta.client.describe_endpoint()
            return True
        except Exception:
            return False