# Files Feature Design

**Status:** Planning Phase (2025-11-30)

---

## Executive Summary

**Files** are auto-generated, LLM-summarized document collections grouped by type and tags. They provide chronological context and insights across related documents (e.g., all "bill" documents tagged "lexus-tx-550").

### Key Concepts

- **File** = Collection of related documents (type + tags)
- **Lazy Generation** = Created on-demand, then kept up-to-date
- **Self-Improving** = Prompts evolve via scorer workers
- **Chronological** = Documents ordered by date for temporal context

---

## Use Cases

### Example 1: Vehicle Maintenance History
```
Type: bill
Tags: lexus-tx-550

File Contents:
- 2024-01-15: Oil change at Lexus dealer - $89.50
- 2024-03-20: Tire rotation - $45.00
- 2024-06-10: Brake service - $450.00
- 2024-09-05: 30k mile service - $350.00

Generated Summary:
"Total maintenance costs for Lexus TX 550 in 2024: $934.50
Average cost per service: $233.63
Most expensive: Brake service ($450)
Trend: Regular maintenance schedule being followed"
```

### Example 2: Utility Bill Tracking
```
Type: bill
Tags: pge, electricity

File Contents:
- Nov 2024: $245.67 (usage: 850 kWh)
- Oct 2024: $198.43 (usage: 720 kWh)
- Sep 2024: $312.89 (usage: 1,100 kWh)

Generated Summary:
"PG&E electricity costs averaging $252.33/month
Peak usage in September (summer cooling)
30% increase from Oct to Nov suggests heating usage increase"
```

### Example 3: University Documents
```
Type: school
Tags: stanford, cs-department

File Contents:
- Course enrollment confirmation
- Tuition payment receipt
- Grade report
- Department event invitation

Generated Summary:
"Stanford CS Department academic records for Fall 2024
Enrolled in 4 courses, tuition paid in full
Current GPA: 3.8"
```

---

## Architecture

### Database Schema

```sql
-- Files table
CREATE TABLE files (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_type VARCHAR NOT NULL,
    tags JSONB NOT NULL,              -- Array of tags
    tag_signature VARCHAR NOT NULL,    -- Sorted, lowercase "bill:lexus-tx-550"
    
    -- File metadata
    document_count INT DEFAULT 0,
    first_document_date TIMESTAMP,
    last_document_date TIMESTAMP,
    
    -- Generated content
    aggregated_content TEXT,           -- Raw aggregated document summaries (for reference)
    summary_text TEXT,                 -- AI-generated summary of aggregated content
    summary_metadata JSONB,            -- Structured insights (totals, trends, etc.)
    
    -- Prompt tracking
    prompt_version UUID REFERENCES prompts(id),
    
    -- Status
    status VARCHAR NOT NULL CHECK (status IN (
        'pending',      -- Needs generation
        'generated',    -- Summary created
        'outdated',     -- New documents added
        'regenerating'  -- Being updated
    )),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_generated_at TIMESTAMP,
    
    UNIQUE(tag_signature)
);

-- Index for quick lookups
CREATE INDEX idx_files_type_tags ON files USING GIN(tags);
CREATE INDEX idx_files_status ON files(status);

-- File-document associations
CREATE TABLE file_documents (
    file_id UUID REFERENCES files(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (file_id, document_id)
);

-- File prompts (self-improving)
-- Extends existing prompts table
INSERT INTO prompts (prompt_type, document_type, prompt_text, version)
VALUES ('file_summarizer', NULL, 'Default file summarization prompt...', 1);
```

### Tag Signature Format

To ensure uniqueness, files use a normalized tag signature:

```python
def create_tag_signature(document_type: str, tags: list[str]) -> str:
    """Create normalized signature for file lookup."""
    # Sort tags alphabetically, lowercase
    sorted_tags = sorted([tag.lower().strip() for tag in tags])
    # Format: "type:tag1:tag2:tag3"
    return f"{document_type.lower()}:{':'.join(sorted_tags)}"

# Examples:
# "bill:lexus-tx-550"
# "bill:pge:electricity"
# "school:stanford:cs-department"
```

