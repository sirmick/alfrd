#!/usr/bin/env python3
"""
Add a document to the inbox for processing.

Creates a properly formatted document folder with meta.json.

Usage:
    python scripts/add-document.py image1.jpg [image2.jpg ...] [--tags bill utilities] [--source mobile]
    
Examples:
    # Single image with default settings
    python scripts/add-document.py ~/Downloads/bill.jpg
    
    # Multiple images with tags
    python scripts/add-document.py page1.jpg page2.jpg --tags bill electric
    
    # With custom source
    python scripts/add-document.py receipt.jpg --source email --tags receipt groceries
"""

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config import Settings
from shared.constants import META_JSON_FILENAME


def detect_file_type(file_path: Path) -> str:
    """
    Detect if file is an image or text file.
    
    Args:
        file_path: Path to the file
        
    Returns:
        'image' or 'text'
    """
    suffix = file_path.suffix.lower()
    
    image_types = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.tiff', '.bmp'}
    text_types = {'.txt', '.text'}
    
    if suffix in image_types:
        return 'image'
    elif suffix in text_types:
        return 'text'
    else:
        # Default to image for unknown types
        return 'image'


def create_document_folder(
    files: list[Path],
    tags: list[str],
    source: str,
    inbox_path: Path
) -> Path:
    """
    Create a document folder in the inbox with proper structure.
    
    Args:
        files: List of file paths to include
        tags: List of tags for the document
        source: Source identifier (e.g., 'mobile', 'email', 'scanner')
        inbox_path: Path to the inbox directory
        
    Returns:
        Path to the created document folder
    """
    # Generate document ID
    doc_id = str(uuid4())
    
    # Create folder name from first file name and timestamp
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    first_file_stem = files[0].stem
    folder_name = f"{first_file_stem}_{timestamp}"
    
    # Create folder
    folder_path = inbox_path / folder_name
    folder_path.mkdir(parents=True, exist_ok=True)
    
    # Copy files and build documents list
    documents = []
    for i, file_path in enumerate(files, 1):
        # Copy file to folder
        dest_file = folder_path / file_path.name
        shutil.copy2(file_path, dest_file)
        
        # Detect file type
        file_type = detect_file_type(file_path)
        
        # Add to documents list
        documents.append({
            "file": file_path.name,
            "type": file_type,
            "order": i
        })
        
        print(f"  ✓ Copied: {file_path.name} (type: {file_type})")
    
    # Create meta.json
    meta = {
        "id": doc_id,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "documents": documents,
        "metadata": {
            "source": source,
            "tags": tags
        }
    }
    
    meta_file = folder_path / META_JSON_FILENAME
    with open(meta_file, 'w') as f:
        json.dump(meta, f, indent=2)
    
    print(f"  ✓ Created: {META_JSON_FILENAME}")
    
    return folder_path


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Add a document to the inbox for processing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single image with default settings
  %(prog)s ~/Downloads/bill.jpg
  
  # Multiple images with tags
  %(prog)s page1.jpg page2.jpg --tags bill electric
  
  # With custom source
  %(prog)s receipt.jpg --source email --tags receipt groceries
        """
    )
    
    parser.add_argument(
        'files',
        nargs='+',
        type=str,
        help='Path(s) to document file(s) (images or text files)'
    )
    
    parser.add_argument(
        '--tags',
        nargs='*',
        default=['unknown'],
        help='Tags for the document (default: unknown)'
    )
    
    parser.add_argument(
        '--source',
        default='mobile',
        help='Source of the document (default: mobile)'
    )
    
    args = parser.parse_args()
    
    # Load settings
    try:
        settings = Settings()
    except Exception as e:
        print(f"✗ Error loading settings: {e}")
        print("  Make sure .env file exists and is configured")
        sys.exit(1)
    
    # Ensure inbox exists
    inbox_path = settings.inbox_path
    inbox_path.mkdir(parents=True, exist_ok=True)
    
    # Validate files
    file_paths = []
    for file_str in args.files:
        file_path = Path(file_str).expanduser().resolve()
        if not file_path.exists():
            print(f"✗ File not found: {file_path}")
            sys.exit(1)
        if not file_path.is_file():
            print(f"✗ Not a file: {file_path}")
            sys.exit(1)
        file_paths.append(file_path)
    
    # Display info
    print(f"\n📄 Adding document to inbox")
    print(f"   Inbox: {inbox_path}")
    print(f"   Files: {len(file_paths)}")
    print(f"   Tags: {', '.join(args.tags)}")
    print(f"   Source: {args.source}")
    print()
    
    # Create document folder
    try:
        folder_path = create_document_folder(
            files=file_paths,
            tags=args.tags,
            source=args.source,
            inbox_path=inbox_path
        )
        
        print()
        print(f"✅ Document added successfully!")
        print(f"   Location: {folder_path}")
        print(f"   Folder: {folder_path.name}")
        print()
        print(f"🚀 Next steps:")
        print(f"   1. Run document processor: python document-processor/src/document_processor/main.py")
        print(f"   2. Check processed output in: {settings.documents_path}")
        
    except Exception as e:
        print(f"\n✗ Error creating document folder: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()