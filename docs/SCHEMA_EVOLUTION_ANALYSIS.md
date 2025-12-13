# Schema Evolution Analysis: Self-Evolving Prompts and Data Consistency

**Date:** 2025-12-10  
**File Analyzed:** PG&E Utility Bills (12 documents)  
**File ID:** 6ba2101d-c326-4eec-a5f9-60e57e5c25e8

---

## Problem Statement

The self-evolving prompt system in ALFRD creates a fundamental challenge: **as prompts improve over time, earlier documents may be extracted with lower quality or different schemas than later documents**. This creates inconsistency in structured data that makes aggregation, analysis, and data table display problematic.

---

## Evidence from Production Data

### Schema Inconsistencies Observed

Analyzing 12 PG&E utility bills from the same series, we see **significant schema variations** in the `structured_data.utility_bill` field:

#### 1. **Nested Structure Differences**

**Early Document (pge_2024_01):**
```json
"usage": {
  "electric_kwh": 833,
  "gas_therms": 27
}
```

**Later Document (pge_2024_09):**
```json
"usage_consumption": {
  "electric_kwh": 933,
  "gas_therms": 41
}
```

**Another Variant (pge_2024_10):**
```json
"usage": {
  "total_kwh": 689,
  "therms": 26
}
```

**Field name variations:** `usage` vs `usage_consumption` vs `usage_consumption`  
**Key variations:** `electric_kwh` vs `total_kwh`, `gas_therms` vs `therms`

#### 2. **Rate Information Schema Drift**

**Document pge_2024_01:**
```json
"rate_tariff": {
  "electric_generation_rate": 0.139,
  "electric_delivery_rate": 0.079,
  "gas_rate": 1.852
}
```

**Document pge_2024_04:**
```json
"rate_information": {
  "electric_rate": {
    "generation_charges": 0.1412,
    "delivery_charges": 0.0778
  },
  "gas_rate": 1.9267
}
```

**Document pge_2024_05:**
```json
"rate_tariff": {
  "electric_generation_charges": "included",
  "electric_delivery_charges": "included",
  "gas_charges": "included",
  "taxes_and_fees": "included"
}
```

**Document pge_2024_06:**
```json
"rate_information": {
  "electric_generation_rate": null,
  "electric_delivery_rate": null,
  "gas_rate": null
}
```

**Issues:**
- Field name changes: `rate_tariff` vs `rate_information`
- Data type changes: numeric values → string "included" → null
- Nested structure changes: flat vs nested electric_rate object
- Key name variations: `electric_generation_rate` vs `generation_charges`

#### 3. **Billing Period Format Inconsistencies**

- `"January 27, 2024 to February 26, 2024"` (verbose)
- `"February 22, 2024 to March 23, 2024"` (verbose)
- `"May 24, 2024 to June 23, 2024"` (verbose)
- `"June 25 - July 25, 2024"` (abbreviated)
- `"August 26 to September 25, 2024"` (mixed)
- `"September 26 - October 26, 2024"` (abbreviated)

**Issue:** Date range format is inconsistent, making parsing difficult

#### 4. **Charge Breakdown Variations**

All documents have similar but slightly different charge structures, some with more detail than others.

---

## Root Causes

### 1. **Prompt Evolution Over Time**
- As the LLM prompt improves, it extracts data differently
- Later prompts may recognize more fields or organize data better
- Version 1 of prompt → simple flat structure
- Version 5 of prompt → sophisticated nested structure
- **Result:** Documents processed at different times have incompatible schemas

### 2. **LLM Non-Determinism**
- Even with the same prompt, LLMs can produce varying output structures
- Field naming choices: "usage" vs "usage_consumption"
- Data representation: numeric vs string vs null

### 3. **No Schema Enforcement**
- JSONB in PostgreSQL allows any structure
- No validation that enforces consistent field names or types
- LLM outputs are stored directly without normalization

---

## Impact on System

### 1. **Data Table Display Problems** ⚠️

When trying to display this data in a table (as the user is experiencing):

- **Column naming chaos:** Different documents have different field names for the same concept
- **Missing data:** Some documents have `electric_kwh`, others have `total_kwh`, creating sparse columns
- **Type mismatches:** A field that's numeric in one doc is a string in another
- **Nested structure hell:** Flattening produces different paths for the same logical data

### 2. **Aggregation Failures** ⚠️

```python
# This won't work consistently:
total_kwh = sum(doc['structured_data']['utility_bill']['usage']['electric_kwh'] 
                for doc in documents)
```

