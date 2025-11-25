"""File type detection module."""

import magic
from pathlib import Path
from typing import Tuple, Dict
import sys
import json

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from shared.constants import SUPPORTED_IMAGE_TYPES, SUPPORTED_TEXT_TYPES, META_JSON_FILENAME


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
            file_type: 'image', 'text', or 'unknown'
            mime_type: MIME type string
        """
        mime_type = self.magic.from_file(str(file_path))
        suffix = file_path.suffix.lower()
        
        if suffix in SUPPORTED_IMAGE_TYPES:
            return ("image", mime_type)
        elif suffix in SUPPORTED_TEXT_TYPES:
            return ("text", mime_type)
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
        return file_type in ["image", "text"]
    
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
    
    def validate_document_folder(self, folder_path: Path) -> Tuple[bool, str, Dict]:
        """
        Validate a document folder structure.
        
        A valid document folder must:
        1. Be a directory
        2. Contain a meta.json file
        3. Have valid structure in meta.json
        4. Reference existing files
        
        Args:
            folder_path: Path to the document folder
            
        Returns:
            Tuple of (is_valid, error_message, meta_dict)
            is_valid: True if folder is valid
            error_message: Error description if invalid, empty string if valid
            meta_dict: Parsed meta.json if valid, empty dict otherwise
        """
        # Check if path is a directory
        if not folder_path.exists():
            return (False, f"Folder does not exist: {folder_path}", {})
        
        if not folder_path.is_dir():
            return (False, f"Path is not a directory: {folder_path}", {})
        
        # Check for meta.json
        meta_file = folder_path / META_JSON_FILENAME
        if not meta_file.exists():
            return (False, f"Missing {META_JSON_FILENAME}", {})
        
        # Parse meta.json
        try:
            with open(meta_file, 'r') as f:
                meta = json.load(f)
        except json.JSONDecodeError as e:
            return (False, f"Invalid JSON in {META_JSON_FILENAME}: {e}", {})
        except Exception as e:
            return (False, f"Error reading {META_JSON_FILENAME}: {e}", {})
        
        # Validate meta structure
        if 'id' not in meta:
            return (False, "Missing 'id' field in meta.json", {})
        
        if 'documents' not in meta:
            return (False, "Missing 'documents' field in meta.json", {})
        
        documents = meta.get('documents', [])
        if not isinstance(documents, list):
            return (False, "'documents' field must be a list", {})
        
        if len(documents) == 0:
            return (False, "No documents listed in meta.json", {})
        
        # Validate each document entry
        for i, doc in enumerate(documents):
            if not isinstance(doc, dict):
                return (False, f"Document entry {i} is not a dict", {})
            
            if 'file' not in doc:
                return (False, f"Document entry {i} missing 'file' field", {})
            
            if 'type' not in doc:
                return (False, f"Document entry {i} missing 'type' field", {})
            
            file_path = folder_path / doc['file']
            if not file_path.exists():
                return (False, f"Referenced file not found: {doc['file']}", {})
            
            # Validate file type matches
            doc_type = doc['type']
            if doc_type not in ['image', 'text']:
                return (False, f"Invalid document type '{doc_type}' in entry {i}", {})
        
        return (True, "", meta)