---

## Processing Pipeline

### File Worker (New)

Add a 6th worker to the pipeline:

```python
class FileWorker(BaseWorker):
    """Generate and maintain file summaries."""
    
    source_status = 'completed'  # Documents ready for filing
    
    async def process_document(self, doc: dict):
        """Check if document should be added to files."""
        # 1. Extract type + tags from document
        doc_type = doc['document_type']
        tags = doc.get('tags', [])
        
        # 2. Find or create file(s) for this document
        for tag_combo in get_tag_combinations(tags):
            signature = create_tag_signature(doc_type, tag_combo)
            file_record = await self.find_or_create_file(signature, doc_type, tag_combo)
            
            # 3. Add document to file if not already present
            await self.add_document_to_file(file_record['id'], doc['id'])
            
            # 4. Mark file as outdated
            await self.mark_file_outdated(file_record['id'])
```

### File Generator Worker

Separate worker for generating/updating file summaries:

```python
class FileGeneratorWorker(BaseWorker):
    """Generate summaries for outdated files."""
    
    async def run(self):
        """Poll for files needing generation."""
        while self.running:
            # Get files that need generation
            files = await self.db.get_files_by_status(['pending', 'outdated'])
            
            for file_record in files:
                await self.generate_file_summary(file_record)
            
            await asyncio.sleep(self.poll_interval)
    
    async def generate_file_summary(self, file_record: dict):
        """Generate summary for a file."""
        # 1. Query ALL documents matching file's tags (not just manually added)
        docs = await self.db.get_documents_by_tags(
            document_type=file_record['document_type'],
            tags=file_record['tags'],
            order_by='created_at DESC'  # Reverse chronological
        )
        
        # 2. Build aggregated content text (reverse chronological)
        aggregated_lines = []
        aggregated_lines.append(f"File: {file_record['document_type']} - {', '.join(file_record['tags'])}")
        aggregated_lines.append(f"Total Documents: {len(docs)}")
        aggregated_lines.append("")
        aggregated_lines.append("=" * 80)
        
        for i, doc in enumerate(docs, 1):
            aggregated_lines.append("")
            aggregated_lines.append(f"Document #{i}: {doc['filename']}")
            aggregated_lines.append(f"Date: {doc['created_at']}")
            aggregated_lines.append(f"Type: {doc['document_type']}")
            if doc.get('structured_data'):
                aggregated_lines.append(f"Data: {json.dumps(doc['structured_data'])}")
            if doc.get('summary'):
                aggregated_lines.append(f"Summary: {doc['summary']}")
            aggregated_lines.append("-" * 80)
        
        aggregated_content = "\n".join(aggregated_lines)
        
        # 3. Get active file summarizer prompt
        prompt = await self.db.get_active_prompt('file_summarizer', None)
        
        # 4. Call MCP tool to generate AI summary
        from mcp_server.tools.summarize_file import summarize_file
        result = summarize_file(
            documents=[{
                'created_at': doc['created_at'],
                'filename': doc['filename'],
                'summary': doc.get('summary'),
                'structured_data': doc.get('structured_data'),
                'document_type': doc.get('document_type')
            } for doc in docs],
            file_type=file_record['document_type'],
            tags=file_record['tags'],
            prompt=prompt['prompt_text'],
            bedrock_client=self.bedrock
        )
        
        # 5. Update file record with BOTH aggregated content AND AI summary
        await self.db.update_file(
            file_record['id'],
            aggregated_content=aggregated_content,
            summary_text=result['summary'],
            summary_metadata=result['metadata'],
            status='generated',
            last_generated_at=datetime.utcnow()
        )
```

### File Scorer Worker

Self-improving prompts for file summaries:

```python
class FileScorerWorker(BaseWorker):
    """Score and improve file summarization prompts."""
    
    async def score_file_summary(self, file_record: dict):
        """Evaluate file summary quality."""
        # Get file summary and source documents
        docs = await self.db.get_file_documents(file_record['id'])
        
        # Call MCP scorer tool
        from mcp_server.tools.score_file_summary import score_file_summary
        result = score_file_summary(
            file_summary=file_record['summary_text'],
            documents=docs,
            current_prompt=file_record['prompt_version'],
            bedrock_client=self.bedrock
        )
        
        # If better prompt found, create new version
        if result['score'] > current_score + threshold:
            await self.db.create_prompt(
                prompt_type='file_summarizer',
                prompt_text=result['improved_prompt'],
                performance_score=result['score']
            )
```

