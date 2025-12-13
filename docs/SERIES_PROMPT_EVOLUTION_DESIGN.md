# Series-Specific Prompt Evolution Design

**Date:** 2025-12-10  
**Status:** Proposed Design  
**Author:** Design session feedback

---

## Core Concept

Instead of having a single generic prompt per document type that evolves globally, **each series gets its own specialized prompt** that evolves specifically for that vendor/entity's document format. This solves the schema drift problem while maintaining self-improvement.

---

## The Workflow

### Phase 1: Initial Document Processing (Generic)

```
1. Document arrives → OCR
2. Classify document → "utility_bill"
3. Summarize with GENERIC utility_bill prompt → structured_data (generic schema)
4. Score & evolve the GENERIC prompt (global improvement)
```

### Phase 2: Series Assignment & Specialization

```
5. Detect series → "PG&E Monthly Bills"
6. Check if series has custom prompt
   
   IF series_prompt EXISTS:
       - Use series-specific prompt
   ELSE:
       - Create NEW series_prompt from generic prompt
       - Initialize with schema tailored to this vendor
   
7. Summarize AGAIN with series_prompt → structured_data_series (consistent schema)
8. Store BOTH extractions:
   - structured_data: Generic extraction
   - structured_data_series: Series-specific extraction (preferred for display)
```

### Phase 3: Series Prompt Evolution & Regeneration

```
9. Score the series extraction quality
10. Evolve the series_prompt based on this specific vendor's patterns

11. IF series_prompt improves beyond threshold:
    - Mark as new version
    - REGENERATE all previous documents in this series
    - Update all structured_data_series fields
    - Now entire series has consistent schema!
```

---

## Database Schema Changes

### Use Existing `prompts` Table (No New Table Needed!)

The existing `prompts` table already supports what we need:

```sql
-- Existing schema (from api-server/src/api_server/db/schema.sql)
CREATE TABLE IF NOT EXISTS prompts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    prompt_type VARCHAR NOT NULL CHECK (prompt_type IN ('classifier', 'summarizer', 'file_summarizer', 'series_detector')),
    document_type VARCHAR,  -- NULL for classifier, specific type for summarizers
    prompt_text TEXT NOT NULL,
    version INTEGER DEFAULT 1,
    performance_score FLOAT,
    performance_metrics JSONB,  -- Can store schema definition here!
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT true,
    user_id VARCHAR,
    
    UNIQUE(prompt_type, document_type, version, user_id)
);
```

**How to use for series prompts:**
- `prompt_type` = `'series_summarizer'` (new type)
- `document_type` = `series_id` (store series UUID as string)
- `performance_metrics` JSONB = store schema definition + stats
- `version` = prompt version for this series
- `is_active` = TRUE for current version

### Extend Existing `prompts` Table

```sql
-- Add 'series_summarizer' to prompt_type check constraint
ALTER TABLE prompts DROP CONSTRAINT IF EXISTS prompts_prompt_type_check;
ALTER TABLE prompts ADD CONSTRAINT prompts_prompt_type_check
    CHECK (prompt_type IN ('classifier', 'summarizer', 'file_summarizer', 'series_detector', 'series_summarizer'));
```

### Update `documents` Table

```sql
-- Add series-specific extraction storage
ALTER TABLE documents
ADD COLUMN structured_data_series JSONB,           -- Series-specific extraction
ADD COLUMN series_prompt_id UUID REFERENCES prompts(id),  -- Which series prompt was used
ADD COLUMN extraction_method VARCHAR DEFAULT 'generic';  -- 'generic' or 'series'

-- Index for series extraction queries
CREATE INDEX idx_documents_series_data ON documents
USING GIN(structured_data_series);
```

### Update `series` Table

```sql
ALTER TABLE series
ADD COLUMN active_prompt_id UUID REFERENCES prompts(id),
ADD COLUMN last_schema_update TIMESTAMP WITH TIME ZONE,
ADD COLUMN regeneration_pending BOOLEAN DEFAULT FALSE;
```

---

## Prompt Structure

### Generic Prompt (Document Type Level)

```yaml
# prompts/summarizers/utility_bill.yaml
system: |
  Extract structured data from utility bills.
  
user_template: |
  Extract the following from this utility bill:
  
  Required fields:
  - utility_provider (string)
  - total_amount_due (number)
  - due_date (YYYY-MM-DD)
  
  Optional fields:
  - usage.electric_kwh (number)
  - usage.gas_therms (number)
  - charges.electric_generation (number)
  - charges.electric_delivery (number)
  - charges.gas (number)
  - charges.taxes_and_fees (number)
  
  Return as JSON with these exact field names.
```

