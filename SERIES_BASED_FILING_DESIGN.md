# Series-Based Document Filing - Design Document

**Status:** Implemented (Hybrid Approach)
**Created:** 2025-12-04
**Updated:** 2025-12-04
**Replaces:** Tag-based auto-file system (filing_worker.py)

---

## Problem Statement

The tag-based auto-file system creates fragmented files because the LLM classifier's tags evolve over time:

- **Early documents** (Month 1): Tagged as `[automotive, insurance, recurring, state-farm]`
- **Later documents** (Month 2): Tagged as `[automotive, billing, insurance, recurring, state-farm]`
- **Result**: 12 identical State Farm bills split across 5 different files

This defeats the purpose of automatic organization as the classifier improves.

---

## Solution: Hybrid Series-Based Filing

**Approach:** Combine series entities with tag-based filing for maximum flexibility.

Instead of pure tag-based signatures OR pure series entities, use a **hybrid approach** that:
1. Creates series entities with rich metadata
2. Generates series-specific tags
3. Creates files based on those tags
4. Links documents to both series AND files

### Core Concept

A **Series** is a collection of related recurring documents from the same entity:
- `State Farm Auto Insurance - Monthly Premiums`
- `PG&E Utility Bills - Monthly Electric & Gas`
- `Bay Area Properties LLC - Monthly Rent Receipts`

Each series generates:
- **Series Entity**: Stored in `series` table with metadata
- **Series Tag**: Applied to documents (e.g., `series:state-farm`)
- **Series File**: Auto-created file that groups documents with the series tag

---

## Database Schema

### New `series` Table

```sql
CREATE TABLE series (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Core identification
    title VARCHAR NOT NULL,  -- "State Farm Auto Insurance - Monthly Premiums"
    entity VARCHAR NOT NULL,  -- "State Farm Insurance"
    series_type VARCHAR NOT NULL,  -- "monthly_insurance_bill"
    frequency VARCHAR,  -- "monthly", "annual", "quarterly", etc.
    
    -- LLM-generated description
    description TEXT,  -- "Monthly auto insurance bills for Alex Johnson's Honda Civic"
    
    -- Structured metadata (JSONB)
    metadata JSONB,  -- {"policy_number": "SF-AUTO-2024-987654", "vehicle": "Honda Civic"}
    
    -- Series period
    first_document_date TIMESTAMP,
    last_document_date TIMESTAMP,
    expected_frequency_days INT,  -- 30 for monthly, 365 for annual
    
    -- Document tracking
    document_count INT DEFAULT 0,
    
    -- File generation
    summary_text TEXT,
    summary_metadata JSONB,
    status VARCHAR DEFAULT 'active',  -- active, completed, archived
    
    -- Ownership
    user_id VARCHAR,
    source VARCHAR DEFAULT 'llm',  -- llm or user
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_generated_at TIMESTAMP,
    
    -- Uniqueness constraint
    UNIQUE(entity, series_type, user_id)
);

CREATE INDEX idx_series_entity ON series(entity);
CREATE INDEX idx_series_type ON series(series_type);
CREATE INDEX idx_series_status ON series(status);
CREATE INDEX idx_series_user ON series(user_id);
```

### New `document_series` Junction Table

```sql
CREATE TABLE document_series (
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    series_id UUID REFERENCES series(id) ON DELETE CASCADE,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    added_by VARCHAR DEFAULT 'llm',  -- llm or user
    PRIMARY KEY (document_id, series_id)
);

CREATE INDEX idx_document_series_series ON document_series(series_id);
CREATE INDEX idx_document_series_document ON document_series(document_id);
```

---

## Worker Architecture Changes

### FilingWorker Process Flow (Hybrid Approach)

```
1. Poll for documents with status='summarized'
   ↓
2. For each document:
   a. Extract: summary, document_type, structured_data, tags
   b. Call MCP tool: detect_series(document_data)
   c. LLM returns series metadata
   d. Find or create series in DB
   e. Add document to document_series junction table
   f. Create series-specific tag (e.g., "series:state-farm")
   g. Apply tag to document via document_tags table
   h. Create file based on series tag (if doesn't exist)
   i. Add document to file_documents junction table
   j. Update document status to 'filed'
```

### MCP Tool: `detect_series`

**Input:**
```json
{
  "summary": "State Farm Auto Insurance bill for $150.00 due May 21, 2024",
  "document_type": "insurance",
  "structured_data": {
    "insurance_company_name": "State Farm Insurance",
    "policy_number": "SF-AUTO-2024-987654",
    "premium_amount": 150.0,
    "payment_frequency": "Monthly"
  },
  "tags": ["automotive", "billing", "insurance", "recurring", "state-farm"]
}
```

