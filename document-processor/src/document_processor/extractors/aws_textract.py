"""AWS Textract OCR extraction for documents.

DEPRECATED: This class now wraps AWSClientManager for backward compatibility.
New code should use AWSClientManager directly for caching benefits.
"""

from pathlib import Path
from typing import Dict
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from shared.config import Settings
from shared.constants import TEXTRACT_MAX_SIZE, TEXTRACT_TIMEOUT
from shared.aws_clients import AWSClientManager


class TextractExtractor:
    """Extract text from images using AWS Textract.
    
    NOTE: This is now a thin wrapper around AWSClientManager.
    Uses shared client instance for caching and cost tracking.
    """
    
    def __init__(self, aws_access_key_id: str = None, aws_secret_access_key: str = None, region: str = None):
        """
        Initialize the Textract extractor.
        
        Args:
            aws_access_key_id: AWS access key (optional, can use env/IAM)
            aws_secret_access_key: AWS secret key (optional, can use env/IAM)
            region: AWS region (default: us-east-1)
        """
        # Use unified AWS client manager (singleton with caching)
        self._aws_manager = AWSClientManager(
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_region=region,
            enable_cache=True
        )
        
        # Keep reference to boto3 client for backward compatibility
        self.textract = self._aws_manager._textract_client
    
    async def extract_text(self, image_path: Path) -> Dict:
        """
        Extract text from an image using AWS Textract.
        
        Now uses AWSClientManager for automatic caching and cost tracking.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Dictionary containing:
                - extracted_text: str - The extracted text content
                - confidence: float - Average confidence score (0-1)
                - blocks: dict - Block-level data by type
                - metadata: dict - Additional metadata
                - cached: bool - Whether response was from cache
                
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
            
            # Call Textract via AWSClientManager (with caching!)
            result = await self._aws_manager.extract_text_textract(
                image_bytes=image_bytes,
                use_cache=True
            )
            
            # Add image format to metadata
            result['metadata']['image_format'] = image_path.suffix.lower()
            
            return result
            
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