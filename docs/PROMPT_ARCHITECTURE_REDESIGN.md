# Prompt Architecture Redesign - Static vs Evolving Prompts

**Date:** 2025-12-12  
**Issue:** Schema drift in series-based document extraction  
**Status:** Design Complete, Implementation Pending

---

## Executive Summary

ALFRD currently suffers from schema drift where documents in the same series (e.g., 12 monthly State Farm insurance bills) have **inconsistent field names** in their structured data. The root cause is that prompts evolve independently without proper categorization and context injection.

**Solution:** Implement a **Static vs Evolving** prompt architecture with dynamic context injection to ensure consistency.

---

## Problem Analysis

### Observed Symptoms

1. **Schema Drift Within Series**
   - 12 State Farm insurance documents have **12 different schemas**
   - Example field variations:
     - `total_monthly_premium` vs `premium_amount` vs `amount_due`
     - `insured_vehicle` (object) vs `insured_vehicle_year_make_model` (string)
     - `coverage_period` vs `policy_period` vs `policy_period_start/end`

2. **Duplicate Series Creation**
   - 3 separate series for what should be 1:
     - "State Farm Insurance" + "monthly_insurance_bill" (11 docs)
     - "State Farm Insurance" + "monthly_auto_insurance_bill" (1 doc)
     - "State Farm **Auto** Insurance" + "monthly_insurance_bill" (2 docs)

3. **Each Document Gets Own Prompt**
   - Every document has different `series_prompt_id` (12 unique UUIDs)
   - Each prompt used only once (`documents_using_this_prompt = 1`)
   - All prompts have `is_active = false` and `version = 1`

### Root Causes

1. **Missing Context Injection**
   - **Classifier**: Doesn't inject existing tags → creates duplicate tags
   - **Series Detector**: Doesn't inject existing series → creates duplicate series

2. **No Prompt Type Differentiation**
   - All prompts treated as "evolving" when some should be static
   - No score ceiling to stop evolution when "good enough"

3. **No Regeneration Mechanism**
   - Series prompts evolve but old documents aren't regenerated
   - Creates schema drift within series

---

## Proposed Architecture

### Prompt Behavior Types

```python
class PromptBehavior(Enum):
    STATIC = "static"                          # Never evolves
    EVOLVING = "evolving"                      # Evolves with ceiling
    EVOLVING_WITH_REGEN = "evolving_with_regen" # Evolves + regenerates
```

### Prompt Configuration

All prompts stored in **same database table** (`prompts`), differentiated by configuration:

| Prompt Type | Behavior | Can Evolve | Score Ceiling | Regenerates | Context Injection |
|-------------|----------|------------|---------------|-------------|-------------------|
| **classifier** | STATIC | ❌ | N/A | N/A | All unique tag combinations (excluding `series:*`) |
| **series_detector** | STATIC | ❌ | N/A | N/A | All existing series + tags + summary |
| **file_summarizer** | STATIC | ❌ | N/A | N/A | None |
| **summarizer** (generic) | EVOLVING | ✅ | 0.95 | ❌ | None |
| **series_summarizer** | EVOLVING_WITH_REGEN | ✅ | 0.95 | ✅ | None |

---

## Implementation Guide

### Phase 1: Database Schema Updates

```sql
-- Add prompt behavior tracking columns
ALTER TABLE prompts ADD COLUMN can_evolve BOOLEAN DEFAULT TRUE;
ALTER TABLE prompts ADD COLUMN score_ceiling FLOAT DEFAULT 0.95;
ALTER TABLE prompts ADD COLUMN regenerates_on_update BOOLEAN DEFAULT FALSE;

-- Update existing prompts to mark as static
UPDATE prompts 
SET can_evolve = FALSE, score_ceiling = NULL
WHERE prompt_type IN ('classifier', 'series_detector', 'file_summarizer');

-- Update existing series_summarizer to enable regeneration
UPDATE prompts
SET regenerates_on_update = TRUE
WHERE prompt_type = 'series_summarizer';
```

