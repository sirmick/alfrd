# JSON Flattening and DataFrame Conversion

**Feature:** Extract deeply nested JSONB data from ALFRD documents into pandas DataFrames for analysis.

## Overview

The JSON flattening utilities allow you to convert the deeply nested `structured_data` field from documents into tabular format (pandas DataFrames) for analysis, visualization, and export.

**Key Features:**
- **Schemaless**: Works with any JSON structure - no predefined schema required
- **Permissive**: Handles varying JSON formats across documents gracefully
- **Flexible**: Multiple strategies for handling arrays and nested objects
- **Integrated**: Works directly with ALFRD database queries

## Quick Start

### Basic Usage

```python
from shared.database import AlfrdDatabase
from shared.config import get_config
from shared.json_flattener import flatten_documents_to_dataframe

# Initialize database
config = get_config()
db = AlfrdDatabase(config.database_url)
await db.initialize()

# Get all documents with a specific tag as DataFrame
df = await flatten_documents_to_dataframe(db, tags=['series:pge'])

# Now you have a pandas DataFrame!
print(df.head())
df.to_csv('pge_bills.csv')
```

### Command-Line Usage

```bash
# Analyze documents from a file
./scripts/analyze-file-data --file-id <uuid>

# Analyze documents with specific tags
./scripts/analyze-file-data --tags series:pge

# Export to CSV
./scripts/analyze-file-data --tags series:pge --output pge_bills.csv

# Show structure analysis
./scripts/analyze-file-data --tags series:pge --analyze-structure

# Create time series pivot
./scripts/analyze-file-data --tags series:pge --pivot --pivot-freq M
```

## Core Functions

### `flatten_dict()`

Recursively flatten a nested dictionary into dot-notation keys.

```python
from shared.json_flattener import flatten_dict

data = {
    'vendor': 'PG&E',
    'bill': {
        'amount': 123.45,
        'line_items': [
            {'description': 'Electric', 'amount': 100.00}
        ]
    }
}

result = flatten_dict(data)
# {
#     'vendor': 'PG&E',
#     'bill.amount': 123.45,
#     'bill.line_items.0.description': 'Electric',
#     'bill.line_items.0.amount': 100.00
# }
```

**Parameters:**
- `data`: Dictionary to flatten
- `parent_key`: Key prefix for nested values (default: '')
- `sep`: Separator between nested keys (default: '.')
- `max_depth`: Maximum nesting depth (None = unlimited)
- `current_depth`: Internal recursion tracking

### `flatten_to_dataframe()`

Convert a list of documents with nested JSONB to pandas DataFrame.

```python
from shared.json_flattener import flatten_to_dataframe

docs = [
    {
        'id': 'doc1',
        'created_at': '2024-01-01',
        'structured_data': {'vendor': 'PG&E', 'amount': 123.45}
    },
    {
        'id': 'doc2',
        'created_at': '2024-02-01',
        'structured_data': {'vendor': 'PG&E', 'amount': 145.67}
    }
]

df = flatten_to_dataframe(docs)
# DataFrame with columns: id, created_at, vendor, amount
```

**Parameters:**
- `documents`: List of document dicts from database
- `structured_data_key`: Key containing nested JSON (default: 'structured_data')
- `include_metadata`: Include document metadata columns (default: True)
- `metadata_columns`: Specific metadata columns (default: ['id', 'created_at', 'document_type', 'summary'])
- `max_depth`: Maximum nesting depth to flatten
- `array_strategy`: How to handle arrays (see below)
- `sep`: Separator for nested keys (default: '.')

### `flatten_documents_to_dataframe()`

Fetch documents from database and convert to flattened DataFrame.

```python
from shared.json_flattener import flatten_documents_to_dataframe

# By file ID
df = await flatten_documents_to_dataframe(db, file_id=file_uuid)

# By tags
df = await flatten_documents_to_dataframe(db, tags=['series:pge'])

# By specific document IDs
df = await flatten_documents_to_dataframe(db, document_ids=[id1, id2])
```

**Parameters:**
- `db`: AlfrdDatabase instance
- `file_id`: Optional file UUID to fetch documents from
- `tags`: Optional list of tags to filter documents
- `document_ids`: Optional specific document IDs to fetch
- All parameters from `flatten_to_dataframe()` above

## Array Handling Strategies

Different strategies for handling arrays in JSON:

### 1. `flatten` (default)

Expand arrays into indexed columns:

```python
df = flatten_to_dataframe(docs, array_strategy='flatten')
# tags: ['a', 'b', 'c'] → columns: tags.0, tags.1, tags.2
```

**Best for:** Small, fixed-size arrays

### 2. `json`

Keep arrays as JSON strings:

```python
df = flatten_to_dataframe(docs, array_strategy='json')
# tags: ['a', 'b', 'c'] → column: tags='["a","b","c"]'
```

**Best for:** Preserving array structure, large arrays

### 3. `first`

Take only the first element:

```python
df = flatten_to_dataframe(docs, array_strategy='first')
# tags: ['a', 'b', 'c'] → column: tags='a'
```

**Best for:** Arrays where first element is most important

### 4. `count`

Replace with array length:

```python
df = flatten_to_dataframe(docs, array_strategy='count')
# tags: ['a', 'b', 'c'] → column: tags_count=3
```

**Best for:** Statistical analysis of array sizes

## Helper Functions

### `analyze_json_structure()`

Analyze JSON structure to understand the schema:

```python
from shared.json_flattener import analyze_json_structure

# Analyze list of structured_data dicts
structure = analyze_json_structure([doc['structured_data'] for doc in docs])

for field, info in structure.items():
    print(f"{field}:")
    print(f"  Types: {info['types']}")
    print(f"  Found in: {info['count']}/{len(docs)} documents")
    print(f"  Samples: {info['samples'][:3]}")
```