---

## Tag Combination Strategy

### Problem
A document with tags `['lexus-tx-550', 'oil-change', 'maintenance']` could belong to multiple files:
- `bill:lexus-tx-550`
- `bill:oil-change`
- `bill:maintenance`
- `bill:lexus-tx-550:oil-change`
- etc.

### Solution: Configurable Strategy

```python
# Config setting
file_tag_strategy: str = "primary_only"  # or "all_combinations"

def get_tag_combinations(tags: list[str], strategy: str = "primary_only"):
    """Get tag combinations for file creation."""
    if strategy == "primary_only":
        # Only create file for first tag
        return [tags[:1]] if tags else [[]]
    
    elif strategy == "all_combinations":
        # Create files for all combinations (expensive!)
        from itertools import combinations
        combos = []
        for i in range(1, len(tags) + 1):
            combos.extend(combinations(tags, i))
        return [list(c) for c in combos]
    
    elif strategy == "single_and_full":
        # Single tags + full tag set
        single = [[tag] for tag in tags]
        full = [tags] if len(tags) > 1 else []
        return single + full
    
    else:
        raise ValueError(f"Unknown strategy: {strategy}")
```

**Recommendation:** Start with `"primary_only"` (first tag only) for simplicity.

---

## MCP Tools

### 1. `summarize_file`

```python
# mcp-server/src/mcp_server/tools/summarize_file.py

async def summarize_file(
    documents: list[dict],
    file_type: str,
    tags: list[str],
    prompt: str,
    bedrock_client
) -> dict:
    """
    Generate summary for a file (collection of documents).
    
    Args:
        documents: List of document entries with summaries
        file_type: Document type (bill, school, etc.)
        tags: Tags defining this file
        prompt: Summarization prompt from DB
        bedrock_client: AWS Bedrock client
    
    Returns:
        {
            'summary': str,  # Generated summary text
            'metadata': dict,  # Structured insights
            'confidence': float
        }
    """
    # Build input text
    context = f"File Type: {file_type}\nTags: {', '.join(tags)}\n\n"
    context += "Documents (chronological order):\n\n"
    
    for i, doc in enumerate(documents, 1):
        context += f"[{i}] {doc['date']} - {doc['filename']}\n"
        context += f"Summary: {json.dumps(doc['summary'])}\n\n"
    
    # Call Bedrock with prompt
    messages = [
        {
            "role": "user",
            "content": [
                {"text": prompt},
                {"text": context}
            ]
        }
    ]
    
    response = bedrock_client.invoke_model(
        model_id="us.amazon.nova-lite-v1:0",
        messages=messages
    )
    
    # Parse response
    result = parse_file_summary_response(response)
    
    return result
```

### 2. `score_file_summary`

```python
# mcp-server/src/mcp_server/tools/score_file_summary.py

async def score_file_summary(
    file_summary: str,
    documents: list[dict],
    current_prompt: dict,
    bedrock_client
) -> dict:
    """
    Score file summary quality and suggest improvements.
    
    Evaluates:
    - Completeness (all documents covered?)
    - Insights (trends, patterns identified?)
    - Accuracy (no hallucinations?)
    - Usefulness (actionable information?)
    
    Returns:
        {
            'score': float,  # 0-1
            'improved_prompt': str,  # Better prompt
            'reasoning': str
        }
    """
    # Implementation similar to score_summarization
    pass
```

---

## API Endpoints

### List Files

```python
@router.get("/api/v1/files")
async def list_files(
    type: str = None,
    tags: list[str] = Query(None),
    status: str = None,
    limit: int = 50,
    offset: int = 0
):
    """List all files with optional filters."""
    return await db.list_files(
        document_type=type,
        tags=tags,
        status=status,
        limit=limit,
        offset=offset
    )
```