### Phase 2: Move Hardcoded Prompts to Database

**File:** `mcp-server/src/mcp_server/tools/detect_series.py`

**Current:** Lines 13-41 contain hardcoded `SERIES_DETECTION_SYSTEM_PROMPT`

**Action:**
1. Create database entry for series_detector prompt
2. Load via data loader script
3. Update `detect_series()` to fetch from database instead of constant

```python
# scripts/load-prompts-to-db (update)

series_detector_prompt = """You are a document series detection expert...
[Move content from detect_series.py line 13-41]
"""

await db.create_prompt(
    prompt_id=uuid4(),
    prompt_type='series_detector',
    document_type=None,
    prompt_text=series_detector_prompt,
    version=1,
    can_evolve=False,  # STATIC
    score_ceiling=None,
    regenerates_on_update=False
)
```

### Phase 3: Context Injection Functions

**File:** `shared/database.py`

Add helper methods for injecting dynamic context:

```python
async def get_unique_tag_combinations(
    self, 
    exclude_prefix: str = None,
    limit: int = 100
) -> List[List[str]]:
    """Get all unique tag combinations for classifier context.
    
    Args:
        exclude_prefix: Exclude tags starting with this (e.g., 'series:')
        limit: Maximum number of combinations to return
        
    Returns:
        List of tag combinations, e.g., [['bill', 'utilities'], ['insurance', 'monthly']]
    """
    await self.initialize()
    
    async with self.pool.acquire() as conn:
        query = """
            SELECT 
                array_agg(t.tag_name ORDER BY t.tag_name) as tag_combo
            FROM documents d
            INNER JOIN document_tags dt ON d.id = dt.document_id
            INNER JOIN tags t ON dt.tag_id = t.id
            WHERE d.status = 'completed'
        """
        
        if exclude_prefix:
            query += " AND NOT t.tag_name LIKE $1"
            
        query += """
            GROUP BY d.id
            HAVING COUNT(*) > 0
            ORDER BY COUNT(*) DESC
            LIMIT $2
        """
        
        params = [f"{exclude_prefix}%" if exclude_prefix else None, limit]
        params = [p for p in params if p is not None]
        
        rows = await conn.fetch(query, *params)
        return [row['tag_combo'] for row in rows if row['tag_combo']]


async def get_all_series_with_context(self, limit: int = 50) -> List[Dict]:
    """Get all series with context for series_detector.
    
    Returns:
        List of series with entity, series_type, tags, and sample metadata
    """
    await self.initialize()
    
    async with self.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT 
                s.id,
                s.entity,
                s.series_type,
                s.title,
                s.frequency,
                s.metadata,
                array_agg(DISTINCT t.tag_name) FILTER (WHERE t.tag_name LIKE 'series:%') as series_tags
            FROM series s
            LEFT JOIN document_series ds ON s.id = ds.series_id
            LEFT JOIN document_tags dt ON ds.document_id = dt.document_id
            LEFT JOIN tags t ON dt.tag_id = t.id
            WHERE s.status = 'active'
            GROUP BY s.id, s.entity, s.series_type, s.title, s.frequency, s.metadata
            ORDER BY s.document_count DESC
            LIMIT $1
        """, limit)
        
        return [dict(row) for row in rows]
```

### Phase 4: Update Task Functions with Context Injection

**File:** `document-processor/src/document_processor/tasks/document_tasks.py`

#### 4a. Update `classify_step()` (lines 195-297)

```python
# BEFORE (line 223):
known_types = [t['type_name'] for t in await db.get_document_types()]
existing_tags = await db.get_popular_tags(limit=50)

# AFTER:
known_types = [t['type_name'] for t in await db.get_document_types()]

# NEW: Inject unique tag combinations for consistency
tag_combinations = await db.get_unique_tag_combinations(exclude_prefix='series:', limit=100)

# Format for LLM context
tag_combo_text = "\n".join([
    f"  - {', '.join(tags)}" 
    for tags in tag_combinations[:20]  # Top 20 most common
])

# Update prompt with context
prompt_with_context = f"""{prompt['prompt_text']}

EXISTING TAG COMBINATIONS IN DATABASE:
{tag_combo_text}

IMPORTANT: Reuse existing tags when appropriate to maintain consistency."""
```