**LLM Prompt:**
```
Analyze this document and determine what recurring series it belongs to.

Document Summary: {summary}
Document Type: {document_type}
Structured Data: {structured_data}
Tags: {tags}

Identify:
1. Entity Name: The primary organization/company (e.g., "State Farm Insurance")
2. Series Type: Category of recurring series (e.g., "monthly_insurance_bill")
3. Frequency: Recurrence pattern (monthly, quarterly, annual, etc.)
4. Series Title: Human-readable title (e.g., "State Farm Auto Insurance - Monthly Premiums")
5. Description: Brief description of this series
6. Key Metadata: Extract important identifiers (policy numbers, account numbers, etc.)

Return JSON with:
- entity (string): Official entity name
- series_type (string): snake_case category
- frequency (string): monthly/quarterly/annual/weekly/etc.
- title (string): Human-readable series name
- description (string): 1-2 sentence description
- metadata (object): Key identifiers and details
```

**Output:**
```json
{
  "entity": "State Farm Insurance",
  "series_type": "monthly_insurance_bill",
  "frequency": "monthly",
  "title": "State Farm Auto Insurance - Monthly Premiums",
  "description": "Monthly auto insurance bills for Alex Johnson's 2019 Honda Civic",
  "metadata": {
    "policy_number": "SF-AUTO-2024-987654",
    "vehicle": "2019 Honda Civic",
    "policy_holder": "Alex Johnson",
    "coverage_type": "Auto"
  }
}
```

---

## Example Series

