# ALFRD Test Dataset Generator

Generate realistic document images for testing the ALFRD document processing system.

## Overview

This generator creates a full year of realistic documents (bills, receipts, school documents, etc.) as JPG images using HTML templates and Playwright browser automation.

**Generated Documents (per year):**
- 12 PG&E utility bills (monthly)
- 12 Rent receipts (monthly)
- 12 Auto insurance bills (monthly)
- 2 Tuition bills (spring + fall semesters)
- **Total: ~38 documents**

## Prerequisites

- Python 3.11+
- Node.js (for Playwright browsers)

## Installation

```bash
# 1. Navigate to this directory
cd test-dataset-generator

# 2. Create and activate virtual environment
python3 -m venv venv
. venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Install Playwright browsers (first time only)
playwright install chromium

# 5. Install system dependencies for Playwright (Linux only)
sudo apt-get update && sudo apt-get install -y \
    libnspr4 libnss3 libatk1.0-0t64 libatk-bridge2.0-0t64 \
    libcups2t64 libatspi2.0-0t64 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libcairo2 libpango-1.0-0 \
    libasound2t64
```

**Note:** Playwright is a browser automation library used to render HTML templates as images by taking screenshots with a headless browser.

## Usage

### Generate Full Year Dataset

```bash
# Generate all documents for 2024
python generator.py
```

This will create:
```
output/
├── bills/
│   ├── pge_2024_01.jpg
│   ├── pge_2024_02.jpg
│   └── ... (12 total)
├── property/
│   ├── rent_2024_01.jpg
│   ├── rent_2024_02.jpg
│   └── ... (12 total)
├── vehicle/
│   ├── insurance_2024_01.jpg
│   └── ... (12 total)
└── school/
    ├── tuition_spring_2024.jpg
    └── tuition_fall_2024.jpg
```

### Use with ALFRD

```bash
# Copy generated documents to ALFRD inbox
# (You'll need to create meta.json files or use add-document script)

# Example: Add a single document
cd ../esec
./scripts/add-document ../test-dataset-generator/output/bills/pge_2024_01.jpg --tags bill utilities

# Or batch import all bills
for file in ../test-dataset-generator/output/bills/*.jpg; do
    ./scripts/add-document "$file" --tags bill utilities
done
```

## Project Structure

```
test-dataset-generator/
├── generator.py              # Main generation script
├── requirements.txt          # Python dependencies
├── README.md                 # This file
├── personas/
│   └── alex_johnson.yaml    # Persona definition
├── templates/
│   ├── bills/
│   │   └── pge_utility.html # PG&E bill template
│   ├── property/
│   │   └── rent_receipt.html
│   ├── school/
│   │   └── tuition_bill.html
│   └── vehicle/
│       └── insurance_bill.html
└── output/                   # Generated JPG files
```

## How It Works

1. **Persona Definition** - `personas/alex_johnson.yaml` contains all personal details (address, school, vehicle, etc.)

2. **Data Generation** - `generator.py` creates realistic data for each document:
   - Seasonal usage variations for utility bills
   - Random but realistic amounts
   - Proper date sequencing
   - 10% chance of late rent payment

3. **HTML Templates** - Jinja2 templates styled with CSS to look like real documents

4. **Image Rendering** - Playwright renders HTML to JPG at 850x1100px

## Customization

### Modify Persona

Edit `personas/alex_johnson.yaml` to change:
- Name, address, contact info
- School details
- Vehicle information
- Rent amount
- Utility accounts

### Add Document Types

1. Create HTML template in `templates/{category}/`
2. Add data generation method to `generator.py`
3. Add generation call in `generate_year()` method

### Adjust Amounts

Edit the data generation methods in `generator.py`:
- `generate_pge_bill_data()` - Utility bill amounts
- `generate_rent_receipt_data()` - Rent amounts
- `generate_insurance_bill_data()` - Insurance premiums
- `generate_tuition_bill_data()` - Tuition and fees

## Template Variables

Each HTML template uses Jinja2 variables. Example for PG&E bill:

```jinja
{{ bill_date }}
{{ customer_name }}
{{ kwh_usage }}
{{ total_amount }}
```

See individual template files for complete variable lists.

## Performance

- **Generation Speed**: ~2 seconds per document
- **Total Time**: ~90 seconds for full year (38 documents)
- **File Size**: ~50-150KB per JPG

## Troubleshooting

### Playwright Not Found

```bash
# Install Playwright browsers
playwright install chromium
```

### Module Import Errors

```bash
# Reinstall dependencies
pip install -r requirements.txt
```

### Low Quality Images

Edit `generator.py` and increase JPEG quality:
```python
await page.screenshot(
    path=str(output_path),
    type='jpeg',
    quality=95,  # Increase from 85
    full_page=True
)
```

## Examples

### PG&E Utility Bill
- Monthly billing cycle (20th-28th)
- Seasonal usage variations (higher in summer/winter)
- Electric + gas charges
- Realistic pricing structure

### Rent Receipt
- Paid on 1st of month
- 10% chance of late fee
- Formal receipt format
- Property manager signature

### Tuition Bill
- Spring (January) and Fall (August)
- Course enrollment details
- Tuition + fees breakdown
- Payment due dates

### Auto Insurance Bill
- Monthly premium billing
- Full coverage details
- Policy information
- Agent contact details

## Future Enhancements

- [ ] More document types (credit cards, tax forms, medical bills)
- [ ] Configurable document counts
- [ ] PDF output option
- [ ] Batch ALFRD import script
- [ ] Multiple persona support
- [ ] Random variations in template styles

## License

MIT License - Same as ALFRD parent project

---

**Generated with ❤️ for ALFRD Testing**