#### 4b. Update `file_step()` (lines 647-726)

```python
# BEFORE (line 667-674):
series_data = detect_series_with_retry(
    summary=doc['summary'],
    document_type=doc['document_type'],
    structured_data=structured_data,
    tags=tags,
    bedrock_client=bedrock_client
)

# AFTER:
# NEW: Get existing series context
existing_series = await db.get_all_series_with_context(limit=50)

# NEW: Pass context to detect_series
series_data = detect_series_with_retry(
    summary=doc['summary'],
    document_type=doc['document_type'],
    structured_data=structured_data,
    tags=tags,
    existing_series=existing_series,  # NEW parameter
    bedrock_client=bedrock_client
)
```

#### 4c. Update `detect_series()` in `mcp-server/src/mcp_server/tools/detect_series.py`

```python
def detect_series(
    summary: str,
    document_type: str,
    structured_data: Dict[str, Any],
    tags: list[str],
    bedrock_client,
    existing_series: List[Dict] = None  # NEW parameter
) -> Dict[str, Any]:
    """Detect which series a document belongs to using LLM analysis."""
    
    # NEW: Format existing series for context
    series_context = ""
    if existing_series:
        series_list = []
        for s in existing_series[:20]:  # Top 20
            series_tags = ', '.join(s.get('series_tags', []))
            series_list.append(
                f"  - {s['entity']} ({s['series_type']}) [{series_tags}]"
            )
        series_context = "\n\nEXISTING SERIES IN DATABASE:\n" + "\n".join(series_list)
        series_context += "\n\nIMPORTANT: Reuse existing series when appropriate. Use exact entity names."
    
    # Build context with existing series
    context = f"""Document Summary: {summary}

Document Type: {document_type}

Structured Data: {json.dumps(structured_data, indent=2)}

Tags: {', '.join(tags)}{series_context}"""
    
    # ... rest of function unchanged
```

### Phase 5: Update Scoring Logic with Ceiling

**File:** `document-processor/src/document_processor/tasks/document_tasks.py`

Create helper function:

```python
def should_evolve_prompt(prompt: Dict, score: float, settings) -> bool:
    """Check if prompt should evolve based on behavior config."""
    
    # Check if evolution is allowed
    if not prompt.get('can_evolve', True):
        logger.info(f"Prompt {prompt['prompt_type']} is static, skipping evolution")
        return False
    
    # Check score ceiling
    current_score = prompt.get('performance_score') or 0
    ceiling = prompt.get('score_ceiling', 0.95)
    
    if current_score >= ceiling:
        logger.info(
            f"Score {current_score:.2f} >= ceiling {ceiling:.2f}, "
            f"good enough - not evolving"
        )
        return False
    
    # Check improvement threshold
    if score <= current_score + settings.prompt_update_threshold:
        return False
    
    return True
```

Update scoring steps:

```python
# In score_classification_step() (line 494):
if not should_evolve_prompt(prompt, score_result['score'], settings):
    return score_result['score']

# In score_summary_step() (line 598):
if not should_evolve_prompt(prompt, score_result['score'], settings):
    return score_result['score']

# In score_series_extraction_step() (line 1082):
if not should_evolve_prompt(series_prompt, score_result['score'], settings):
    return score_result['score']
```

### Phase 6: Initial Data Load

**File:** `scripts/load-prompts-to-db`

Update to set `can_evolve` flag:

