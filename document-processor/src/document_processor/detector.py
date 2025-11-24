"""File type detection module."""

import magic
from pathlib import Path
from typing import Tuple
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from shared.constants import SUPPORTED_IMAGE_TYPES, SUPPORTED_DOCUMENT_TYPES


class FileDetector:
    """Detects and validates file types."""
    
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
        mime_type = self.magic.from_file(str(file_path))
        suffix = file_path.suffix.lower()
        
        if suffix in SUPPORTED_IMAGE_TYPES:
            return ("image", mime_type)
        elif suffix in SUPPORTED_DOCUMENT_TYPES:
            return ("pdf", mime_type)
        else:
            return ("unknown", mime_type)
    
    def is_supported(self, file_path: Path) -> bool:
        """
        Check if file type is supported.
        
        Args:
            file_path: Path to the file to check
            
        Returns:
            True if file type is supported, False otherwise
        """
        file_type, _ = self.detect_type(file_path)
        return file_type in ["image", "pdf"]
    
    def validate_file(self, file_path: Path) -> Tuple[bool, str]:
        """
        Validate file exists and is supported.
        
        Args:
            file_path: Path to the file to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not file_path.exists():
            return (False, f"File does not exist: {file_path}")
        
        if not file_path.is_file():
            return (False, f"Path is not a file: {file_path}")
        
        if not self.is_supported(file_path):
            file_type, mime_type = self.detect_type(file_path)
            return (False, f"Unsupported file type: {file_type} ({mime_type})")
        
        return (True, "")