"""PDF text extraction module."""

from pathlib import Path
from typing import Dict
from pypdf import PdfReader
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))


class PDFExtractor:
    """Extract text from PDF files."""
    
    async def extract_text(self, pdf_path: Path) -> Dict:
        """
        Extract text from a PDF file.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Dictionary containing:
                - extracted_text: str - The extracted text content
                - confidence: float - Confidence score (always 1.0 for PDF)
                - metadata: dict - Additional metadata
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
            
            # Get PDF metadata
            metadata = {
                "page_count": len(reader.pages),
                "extractor": "pypdf",
                "file_size": pdf_path.stat().st_size
            }
            
            # Add PDF info if available
            if reader.metadata:
                pdf_info = {}
                if reader.metadata.title:
                    pdf_info["title"] = reader.metadata.title
                if reader.metadata.author:
                    pdf_info["author"] = reader.metadata.author
                if reader.metadata.creator:
                    pdf_info["creator"] = reader.metadata.creator
                if reader.metadata.producer:
                    pdf_info["producer"] = reader.metadata.producer
                if pdf_info:
                    metadata["pdf_info"] = pdf_info
            
            return {
                "extracted_text": extracted_text.strip(),
                "confidence": 1.0,  # PDF extraction is deterministic
                "metadata": metadata
            }
            
        except Exception as e:
            raise RuntimeError(f"Failed to extract text from PDF: {e}") from e