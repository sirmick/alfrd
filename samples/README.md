# Sample Documents

Place test documents here for OCR testing.

## Structure
- Each document should be a clear image (JPG, PNG)
- Supported types: bills, receipts, letters, forms
- Will be used to test AWS Textract OCR extraction

## Usage
Test OCR on a sample:
```bash
python -c "
import sys
import asyncio
from pathlib import Path
sys.path.insert(0, 'document-processor/src')
sys.path.insert(0, '.')
from document_processor.extractors.aws_textract import TextractExtractor

async def test_ocr(image_path):
    extractor = TextractExtractor()
    result = await extractor.extract_text(Path(image_path))
    print(f'Extracted text ({result["confidence"]:.2%} confidence):')
    print(result['extracted_text'])
    print(f'Metadata: {result["metadata"]}')

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python -c ... <image_path>')
    else:
        asyncio.run(test_ocr(sys.argv[1]))
"
```