**Why it fails:**
- Some docs use `usage`, others use `usage_consumption`
- Some use `electric_kwh`, others use `total_kwh`
- Some values are numeric, others are strings or null

### 3. **Query Complexity** ⚠️

PostgreSQL JSONB queries become unwieldy:
```sql
SELECT 
  structured_data->'utility_bill'->'usage'->>'electric_kwh' AS kwh_v1,
  structured_data->'utility_bill'->'usage_consumption'->>'electric_kwh' AS kwh_v2,
  structured_data->'utility_bill'->'usage'->>'total_kwh' AS kwh_v3
FROM documents;
```

### 4. **Analytics Breakdown** ⚠️

- Time-series analysis requires consistent field names
- Trend detection fails with schema drift
- Reporting tools can't handle dynamic schemas

---

## Proposed Solutions

### Solution 1: **Schema Versioning + Migration** ⭐ (Recommended)

**Concept:** Track schema version per document, provide migration layer

```python
class SchemaVersion:
    v1 = {
        "usage": {"electric_kwh", "gas_therms"},
        "rate_tariff": {"electric_generation_rate", ...}
    }
    v2 = {
        "usage_consumption": {"electric_kwh", "gas_therms"},
        "rate_information": {...}
    }

def normalize_to_latest(doc, from_version):
    """Migrate old schema to current version"""
    if from_version == "v1":
        # Rename 'usage' to 'usage_consumption'
        # Normalize rate_tariff to rate_information
        ...
```

**Implementation:**
1. Add `schema_version` field to documents table
2. Create schema registry with versions
3. Build migration functions for each version transition
4. On data access, normalize to latest schema on-the-fly
5. Optional: Background job to migrate old documents

**Pros:**
- Backward compatible
- Enables continuous improvement
- Data access layer handles complexity

**Cons:**
- Migration code maintenance
- Performance overhead on reads (can be cached)

---

### Solution 2: **Strict Schema Enforcement**

**Concept:** Define rigid schema, validate LLM output before storage

```python
UTILITY_BILL_SCHEMA = {
    "type": "object",
    "required": ["utility_provider", "total_amount_due", "due_date"],
    "properties": {
        "utility_provider": {"type": "string"},
        "total_amount_due": {"type": "number"},
        "due_date": {"type": "string", "format": "date"},
        "usage": {
            "type": "object",
            "properties": {
                "electric_kwh": {"type": "number"},
                "gas_therms": {"type": "number"}
            }
        }
    }
}

def store_document(doc):
    # Validate against schema
    jsonschema.validate(doc['structured_data'], UTILITY_BILL_SCHEMA)
    # Normalize field names
    doc = normalize_field_names(doc)
    # Store
    db.insert(doc)
```

**Pros:**
- Guaranteed consistency
- Predictable queries
- Clean data tables

**Cons:**
- **Blocks prompt evolution** ❌ (defeats self-improving purpose)
- Requires manual schema updates
- May reject valid extractions that don't fit schema

---

### Solution 3: **Schema Registry + Field Mapping** ⭐

**Concept:** Maintain field equivalence registry, normalize on write

```python
FIELD_EQUIVALENTS = {
    "usage.electric_kwh": ["usage_consumption.electric_kwh", "usage.total_kwh"],
    "rate_info.electric_generation": [
        "rate_tariff.electric_generation_rate",
        "rate_information.electric_rate.generation_charges"
    ]
}

def normalize_on_write(structured_data):
    """Normalize to canonical field names"""
    canonical = {}
    for canonical_path, variants in FIELD_EQUIVALENTS.items():
        # Find value in any variant location
        value = extract_first_found(structured_data, [canonical_path] + variants)
        if value is not None:
            set_nested(canonical, canonical_path, value)
    return canonical
```

**Database Storage:**
```json
{
  "structured_data": {...},  // Original LLM output
  "structured_data_normalized": {...}  // Canonical version for queries
}
```

**Pros:**
- Allows prompt evolution
- Consistent query interface
- Preserves original data

**Cons:**
- Dual storage increases DB size
- Field mapping maintenance
- Need to identify equivalents

---

### Solution 4: **Reprocessing with Best Prompt**

**Concept:** When schema improves significantly, reprocess old documents

```python
async def reprocess_with_improved_prompt(series_id, new_prompt_version):
    """Reprocess all documents in series with latest prompt"""
    documents = await db.get_series_documents(series_id)
    for doc in documents:
        if doc.prompt_version < new_prompt_version:
            # Reprocess with new prompt
            new_extraction = await summarize_dynamic(
                doc.extracted_text, 
                doc.document_type,
                prompt_version=new_prompt_version
            )
            # Update document
            await db.update_structured_data(doc.id, new_extraction)
```