```python
# Classifier (STATIC)
await db.create_prompt(
    prompt_id=uuid4(),
    prompt_type='classifier',
    document_type=None,
    prompt_text=classifier_prompt_text,
    version=1,
    can_evolve=False,  # STATIC
    score_ceiling=None,
    regenerates_on_update=False
)

# Series Detector (STATIC) - NEW!
await db.create_prompt(
    prompt_id=uuid4(),
    prompt_type='series_detector',
    document_type=None,
    prompt_text=series_detector_prompt_text,
    version=1,
    can_evolve=False,  # STATIC
    score_ceiling=None,
    regenerates_on_update=False
)

# File Summarizer (STATIC)
await db.create_prompt(
    prompt_id=uuid4(),
    prompt_type='file_summarizer',
    document_type=None,
    prompt_text=file_summarizer_prompt_text,
    version=1,
    can_evolve=False,  # STATIC
    score_ceiling=None,
    regenerates_on_update=False
)

# Generic Summarizers (EVOLVING)
for doc_type in ['insurance', 'bill', 'finance', ...]:
    await db.create_prompt(
        prompt_id=uuid4(),
        prompt_type='summarizer',
        document_type=doc_type,
        prompt_text=summarizer_prompts[doc_type],
        version=1,
        can_evolve=True,  # EVOLVING
        score_ceiling=0.95,
        regenerates_on_update=False
    )
```

---

## Testing Plan

### Unit Tests

1. **Test Context Injection**
   ```bash
   pytest -k test_get_unique_tag_combinations
   pytest -k test_get_all_series_with_context
   ```

2. **Test Prompt Evolution Logic**
   ```bash
   pytest -k test_should_evolve_prompt
   ```

### Integration Tests

1. **Test Static Prompts Don't Evolve**
   - Process 10 documents with classifier
   - Verify prompt version stays at 1
   - Verify tags are reused

2. **Test Series Reuse**
   - Process 12 monthly insurance bills
   - Verify only 1 series created
   - Verify all use same `series_prompt_id`

3. **Test Score Ceiling**
   - Create prompt with score 0.94
   - Score new document at 0.96
   - Verify prompt evolves
   - Create another prompt with score 0.96
   - Score new document at 0.97
   - Verify prompt does NOT evolve (ceiling reached)

---

## Migration Guide

### For Existing Databases

```bash
# 1. Backup
pg_dump -U alfrd_user alfrd > backup_$(date +%Y%m%d).sql

# 2. Apply schema changes
psql -U alfrd_user -d alfrd < migration_static_prompts.sql

# 3. Update existing prompts
psql -U alfrd_user -d alfrd -c "
UPDATE prompts 
SET can_evolve = FALSE 
WHERE prompt_type IN ('classifier', 'file_summarizer');
"

# 4. Load series_detector prompt
./scripts/load-prompts-to-db

# 5. Verify
psql -U alfrd_user -d alfrd -c "
SELECT prompt_type, can_evolve, score_ceiling 
FROM prompts 
WHERE is_active = TRUE;
"
```

---

## Benefits

1. **Eliminates Schema Drift**
   - Series prompts evolve together (all docs regenerated)
   - Static prompts prevent category creep

2. **Prevents Duplicate Series**
   - Series detector sees existing series
   - Reuses entity names consistently

3. **Improves Tag Consistency**
   - Classifier sees existing tag combinations
   - Reuses tags instead of creating variations

4. **Stops Over-Optimization**
   - Score ceiling prevents endless evolution
   - "Good enough" is actually good enough (0.95)

5. **Same Storage, Different Behavior**
   - All prompts in one table
   - Python classes handle behavior differences
   - Easy to modify via database

---

## Future Enhancements

1. **Prompt Templates**
   - Pre-built templates for common series types
   - User-customizable prompt library

2. **A/B Testing**
   - Test prompt variations
   - Auto-select best performing

3. **Prompt Inheritance**
   - Series prompts inherit from generic
   - Override specific fields only

4. **Manual Override**
   - UI to edit prompts
   - Force regeneration on demand

---

**Implementation Status:** Design Complete  
**Next Steps:** Phase 1 - Database Schema Updates