### Series-Specific Prompt (PG&E Variant)

```yaml
# Generated dynamically, stored in series_prompts table
system: |
  Extract structured data from PG&E utility bills.
  This prompt is specialized for Pacific Gas & Electric's specific format.
  
user_template: |
  Extract the following from this PG&E bill:
  
  REQUIRED FIELDS (strict schema):
  {
    "utility_provider": "PG&E",
    "account_number": "string (format: 123456789)",
    "service_address": "string",
    "billing_period": {
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD"
    },
    "statement_date": "YYYY-MM-DD",
    "due_date": "YYYY-MM-DD",
    "usage": {
      "electric_kwh": number,
      "gas_therms": number
    },
    "charges": {
      "electric_generation": number,
      "electric_delivery": number,
      "gas": number,
      "taxes_and_fees": number
    },
    "previous_balance": number,
    "total_amount_due": number,
    "rate_schedule": {
      "electric_generation_rate": number,  // per kWh
      "electric_delivery_rate": number,    // per kWh
      "gas_rate": number                   // per therm
    },
    "late_payment_fee": number
  }
  
  IMPORTANT:
  - Use EXACT field names above
  - billing_period dates: Parse from text like "January 27, 2024 to February 26, 2024"
  - All monetary values as numbers (no strings)
  - If field not found, use null (not string "N/A")
  - electric_kwh and gas_therms are ALWAYS numbers, never strings
  
  PG&E-SPECIFIC NOTES:
  - Account number is always 9 digits
  - Service address format: street, apt, city, state, zip
  - Rate schedules appear in "Charges" section
  - Statement date is in top right of bill
```

---

## Implementation Details

### New MCP Tool: `summarize_with_series_prompt`

```python
# mcp-server/src/mcp_server/tools/summarize_series.py

async def summarize_with_series_prompt(
    document_id: str,
    series_id: str,
    extracted_text: str
) -> dict:
    """
    Summarize document using series-specific prompt.
    Creates new prompt if series doesn't have one yet.
    """
    # Get or create series prompt
    series_prompt = await get_active_series_prompt(series_id)
    
    if not series_prompt:
        # First document in series - create prompt from generic
        base_prompt = await get_generic_prompt(document_type)
        series_prompt = await create_series_prompt(
            series_id=series_id,
            base_prompt=base_prompt,
            initial_document=extracted_text
        )
    
    # Use series-specific prompt
    response = await bedrock_client.invoke_model(
        prompt=series_prompt.prompt_text,
        document_text=extracted_text,
        schema=series_prompt.schema_definition
    )
    
    # Validate against expected schema
    if not validate_schema(response, series_prompt.schema_definition):
        logger.warning(f"Series extraction didn't match schema for {document_id}")
    
    return {
        "structured_data": response,
        "prompt_version": series_prompt.version,
        "schema_version": series_prompt.version
    }
```

### Automatic Schema Initialization

```python
async def create_series_prompt(
    series_id: str,
    base_prompt: dict,
    initial_document: str
) -> SeriesPrompt:
    """
    Create first series-specific prompt by analyzing initial document.
    """
    # Ask LLM to analyze document and suggest schema
    schema_suggestion = await bedrock_client.invoke_model(
        prompt=f"""
        Analyze this document and suggest a strict JSON schema for extracting data.
        
        Base schema template:
        {base_prompt['schema']}
        
        Document:
        {initial_document}
        
        Suggest:
        1. Required fields and their types
        2. Optional fields specific to this vendor
        3. Validation rules (formats, ranges)
        4. Vendor-specific extraction notes
        
        Return as JSON schema.
        """
    )
    
    # Create series prompt
    series_prompt = await db.create_series_prompt(
        series_id=series_id,
        prompt_text=base_prompt['template'],
        schema_definition=schema_suggestion['schema'],
        version=1,
        created_from='generic'
    )
    
    # Link to series
    await db.update_series(series_id, active_prompt_id=series_prompt.id)
    
    return series_prompt
```

### Series Regeneration Logic

