#!/usr/bin/env python3
"""
Simple test script for AWS Textract OCR.

Usage:
    python samples/test_ocr.py samples/your-image.jpg
"""
import sys
import os
import asyncio
from pathlib import Path

# Add paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'document-processor', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from document_processor.extractors.aws_textract import TextractExtractor


async def test_ocr(image_path: str):
    """Test OCR extraction on an image."""
    print(f"Testing OCR on: {image_path}")
    print("=" * 80)
    
    path = Path(image_path)
    if not path.exists():
        print(f"Error: File not found: {image_path}")
        return
    
    # Initialize extractor
    extractor = TextractExtractor()
    
    try:
        # Extract text
        result = await extractor.extract_text(path)
        
        # Display results
        print(f"\n✓ OCR Completed")
        print(f"Overall Confidence: {result['confidence']:.2%}")
        
        # Display metadata
        print(f"\n📊 Metadata:")
        print("-" * 80)
        for key, value in result['metadata'].items():
            print(f"  {key}: {value}")
        
        # Display blocks by type
        blocks = result.get('blocks', {})
        
        # PAGE blocks
        if blocks.get('PAGE'):
            print(f"\n📄 PAGE Blocks ({len(blocks['PAGE'])}):")
            print("-" * 80)
            for i, block in enumerate(blocks['PAGE'], 1):
                print(f"  Page {i}:")
                geom = block['geometry']
                if 'BoundingBox' in geom:
                    bbox = geom['BoundingBox']
                    print(f"    BoundingBox: ({bbox.get('Left', 0):.3f}, {bbox.get('Top', 0):.3f}) "
                          f"W:{bbox.get('Width', 0):.3f} H:{bbox.get('Height', 0):.3f}")
        
        # LINE blocks
        if blocks.get('LINE'):
            print(f"\n📝 LINE Blocks ({len(blocks['LINE'])}):")
            print("-" * 80)
            for i, block in enumerate(blocks['LINE'][:20], 1):  # Show first 20 lines
                conf = block['confidence']
                text = block['text']
                geom = block['geometry']
                bbox = geom.get('BoundingBox', {})
                print(f"  Line {i} [{conf:.1f}%]:")
                print(f"    Text: {text}")
                if bbox:
                    print(f"    BBox: ({bbox.get('Left', 0):.3f}, {bbox.get('Top', 0):.3f}) "
                          f"W:{bbox.get('Width', 0):.3f} H:{bbox.get('Height', 0):.3f}")
            if len(blocks['LINE']) > 20:
                print(f"  ... and {len(blocks['LINE']) - 20} more lines")
        
        # WORD blocks (show summary)
        if blocks.get('WORD'):
            print(f"\n🔤 WORD Blocks ({len(blocks['WORD'])}):")
            print("-" * 80)
            # Show first 10 words
            for i, block in enumerate(blocks['WORD'][:10], 1):
                conf = block['confidence']
                text = block['text']
                print(f"  Word {i} [{conf:.1f}%]: {text}")
            if len(blocks['WORD']) > 10:
                print(f"  ... and {len(blocks['WORD']) - 10} more words")
            
            # Show confidence distribution
            confidences = [b['confidence'] for b in blocks['WORD']]
            avg_word_conf = sum(confidences) / len(confidences)
            min_conf = min(confidences)
            max_conf = max(confidences)
            print(f"\n  Confidence stats: avg={avg_word_conf:.1f}%, min={min_conf:.1f}%, max={max_conf:.1f}%")
        
        # Display full extracted text
        print(f"\n📄 Full Extracted Text:")
        print("=" * 80)
        print(result['extracted_text'])
        print("=" * 80)
        
    except Exception as e:
        print(f"\n✗ OCR Failed: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python samples/test_ocr.py <image_path>")
        print("\nExample:")
        print("  python samples/test_ocr.py samples/bill.jpg")
        sys.exit(1)
    
    asyncio.run(test_ocr(sys.argv[1]))