**Output:**
```
vendor:
  Types: ['str']
  Found in: 12/12 documents
  Samples: ['PG&E', 'PG&E', 'PG&E']

amount:
  Types: ['float']
  Found in: 12/12 documents
  Samples: [123.45, 145.67, 132.89]
```

### `pivot_time_series()`

Convert DataFrame to time series format:

```python
from shared.json_flattener import pivot_time_series

# Simple time series (monthly totals)
ts = pivot_time_series(df, date_column='created_at', value_column='amount', freq='M')

# By vendor (monthly totals per vendor)
pivot_df = pivot_time_series(
    df, 
    date_column='created_at',
    value_column='amount',
    index_column='vendor',
    freq='M'
)
```

**Frequency Options:**
- `D`: Daily
- `W`: Weekly
- `M`: Monthly
- `Q`: Quarterly
- `Y`: Yearly

## Common Use Cases

### 1. Export Bills to CSV

```bash
./scripts/analyze-file-data --tags series:pge --output pge_bills.csv
```

### 2. Analyze Spending Trends

```python
df = await flatten_documents_to_dataframe(db, tags=['bill'])

# Monthly spending
monthly = df.groupby(pd.Grouper(key='created_at', freq='M'))['amount'].sum()

# By vendor
by_vendor = df.groupby('vendor')['amount'].sum().sort_values(ascending=False)
```

### 3. Compare Line Items

```python
# Flatten line items
df = await flatten_documents_to_dataframe(
    db, 
    tags=['series:pge'],
    array_strategy='flatten'
)

# Extract electric charges
electric = df[[col for col in df.columns if 'line_items' in col and 'Electric' in str(df[col].iloc[0])]]
```

### 4. Explore Unknown Schema

```bash
# Analyze structure first
./scripts/analyze-file-data --tags series:insurance --analyze-structure

# Then export with appropriate strategy
./scripts/analyze-file-data --tags series:insurance --array-strategy json --output insurance.csv
```

## Examples

### Example 1: Monthly Bill Analysis

```python
from shared.database import AlfrdDatabase
from shared.config import get_config
from shared.json_flattener import flatten_documents_to_dataframe
import pandas as pd

# Get all PG&E bills
db = AlfrdDatabase(get_config().database_url)
await db.initialize()

df = await flatten_documents_to_dataframe(db, tags=['series:pge'])

# Calculate statistics
print(f"Total bills: {len(df)}")
print(f"Average amount: ${df['amount'].mean():.2f}")
print(f"Total spent: ${df['amount'].sum():.2f}")

# Monthly breakdown
df['month'] = pd.to_datetime(df['created_at']).dt.to_period('M')
monthly = df.groupby('month')['amount'].agg(['sum', 'mean', 'count'])
print(monthly)

# Export to CSV
df.to_csv('pge_bills_analysis.csv', index=False)
```

### Example 2: Multi-Vendor Comparison

```python
# Get all utility bills
df = await flatten_documents_to_dataframe(db, tags=['utility_bill'])

# Compare vendors
comparison = df.groupby('vendor').agg({
    'amount': ['mean', 'sum', 'count'],
    'id': 'count'
}).round(2)

print(comparison)
```

### Example 3: Time Series Visualization

```python
import matplotlib.pyplot as plt

# Get bills and create time series
df = await flatten_documents_to_dataframe(db, tags=['series:pge'])
ts = pivot_time_series(df, freq='M')

# Plot
ts.plot(kind='line', title='Monthly PG&E Bills', ylabel='Amount ($)')
plt.savefig('pge_trend.png')
```

## Best Practices

1. **Start with Structure Analysis**: Use `--analyze-structure` to understand your data before extracting

2. **Choose Appropriate Array Strategy**:
   - Small, fixed arrays → `flatten`
   - Variable-length arrays → `json` or `count`
   - First element matters → `first`

3. **Limit Nesting Depth**: Use `max_depth` for deeply nested structures to keep DataFrames manageable

4. **Filter Early**: Use tags or file_id to fetch only needed documents

5. **Export to CSV**: Use CSV for further analysis in Excel, R, or other tools

## Troubleshooting

### Issue: Too Many Columns

**Cause:** Arrays being flattened with different lengths across documents

**Solution:** Use `array_strategy='json'` or `array_strategy='count'`

```python
df = flatten_to_dataframe(docs, array_strategy='json')
```

### Issue: Missing Values

**Cause:** Inconsistent JSON structure across documents

**Solution:** This is expected! pandas handles missing values with NaN. Filter or fill as needed:

```python
# Drop rows with missing vendor
df = df.dropna(subset=['vendor'])

# Fill missing amounts with 0
df['amount'] = df['amount'].fillna(0)
```

### Issue: Memory Error

**Cause:** Too many documents loaded at once

**Solution:** Process in batches or filter more specifically:

```python
# More specific tags
df = await flatten_documents_to_dataframe(db, tags=['series:pge', 'utility_bill'])

# Or limit results in database query (modify the function to add limit parameter)
```

## Testing

Run tests with:

```bash
pytest shared/tests/test_json_flattener.py -v
```

Test coverage includes:
- Basic flattening operations
- All array strategies
- Metadata handling
- Structure analysis
- Time series pivoting
- Integration tests with real-world document structures

## API Reference

See [`shared/json_flattener.py`](../shared/json_flattener.py) for complete API documentation.

## See Also

- [`shared/database.py`](../shared/database.py) - Database operations
- [`scripts/analyze-file-data`](../scripts/analyze-file-data) - Command-line interface
- [ARCHITECTURE.md](../ARCHITECTURE.md) - System architecture

---

**Last Updated:** 2025-12-06