```python
async def regenerate_series(series_id: str, new_prompt_version: int):
    """
    Regenerate all documents in series with improved prompt.
    """
    series_prompt = await db.get_series_prompt(series_id, new_prompt_version)
    documents = await db.get_series_documents(series_id)
    
    logger.info(f"Regenerating {len(documents)} documents in series {series_id}")
    
    for doc in documents:
        try:
            # Re-extract with new series prompt
            new_extraction = await summarize_with_series_prompt(
                document_id=doc.id,
                series_id=series_id,
                extracted_text=doc.extracted_text
            )
            
            # Update document
            await db.update_document(
                doc.id,
                structured_data_series=new_extraction['structured_data'],
                series_prompt_version=new_prompt_version,
                extraction_method='series'
            )
            
            logger.info(f"Regenerated document {doc.id}")
            
        except Exception as e:
            logger.error(f"Failed to regenerate {doc.id}: {e}")
            # Continue with other documents
    
    # Mark series as up-to-date
    await db.update_series(
        series_id,
        last_schema_update=datetime.utcnow(),
        regeneration_pending=False
    )
```

---

## Updated Processing Pipeline

### New Task: `series_summarize_task`

```python
# document-processor/src/document_processor/tasks/document_tasks.py

@task
async def series_summarize_task(document_id: str):
    """
    Step 6: Summarize with series-specific prompt (after file task).
    """
    doc = await db.get_document(document_id)
    
    if not doc.series_id:
        logger.info(f"Document {document_id} not in series, skipping series summarization")
        return
    
    # Summarize with series prompt
    result = await summarize_with_series_prompt(
        document_id=document_id,
        series_id=doc.series_id,
        extracted_text=doc.extracted_text
    )
    
    # Update document
    await db.update_document(
        document_id,
        structured_data_series=result['structured_data'],
        series_prompt_version=result['prompt_version'],
        extraction_method='series',
        status='series_summarized'
    )
    
    logger.info(f"Series summarization complete for {document_id}")
```

### New Task: `score_series_extraction_task`

```python
@task
async def score_series_extraction_task(document_id: str):
    """
    Step 7: Score series extraction and evolve series prompt.
    Background task (fire-and-forget).
    """
    doc = await db.get_document(document_id)
    series_prompt = await db.get_active_series_prompt(doc.series_id)
    
    # Score the extraction
    score = await score_series_extraction(
        document_id=document_id,
        series_id=doc.series_id,
        extraction=doc.structured_data_series,
        expected_schema=series_prompt.schema_definition
    )
    
    # Update prompt stats
    await db.increment_series_prompt_stats(
        series_prompt.id,
        score=score
    )
    
    # Check if evolution needed
    if should_evolve_series_prompt(series_prompt, score):
        new_prompt = await evolve_series_prompt(
            series_id=doc.series_id,
            current_prompt=series_prompt,
            recent_documents=await db.get_recent_series_documents(doc.series_id, limit=10)
        )
        
        # Check if improvement is significant
        if new_prompt.predicted_score > series_prompt.performance_score + 0.1:
            logger.info(f"Series prompt improved significantly for series {doc.series_id}")
            
            # Create new version
            new_version = await db.create_series_prompt(
                series_id=doc.series_id,
                prompt_text=new_prompt.text,
                schema_definition=new_prompt.schema,
                version=series_prompt.version + 1,
                created_from='evolved'
            )
            
            # Mark for regeneration
            await db.update_series(
                doc.series_id,
                active_prompt_id=new_version.id,
                regeneration_pending=True
            )
            
            # Trigger regeneration (async)
            await regenerate_series(doc.series_id, new_version.version)
```

---

## Pipeline Flow (Updated)

```
Document Processing:
1. OCR Step → extracted_text
2. Classify Step → document_type = "utility_bill"
3. Summarize Step (Generic) → structured_data
4. [Background] Score Classification
5. File Step → Detect series, assign series_id = "pgande"
6. Series Summarize Step → structured_data_series (consistent schema!)
7. [Background] Score Series Extraction
8. [Conditional] If score improves, regenerate entire series
9. Complete Step → status = "completed"
```

---

## Benefits of This Approach

### ✅ Solves Schema Drift
- **Each series has consistent schema** across all documents
- PG&E bills always use same field names
- SCL bills use their own consistent schema
- No more `usage` vs `usage_consumption` confusion

### ✅ Maintains Self-Improvement
- Generic prompts still evolve (benefits new document types)
- Series prompts evolve specifically for that vendor
- Best of both worlds