### Series 1: State Farm Auto Insurance
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "State Farm Auto Insurance - Monthly Premiums",
  "entity": "State Farm Insurance",
  "series_type": "monthly_insurance_bill",
  "frequency": "monthly",
  "description": "Monthly auto insurance bills for Alex Johnson's 2019 Honda Civic",
  "metadata": {
    "policy_number": "SF-AUTO-2024-987654",
    "vehicle": "2019 Honda Civic",
    "policy_holder": "Alex Johnson"
  },
  "document_count": 12,
  "first_document_date": "2024-01-23T00:00:00Z",
  "last_document_date": "2024-12-21T00:00:00Z",
  "expected_frequency_days": 30,
  "status": "active",
  "source": "llm"
}
```

**All 12 State Farm bills → ONE series** (regardless of tag variations)

### Series 2: PG&E Utility Bills
```json
{
  "id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "title": "PG&E Utility Bills - Monthly Electric & Gas",
  "entity": "Pacific Gas & Electric (PG&E)",
  "series_type": "monthly_utility_bill",
  "frequency": "monthly",
  "description": "Monthly electricity and gas bills for 789 Oak Street, San Francisco",
  "metadata": {
    "account_number": "1234567890",
    "service_address": "789 Oak Street, San Francisco, CA 94109",
    "service_types": ["electricity", "gas"]
  },
  "document_count": 12,
  "status": "active"
}
```

### Series 3: Bay Area Properties Rent
```json
{
  "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "title": "Bay Area Properties LLC - Monthly Rent Receipts",
  "entity": "Bay Area Properties LLC",
  "series_type": "monthly_rent_receipt",
  "frequency": "monthly",
  "description": "Monthly rent payments for 789 Oak Street, San Francisco",
  "metadata": {
    "property_address": "789 Oak Street, San Francisco, CA 94109",
    "monthly_rent": 2400.0,
    "tenant": "Alex Johnson"
  },
  "document_count": 12,
  "status": "active"
}
```

---

## Advantages Over Tag-Based System

| Aspect | Tag-Based Files | Series-Based Files |
|--------|----------------|-------------------|
| **Grouping Logic** | Exact tag match | Semantic similarity |
| **Stability** | Fragments as tags evolve | Stable across classifier versions |
| **State Farm Bills** | 5 different files | 1 series |
| **Organization** | `automotive:billing:insurance:recurring:state-farm` | `State Farm Auto Insurance - Monthly Premiums` |
| **Human Readability** | Low (tag soup) | High (clear titles) |
| **Metadata Richness** | None | Policy numbers, account numbers, etc. |
| **Classifier Evolution** | Breaks grouping | Maintains grouping |

---

## Migration Strategy

### Phase 1: Add Series Tables (This PR)
1. Create `series` table
2. Create `document_series` junction table
3. Keep existing `files` table for backward compatibility

### Phase 2: Update FilingWorker
1. Add `detect_series` MCP tool
2. Update FilingWorker to create series instead of tag-based files
3. Series detection based on entity + series_type + frequency

### Phase 3: File Generation (Existing)
1. FileGeneratorWorker polls for series with status='pending'
2. Aggregates documents in series
3. Generates summary
4. Updates series status to 'generated'

### Phase 4: UI Updates
1. Add `/series` endpoint (like `/files`)
2. Update web UI to show "Series" tab
3. Series list page shows all auto-created series
4. Series detail page shows documents in chronological order

### Phase 5: Migration (Optional)
1. Convert existing tag-based files to series
2. Deprecate tag-based filing logic
3. Remove `file_source` column from files table

---

## API Endpoints

### GET /api/v1/series
List all series with optional filtering

**Query Parameters:**
- `entity` - Filter by entity name
- `series_type` - Filter by series type
- `frequency` - Filter by frequency
- `status` - Filter by status (active/completed/archived)
- `limit` - Max results (default: 50)
- `offset` - Pagination offset

**Response:**
```json
{
  "series": [
    {
      "id": "uuid",
      "title": "State Farm Auto Insurance - Monthly Premiums",
      "entity": "State Farm Insurance",
      "series_type": "monthly_insurance_bill",
      "frequency": "monthly",
      "description": "...",
      "document_count": 12,
      "status": "active"
    }
  ],
  "count": 8,
  "limit": 50,
  "offset": 0
}
```

### GET /api/v1/series/{series_id}
Get series details including all documents

**Response:**
```json
{
  "series": {
    "id": "uuid",
    "title": "State Farm Auto Insurance - Monthly Premiums",
    "entity": "State Farm Insurance",
    "series_type": "monthly_insurance_bill",
    "frequency": "monthly",
    "description": "...",
    "metadata": {...},
    "document_count": 12,
    "summary_text": "...",
    "status": "generated"
  },
  "documents": [
    {
      "id": "doc-uuid",
      "summary": "State Farm Auto Insurance bill for $150.00 due January 23, 2024",
      "created_at": "2024-01-23T00:00:00Z"
    }
  ]
}
```

### POST /api/v1/series/{series_id}/regenerate
Force regeneration of series summary

---

## Implementation Checklist

### Database
- [x] Create `series` table migration
- [x] Create `document_series` table migration
- [x] Add `series` methods to `AlfrdDatabase` class

### MCP Tools
- [x] Create `detect_series` tool in `mcp-server/src/mcp_server/tools/`
- [x] Add Bedrock LLM call for series detection
- [ ] Test series detection with sample documents

### FilingWorker (Hybrid Approach)
- [x] Update `filing_worker.py` to use series detection
- [x] Create series entities in database
- [x] Generate series-specific tags
- [x] Apply tags to documents
- [x] Create files from series tags
- [ ] Test with existing documents

### API
- [ ] Add `GET /api/v1/series` endpoint
- [ ] Add `GET /api/v1/series/{id}` endpoint
- [ ] Add `POST /api/v1/series/{id}/regenerate` endpoint
- [ ] Update OpenAPI docs

### Web UI
- [ ] Add "Series" tab to navigation
- [ ] Create `SeriesPage.jsx` (list view)
- [ ] Create `SeriesDetailPage.jsx` (detail view)
- [ ] Display series metadata and documents

### Testing
- [ ] Test series detection with various document types
- [ ] Test series grouping consistency
- [ ] Test migration from tag-based files
- [ ] End-to-end test: upload → process → series creation

---

## Open Questions

1. **Series Merging**: Should the LLM be able to merge similar series?
   - Example: "State Farm Insurance" vs "State Farm Insurance Company"

2. **Series Splitting**: Should we allow splitting a series into multiple?
   - Example: Split by year (2024 vs 2025)

3. **User Override**: Should users be able to manually create/edit series?
   - Proposal: Add `source='user'` for manually created series

4. **Archived Series**: When to mark a series as `completed` or `archived`?
   - Proposal: After 6 months of no new documents

---

## Hybrid Implementation Details

### Series Tag Format

Series tags follow the pattern: `series:<entity-slug>`

Examples:
- `series:state-farm` (State Farm Insurance)
- `series:pacific-gas-and-electric` (PG&E)
- `series:bay-area-properties` (Landlord)

### Benefits of Hybrid Approach

1. **Rich Metadata**: Series entities store detailed information (frequency, dates, metadata)
2. **Tag Integration**: Series tags work with existing tag features (search, filters)
3. **File Compatibility**: Files auto-created for each series using existing infrastructure
4. **Backward Compatible**: Existing tag and file systems continue to work
5. **Stable Grouping**: Documents grouped by semantic series, not fragile tag combinations

---

**Status:** ✅ Implemented (Hybrid Approach)
**Next Steps:**
1. Add API endpoints for series management
2. Create web UI for viewing series
3. Test with sample documents