### Get File

```python
@router.get("/api/v1/files/{file_id}")
async def get_file(file_id: str):
    """Get file details including summary and documents."""
    file_record = await db.get_file(file_id)
    documents = await db.get_file_documents(file_id)
    
    return {
        "file": file_record,
        "documents": documents
    }
```

### Generate File

```python
@router.post("/api/v1/files/generate")
async def generate_file(
    type: str,
    tags: list[str]
):
    """Manually trigger file generation for type+tags."""
    signature = create_tag_signature(type, tags)
    file_record = await db.find_or_create_file(signature, type, tags)
    
    # Trigger generation
    await db.update_file_status(file_record['id'], 'pending')
    
    return {"file_id": file_record['id'], "status": "queued"}
```

### Regenerate File

```python
@router.post("/api/v1/files/{file_id}/regenerate")
async def regenerate_file(file_id: str):
    """Force regeneration of file summary."""
    await db.update_file_status(file_id, 'outdated')
    return {"status": "queued"}
```

---

## CLI Tools

### View Files

```bash
# List all files
./scripts/view-files

# Filter by type
./scripts/view-files --type bill

# Filter by tags
./scripts/view-files --tags lexus-tx-550

# View specific file
./scripts/view-files <file-id>

# View with full document list
./scripts/view-files <file-id> --documents
```

### Generate File

```bash
# Generate file for type+tags
./scripts/generate-file --type bill --tags lexus-tx-550

# Force regeneration
./scripts/generate-file --id <file-id> --force
```

---

## Implementation Plan

### Phase 1: Database & Core Logic
- [ ] Add `files` and `file_documents` tables to schema
- [ ] Create `AlfrdDatabase` methods for file operations
- [ ] Implement tag signature logic
- [ ] Add tag combination strategy configuration

### Phase 2: File Worker
- [ ] Create `FileWorker` class
- [ ] Implement document-to-file association logic
- [ ] Add file status tracking

### Phase 3: MCP Tools
- [ ] Create `summarize_file` tool
- [ ] Implement file summary prompt template
- [ ] Add to MCP tools registry

### Phase 4: File Generator Worker
- [ ] Create `FileGeneratorWorker` class
- [ ] Implement lazy generation logic
- [ ] Add incremental update support

### Phase 5: Scorer Worker
- [ ] Create `FileScorerWorker` class
- [ ] Implement `score_file_summary` MCP tool
- [ ] Add prompt evolution logic

### Phase 6: API & CLI
- [ ] Add file endpoints to API server
- [ ] Create `view-files` CLI tool
- [ ] Create `generate-file` CLI tool

### Phase 7: Web UI Integration
- [ ] Add Files page to PWA
- [ ] Show file list with filters
- [ ] Display file summaries
- [ ] Link to source documents

---

## Configuration

```python
# shared/config.py additions

class Settings(BaseSettings):
    # ... existing settings ...
    
    # File Worker Configuration
    file_workers: int = 2
    file_poll_interval: int = 10  # seconds
    
    file_generator_workers: int = 2
    file_generator_poll_interval: int = 15
    
    file_scorer_workers: int = 1
    file_scorer_poll_interval: int = 30
    
    # File generation strategy
    file_tag_strategy: str = "primary_only"  # primary_only|single_and_full|all_combinations
    
    # Scoring thresholds
    min_documents_for_file_scoring: int = 3
    file_prompt_update_threshold: float = 0.05
```

---

## Performance Considerations

### Lazy Generation Benefits
- Files created only when accessed (API/CLI request)
- Avoids generating files that are never used
- Once generated, kept up-to-date automatically

### Update Triggers
1. **New Document Added** → Mark relevant files as `outdated`
2. **FileGeneratorWorker** → Regenerate outdated files
3. **Document Edited** → Mark file as `outdated`
4. **Document Deleted** → Remove from file, mark `outdated`

### Caching Strategy
- Generated summaries stored in DB
- No regeneration unless file is `outdated`
- `last_generated_at` timestamp tracks freshness

---

## Example Workflow

### User adds Lexus maintenance bill

