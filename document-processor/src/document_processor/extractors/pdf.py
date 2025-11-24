"""PDF text extraction using pypdf."""

from pathlib import Path
from typing import Dict
from pypdf import PdfReader


class PDFExtractor:
    """Extract text from PDF documents."""
    
    def __init__(self):
        """Initialize the PDF extractor."""
        pass
    
    async def extract_text(self, pdf_path: Path) -> Dict:
        """
        Extract text from PDF file.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Dictionary with extracted_text, confidence, and metadata
        """
        try:
            reader = PdfReader(pdf_path)
            
            # Extract text from all pages
            text_parts = []
            for page_num, page in enumerate(reader.pages, 1):
                page_text = page.extract_text()
                if page_text.strip():
                    text_parts.append(f"--- Page {page_num} ---\n{page_text}")
            
            extracted_text = "\n\n".join(text_parts)
            
            return {
                "extracted_text": extracted_text.strip(),
                "confidence": 1.0,  # pypdf extraction is deterministic
                "metadata": {
                    "page_count": len(reader.pages),
                    "extractor": "pypdf",
                    "has_text": bool(extracted_text.strip())
                }
            }
            
        except Exception as e:
            return {
                "extracted_text": "",
                "confidence": 0.0,
                "metadata": {
                    "error": str(e),
                    "extractor": "pypdf"
                }
            }
    
    def get_pdf_info(self, pdf_path: Path) -> Dict:
        """
        Get PDF metadata without extracting text.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Dictionary with PDF information
        """
        try:
            reader = PdfReader(pdf_path)
            metadata = reader.metadata or {}
            
            return {
                "page_count": len(reader.pages),
                "title": metadata.get("/Title", ""),
                "author": metadata.get("/Author", ""),
                "creator": metadata.get("/Creator", ""),
                "producer": metadata.get("/Producer", ""),
                "is_encrypted": reader.is_encrypted
            }
        except Exception as e:
            return {
                "error": str(e)
            }