**Pros:**
- All documents eventually consistent
- Best quality extraction for all
- Clean schema across time

**Cons:**
- **Cost:** Reprocessing uses AWS Bedrock API calls ($$$)
- **Time:** Reprocessing 1000s of documents takes time
- Still need migration during reprocessing period

---

### Solution 5: **Hybrid: Versioning + Periodic Reprocessing** ⭐⭐ (Best)

**Combine Solutions 1 and 4:**

1. **Track schema version** per document
2. **Normalize on read** using migration functions (Solution 1)
3. **Periodically reprocess** when schema improves significantly (Solution 4)
4. **Flag for reprocessing** when user views old document

```python
class DocumentProcessor:
    async def get_structured_data(self, doc_id):
        doc = await db.get_document(doc_id)
        current_schema = get_latest_schema_version()
        
        # Check if reprocessing needed
        if doc.schema_version < current_schema and should_reprocess(doc):
            # Queue for background reprocessing
            await reprocess_queue.add(doc_id)
            
        # Return normalized data immediately
        return normalize_to_version(doc.structured_data, doc.schema_version, current_schema)
```

**Reprocessing Triggers:**
- Major schema version bump (1.x → 2.x)
- User views document (lazy reprocessing)
- Series aggregation request (ensure consistency)
- Manual "update all" command

**Pros:**
- Best of both worlds
- Eventual consistency
- User can force updates when needed
- Cost-effective (only reprocess when needed)

**Cons:**
- Most complex to implement
- Requires background job infrastructure

---

## Specific Issues in This Dataset

### Current Problems in PG&E Bills:

1. **Usage fields:** 3 different schema variations across 12 documents
2. **Rate information:** 4 different structures (nested object, flat, strings, nulls)
3. **Billing period:** Inconsistent date formatting
4. **Tag duplication:** Some docs have both `series:pacific-gas-and-electric` and `series:pgande`

### Recommended Fix for This Dataset:

```python
# 1. Define canonical schema for utility bills
CANONICAL_UTILITY_BILL = {
    "utility_provider": str,
    "account_number": str,
    "service_address": str,
    "billing_period": {
        "start_date": "YYYY-MM-DD",
        "end_date": "YYYY-MM-DD"
    },
    "statement_date": "YYYY-MM-DD",
    "due_date": "YYYY-MM-DD",
    "usage": {
        "electric_kwh": float,
        "gas_therms": float
    },
    "charges": {
        "electric_generation": float,
        "electric_delivery": float,
        "gas": float,
        "taxes_and_fees": float
    },
    "total_amount_due": float
}

# 2. Create migration for each variation
# 3. Reprocess or normalize on access
```

---

## Recommendations

### Immediate Actions (Week 1):

1. **Implement Solution 3** (Field Mapping) for quick win
   - Create field equivalence registry
   - Add normalization layer to API
   - Update DataTable component to use normalized data

2. **Add schema_version tracking**
   - Alter documents table: `ADD COLUMN schema_version VARCHAR DEFAULT 'v1'`
   - Track which prompt version created each extraction

3. **Document current schema variations**
   - Audit all document types
   - Create schema registry

### Short Term (Month 1):

4. **Implement Solution 1** (Schema Versioning + Migration)
   - Build migration functions
   - Create schema evolution guide
   - Add normalization to query layer

5. **Add reprocessing command**
   - CLI tool: `./scripts/reprocess-series <series_id>`
   - Allow users to update old extractions

### Long Term (Quarter 1):

6. **Implement Solution 5** (Hybrid approach)
   - Background reprocessing queue
   - Automatic schema upgrades
   - Cost tracking for reprocessing

7. **Build schema evolution metrics**
   - Track schema versions in use
   - Identify documents needing reprocessing
   - Monitor data quality over time

---

## Conclusion

**The self-evolving prompt system is valuable but creates real data consistency challenges.** The current PG&E dataset demonstrates:

- ❌ **Inconsistent field naming** across same document type
- ❌ **Variable data types** for same logical fields
- ❌ **Difficult aggregation and analysis**
- ❌ **Data table display confusion**

**The solution is NOT to abandon prompt evolution**, but to add:

✅ **Schema versioning and tracking**  
✅ **Normalization layer for data access**  
✅ **Field mapping registry**  
✅ **Selective reprocessing capability**  

This allows ALFRD to keep improving while maintaining data consistency for users.

---

**Next Steps:** Would you like me to implement Solution 3 (Field Mapping) as a quick fix, or start with Solution 1 (Schema Versioning) for a more robust long-term approach?