```
1. User: ./scripts/add-document lexus-oil-change.jpg --tags bill lexus-tx-550 oil-change

2. Document processed through pipeline:
   pending → ocr_completed → classified → scored_classification → 
   summarized → completed

3. FileWorker (on 'completed' status):
   - Extract: type=bill, tags=['lexus-tx-550', 'oil-change']
   - Create signature: "bill:lexus-tx-550" (primary_only strategy)
   - Find or create file record
   - Add document to file_documents table
   - Mark file status='outdated'

4. FileGeneratorWorker (polls for outdated files):
   - Fetch all documents in file (chronological)
   - Get active file_summarizer prompt
   - Call summarize_file MCP tool
   - Update file record with generated summary
   - Set status='generated'

5. User views file:
   ./scripts/view-files --tags lexus-tx-550
   
   Output:
   File: bill/lexus-tx-550
   Documents: 3
   
   Summary:
   "Lexus TX 550 maintenance history shows regular servicing.
   Total spent: $484.50
   Last service: 2024-11-15 (oil change)
   Next recommended: 2025-02-15"
   
   Documents:
   - 2024-11-15: Oil change at Lexus dealer - $89.50
   - 2024-08-10: Tire rotation - $45.00
   - 2024-05-20: 20k mile service - $350.00
```

---

## Testing Strategy

### Unit Tests
- Tag signature generation
- Tag combination strategies
- File status transitions
- MCP tool responses

### Integration Tests
- Document → File association
- File generation workflow
- Incremental updates
- Prompt evolution

### End-to-End Tests
```python
def test_file_lifecycle():
    # 1. Add 3 related documents
    doc1 = add_document("bill1.jpg", tags=["lexus-tx-550"])
    doc2 = add_document("bill2.jpg", tags=["lexus-tx-550"])
    doc3 = add_document("bill3.jpg", tags=["lexus-tx-550"])
    
    # 2. Wait for processing
    wait_for_status(doc1, 'completed')
    
    # 3. Verify file created
    files = db.list_files(tags=["lexus-tx-550"])
    assert len(files) == 1
    
    # 4. Check file has 3 documents
    file_docs = db.get_file_documents(files[0]['id'])
    assert len(file_docs) == 3
    
    # 5. Verify summary generated
    assert files[0]['status'] == 'generated'
    assert files[0]['summary_text'] is not None
```

---

## Future Enhancements

### Phase 2 Features
- **File Templates**: Predefined formats for common file types
- **Export Formats**: PDF, CSV, Excel reports
- **Scheduled Summaries**: Weekly/monthly auto-generated files
- **File Hierarchies**: Parent-child file relationships

### Phase 3 Features
- **Trend Analysis**: Compare files over time
- **Anomaly Detection**: Flag unusual patterns
- **Predictive Insights**: Forecast future costs/events
- **Cross-File Analysis**: Compare multiple files

---

## Migration Path

### Database Migration

```sql
-- migration.sql
BEGIN;

-- Create files table
CREATE TABLE files ( ... );

-- Create file_documents table
CREATE TABLE file_documents ( ... );

-- Add indexes
CREATE INDEX idx_files_type_tags ON files USING GIN(tags);
CREATE INDEX idx_files_status ON files(status);

-- Add file summarizer prompt
INSERT INTO prompts (prompt_type, document_type, prompt_text, version, is_active)
VALUES (
    'file_summarizer',
    NULL,
    'You are summarizing a collection of related documents...',
    1,
    TRUE
);

COMMIT;
```

### Backward Compatibility
- Existing documents unaffected
- Files generated lazily on demand
- No migration of existing data required
- Can enable/disable file generation via config

---

## Success Metrics

### Quantitative
- Files generated per day
- Average documents per file
- File generation time
- Prompt evolution rate
- API response times

### Qualitative
- Summary accuracy (LLM-scored)
- User feedback on usefulness
- Coverage of document relationships
- Insight quality

---

**Status:** Ready for Phase 1 implementation
**Estimated Timeline:** 2-3 weeks for full feature
**Dependencies:** Existing Phase 1C infrastructure complete ✅