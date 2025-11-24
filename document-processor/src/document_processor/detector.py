"""File type detection for document processor."""

import magic
from pathlib import Path
from typing import Tuple
import sys

# Add parent directories to path for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from shared.constants import SUPPORTED_IMAGE_TYPES, SUPPORTED_DOCUMENT_TYPES


class FileDetector:
    """Detect file types using python-magic."""
    
    def __init__(self):
        """Initialize the file detector with python-magic."""
        self.magic = magic.Magic(mime=True)
    
    def detect_type(self, file_path: Path) -> Tuple[str, str]:
        """
        Detect file type and MIME type.
        
        Args:
            file_path: Path to the file to detect
            
        Returns:
            Tuple of (file_type, mime_type)
            file_type: 'image', 'pdf', or 'unknown'
            mime_type: MIME type string
        """
        # Get MIME type
        mime_type = self.magic.from_file(str(file_path))
        
        # Get file extension
        suffix = file_path.suffix.lower()
        
        # Determine file type category
        if suffix in SUPPORTED_IMAGE_TYPES:
            return ("image", mime_type)
        elif suffix in SUPPORTED_DOCUMENT_TYPES:
            return ("pdf", mime_type)
        else:
            return ("unknown", mime_type)
    
    def is_supported(self, file_path: Path) -> bool:
        """
        Check if file type is supported for processing.
        
        Args:
            file_path: Path to the file to check
            
        Returns:
            True if file is supported, False otherwise
        """
        file_type, _ = self.detect_type(file_path)
        return file_type in ["image", "pdf"]
    
    def get_file_info(self, file_path: Path) -> dict:
        """
        Get comprehensive file information.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Dictionary with file information
        """
        file_type, mime_type = self.detect_type(file_path)
        
        try:
            stat = file_path.stat()
            return {
                "filename": file_path.name,
                "file_type": file_type,
                "mime_type": mime_type,
                "file_size": stat.st_size,
                "extension": file_path.suffix.lower(),
                "is_supported": self.is_supported(file_path)
            }
        except Exception as e:
            return {
                "filename": file_path.name,
                "file_type": file_type,
                "mime_type": mime_type,
                "error": str(e),
                "is_supported": False
            }