### ✅ Automatic Consistency
- When series prompt improves, **entire series gets regenerated**
- Old documents automatically updated with better schema
- User sees consistent data tables

### ✅ Cost-Effective Regeneration
- Only regenerate series when significant improvement
- Threshold-based triggering (e.g., 0.1 score improvement)
- Not all documents need reprocessing, just series members

### ✅ Dual Extraction Safety
- Keep both `structured_data` (generic) and `structured_data_series` (specialized)
- Fallback if series extraction fails
- Can compare quality between approaches

---

## User Experience

### Data Table Display

```python
# API endpoint: GET /api/v1/files/{file_id}
def get_file_data(file_id):
    documents = db.get_file_documents(file_id)
    
    # Use series extraction (preferred) with fallback to generic
    for doc in documents:
        doc.display_data = doc.structured_data_series or doc.structured_data
    
    # Now all PG&E bills have identical field structure!
    return {
        "documents": documents,
        "schema": get_series_schema(documents[0].series_id)  # Show expected schema
    }
```

**Result:** Perfect data table with consistent columns! 🎉

---

## Configuration

### Thresholds (in `shared/config.py`)

```python
# Series prompt evolution
series_prompt_min_documents: int = 3  # Need 3 docs before evolving series prompt
series_prompt_improvement_threshold: float = 0.1  # 10% improvement triggers regen
series_regeneration_batch_size: int = 10  # Regen 10 docs at a time

# Cost controls
max_series_regenerations_per_day: int = 5  # Limit API costs
series_regen_cooldown_hours: int = 24  # Wait 24h between regens
```

---

## Migration Plan

### Phase 1: Add Infrastructure (Week 1)
1. Create `series_prompts` table
2. Add `structured_data_series` column to documents
3. Implement `summarize_with_series_prompt` tool
4. Add `series_summarize_task` to pipeline

### Phase 2: Initial Series Prompts (Week 2)
5. For existing series, generate initial series prompts from current documents
6. Run series summarization on all existing documents
7. Compare generic vs series extractions

### Phase 3: Enable Evolution (Week 3)
8. Add `score_series_extraction_task`
9. Implement prompt evolution logic
10. Enable regeneration with conservative thresholds

### Phase 4: Optimize (Month 2)
11. Tune thresholds based on real data
12. Add UI for viewing series schemas
13. Allow manual trigger of series regeneration

---

## Open Questions

1. **Regeneration Timing**: Immediate or queue for off-hours?
   - **Suggestion:** Queue for low-traffic hours to manage API costs

2. **User Notification**: Tell user when series is regenerating?
   - **Suggestion:** Show "Updating..." badge in UI, auto-refresh when done

3. **Prompt Creation**: Automatic or manual review?
   - **Suggestion:** Automatic creation, optional manual refinement

4. **Fallback Strategy**: What if series extraction fails?
   - **Suggestion:** Always keep generic extraction as fallback

5. **Cross-Series Learning**: Can series prompts learn from each other?
   - **Suggestion:** Future enhancement - use best practices across similar vendors

---

## Cost Analysis

### Current Cost (Without Series Prompts)
- 1 document = 1 generic summarization = $0.003

### New Cost (With Series Prompts)
- 1 document = 1 generic + 1 series summarization = $0.006
- **Double the cost per document**

### Regeneration Cost
- Series of 12 documents improved = 12 × $0.003 = $0.036
- If series evolves 3 times = 3 × $0.036 = $0.108 total

### Mitigation
- Set aggressive improvement threshold (0.1+)
- Limit regenerations per day
- Only regenerate series user actually views
- Cache extractions aggressively

---

## Conclusion

This **series-specific prompt evolution** approach is elegant because:

1. ✅ **Solves the schema drift problem** - Each series has consistent structure
2. ✅ **Maintains self-improvement** - Prompts still evolve, but in focused way
3. ✅ **Automatic consistency** - Regeneration keeps entire series in sync
4. ✅ **Clear data tables** - PG&E bills all have identical schema
5. ✅ **Scalable** - Each vendor/entity gets optimized extraction

**Trade-off:** 2x processing cost per document, but the consistency benefit is worth it for a personal document management system.

**Recommendation:** Implement this design. The "series as unit of schema consistency" is the right mental model.

---

**Next Steps:** 
1. Review this design
2. Adjust thresholds and cost controls
3. Start implementation with Phase 1
4. Test with PG&E series as pilot
