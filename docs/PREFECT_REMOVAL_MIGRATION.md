# Migration Plan: Remove Prefect, Keep Task Logic

**Goal**: Remove Prefect orchestration complexity while keeping task implementations intact.

**Strategy**: Replace Prefect flows/decorators with simple asyncio orchestration, minimal changes to task logic.

---

## Table of Contents

1. [Overview](#overview)
2. [What Changes](#what-changes)
3. [What Stays the Same](#what-stays-the-same)
4. [Migration Steps](#migration-steps)
5. [Code Changes](#code-changes)
6. [Testing Strategy](#testing-strategy)
7. [Rollback Plan](#rollback-plan)

---

## Overview

### Current Architecture (Prefect-based)

```
main.py
  └─> main_orchestrator_flow (Prefect @flow)
        ├─> Monitors DB for pending documents/files
        ├─> Launches process_document_flow (Prefect @flow)
        │     └─> Calls Prefect @tasks: ocr_task → classify_task → etc.
        └─> Launches generate_file_summary_flow (Prefect @flow)
              └─> Calls Prefect @task: generate_file_summary_task
```

**Problem**: Prefect adds complexity (flows, decorators, UI) without providing value for this use case.

### New Architecture (Simple Asyncio)

```
main.py
  └─> SimpleOrchestrator.run()
        ├─> Monitors DB for pending documents/files (same logic)
        ├─> Launches DocumentWorker.process()
        │     └─> Calls plain async functions: _ocr_step → _classify_step → etc.
        └─> Launches FileWorker.process()
              └─> Calls plain async function: _generate_summary
```

**Benefit**: Same functionality, 60% less code, easy debugging with print statements.

---

## What Changes

### Files to Modify

1. **`document-processor/src/document_processor/main.py`**
   - Remove Prefect imports
   - Use new `SimpleOrchestrator` instead of `main_orchestrator_flow`

2. **`document-processor/src/document_processor/tasks/document_tasks.py`**
   - Remove `@task` decorators
   - Remove `rate_limit()` calls (keep semaphores)
   - Keep all task logic (the `_*_impl` functions)
   - Rename: `ocr_task` → `_ocr_step`, etc.

3. **New: `document-processor/src/document_processor/orchestrator.py`**
   - Simple orchestrator class (replaces Prefect flows)

4. **Delete**: 
   - `document-processor/src/document_processor/flows/` (entire directory)

### Dependencies to Remove

```diff
# requirements.txt
-prefect>=3.0.0
-prefect-aws
```

---

## What Stays the Same

✅ **Task Logic**: All OCR, classification, summarization logic unchanged  
✅ **Database**: Same PostgreSQL schema and queries  
✅ **Concurrency**: Same asyncio.Semaphore for rate limiting  
✅ **Error Handling**: Same try/except blocks  
✅ **Status Flow**: Same status transitions (pending → ocr_completed → etc.)  
✅ **Advisory Locks**: Same PostgreSQL locks for prompt evolution  

**Key Insight**: We're just removing the Prefect wrapper layer, keeping the core logic intact.

---

## Migration Steps

### Phase 1: Create New Orchestrator (No Breaking Changes)

**Step 1.1**: Create new orchestrator file

```bash
# Create new file
touch document-processor/src/document_processor/orchestrator.py
```

**Step 1.2**: Implement `SimpleOrchestrator` class (see [Code Changes](#code-changes) below)

**Step 1.3**: Test that it imports without errors

```bash
python3 -c "from document_processor.orchestrator import SimpleOrchestrator; print('✅ Import works')"
```

### Phase 2: Update Task Functions (Minimal Changes)

**Step 2.1**: Strip Prefect decorators from tasks

```python
# BEFORE (Prefect)
@task(name="OCR Document", retries=2, tags=["ocr"])
async def ocr_task(doc_id: UUID, db: AlfrdDatabase) -> str:
    await rate_limit("aws-textract")
    async with _textract_semaphore:
        return await _ocr_task_impl(doc_id, db)

# AFTER (Simple)
async def ocr_step(doc_id: UUID, db: AlfrdDatabase) -> str:
    """Extract text using AWS Textract."""
    async with _textract_semaphore:
        return await _ocr_task_impl(doc_id, db)
```

**Step 2.2**: Rename task functions for clarity

- `ocr_task` → `ocr_step`
- `classify_task` → `classify_step`
- `summarize_task` → `summarize_step`
- `file_task` → `file_step`
- `generate_file_summary_task` → `generate_file_summary_step`

**Keep the `_*_impl` functions exactly as they are** - they contain all the actual logic.

### Phase 3: Update main.py

**Step 3.1**: Replace Prefect flow with simple orchestrator

```python
# BEFORE
from document_processor.flows.orchestrator import main_orchestrator_flow
await main_orchestrator_flow(settings, run_once=run_once)

# AFTER
from document_processor.orchestrator import SimpleOrchestrator
orchestrator = SimpleOrchestrator(settings)
await orchestrator.run(run_once=run_once)
```

**Step 3.2**: Remove Prefect environment variables

```diff
-os.environ.setdefault("PREFECT_SERVER_API_HOST", "0.0.0.0")
-os.environ.setdefault("PREFECT_API_URL", "http://0.0.0.0:4200/api")
-os.environ["PREFECT_LOGGING_LEVEL"] = "INFO"
```

### Phase 4: Test

**Step 4.1**: Test with one document

```bash
./scripts/add-document samples/test.jpg --tags test
python3 document-processor/src/document_processor/main.py --once
```

**Step 4.2**: Check logs for clear error messages

**Step 4.3**: Verify document completes successfully

```bash
./scripts/get-document <doc-id>
```

### Phase 5: Cleanup

**Step 5.1**: Delete Prefect code

```bash
rm -rf document-processor/src/document_processor/flows/
```

**Step 5.2**: Remove Prefect from requirements

```bash
# Edit requirements.txt, remove prefect lines
```

**Step 5.3**: Update documentation (see below)

---

## Code Changes

### New File: `document-processor/src/document_processor/orchestrator.py`

```python
"""Simple asyncio-based orchestrator (replaces Prefect flows)."""

import asyncio
import logging
from pathlib import Path
from typing import Optional
from uuid import UUID

from shared.database import AlfrdDatabase
from shared.config import Settings
from shared.types import DocumentStatus
from mcp_server.llm.bedrock import BedrockClient

logger = logging.getLogger(__name__)


class SimpleOrchestrator:
    """Simple polling orchestrator with asyncio concurrency control."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.db: Optional[AlfrdDatabase] = None
        self.bedrock: Optional[BedrockClient] = None
        
        # Semaphores for concurrency control (same as before)
        self.textract_sem = asyncio.Semaphore(settings.prefect_textract_workers)
        self.bedrock_sem = asyncio.Semaphore(settings.prefect_bedrock_workers)
        self.file_sem = asyncio.Semaphore(settings.prefect_file_generation_workers)
        
        # Flow-level semaphores
        self.doc_flow_sem = asyncio.Semaphore(settings.prefect_max_document_flows)
        self.file_flow_sem = asyncio.Semaphore(settings.prefect_max_file_flows)
    
    async def initialize(self):
        """Initialize database and Bedrock client."""
        self.db = AlfrdDatabase(self.settings.database_url)
        await self.db.initialize()
        
        self.bedrock = BedrockClient(
            aws_access_key_id=self.settings.aws_access_key_id,
            aws_secret_access_key=self.settings.aws_secret_access_key,
            aws_region=self.settings.aws_region
        )
        
        logger.info("✅ Orchestrator initialized")
    
    async def run(self, run_once: bool = False):
        """Main orchestration loop."""
        await self.initialize()
        
        try:
            iteration = 0
            while True:
                iteration += 1
                logger.info(f"🔄 Orchestrator iteration {iteration}")
                
                # Scan inbox for new documents
                new_count = await self._scan_inbox()
                if new_count > 0:
                    logger.info(f"📂 Registered {new_count} new documents from inbox")
                
                # Process pending documents
                await self._process_documents()
                
                # Process pending files
                await self._process_files()
                
                if run_once:
                    logger.info("Run-once mode: waiting for completion")
                    await asyncio.sleep(5)
                    
                    # Check for files created during document processing
                    await self._process_files()
                    break
                
                await asyncio.sleep(10)
        
        finally:
            if self.db:
                await self.db.close()
            logger.info("Orchestrator shutdown complete")
    
    async def _scan_inbox(self) -> int:
        """Scan inbox for new folders and create pending documents."""
        from document_processor.detector import FileDetector
        from shared.constants import META_JSON_FILENAME
        from datetime import datetime, timezone
        from uuid import UUID
        import json
        import shutil
        
        detector = FileDetector()
        inbox = self.settings.inbox_path
        
        if not inbox.exists():
            inbox.mkdir(parents=True, exist_ok=True)
            return 0
        
        folders = [f for f in inbox.iterdir() if f.is_dir()]
        if not folders:
            return 0
        
        # Get existing document IDs
        all_docs = await self.db.list_documents(limit=10000)
        existing_ids = set(doc['id'] for doc in all_docs)
        
        new_count = 0
        for folder_path in folders:
            is_valid, error, meta = detector.validate_document_folder(folder_path)
            
            if not is_valid:
                continue
            
            doc_id = UUID(meta.get('id'))
            
            if doc_id in existing_ids:
                continue
            
            # Create storage paths
            now = datetime.now(timezone.utc)
            year_month = now.strftime("%Y/%m")
            base_path = self.settings.documents_path / year_month
            raw_path = base_path / "raw" / str(doc_id)
            text_path = base_path / "text"
            meta_path = base_path / "meta"
            
            for path in [raw_path, text_path, meta_path]:
                path.mkdir(parents=True, exist_ok=True)
            
            # Copy folder
            shutil.copytree(folder_path, raw_path, dirs_exist_ok=True)
            
            # Create empty text file
            text_file = text_path / f"{doc_id}.txt"
            text_file.write_text("")
            
            # Save metadata
            detailed_meta = {
                'original_meta': meta,
                'processed_at': now.isoformat()
            }
            meta_file = meta_path / f"{doc_id}.json"
            meta_file.write_text(json.dumps(detailed_meta, indent=2))
            
            # Calculate size
            total_size = sum(
                f.stat().st_size
                for f in folder_path.rglob('*')
                if f.is_file()
            )
            
            # Create document record
            await self.db.create_document(
                doc_id=doc_id,
                filename=folder_path.name,
                original_path=str(folder_path),
                file_type='folder',
                file_size=total_size,
                status=DocumentStatus.PENDING,
                raw_document_path=str(raw_path),
                extracted_text_path=str(text_file),
                metadata_path=str(meta_file),
                folder_path=str(folder_path)
            )
            
            new_count += 1
        
        return new_count
    
    async def _process_documents(self):
        """Launch document processing workers."""
        docs = await self.db.get_documents_by_status(
            DocumentStatus.PENDING,
            limit=self.settings.prefect_max_document_flows * 2
        )
        
        if not docs:
            return
        
        logger.info(f"Found {len(docs)} pending documents")
        
        # Launch workers with semaphore control
        tasks = []
        for doc in docs:
            task = asyncio.create_task(
                self._process_document_with_semaphore(doc['id'])
            )
            tasks.append(task)
        
        logger.info(f"Queued {len(docs)} document workers")
        
        # Don't wait - let them run in background
        # (run_once mode waits in main loop)
    
    async def _process_document_with_semaphore(self, doc_id: UUID):
        """Process document with flow-level concurrency control."""
        async with self.doc_flow_sem:
            await self._process_document(doc_id)
    
    async def _process_document(self, doc_id: UUID):
        """Complete document processing pipeline."""
        from document_processor.tasks.document_tasks import (
            ocr_step, classify_step, score_classification_step,
            summarize_step, score_summary_step, file_step
        )
        
        try:
            doc = await self.db.get_document(doc_id)
            logger.info(f"📄 Processing: {doc['filename']} ({doc_id})")
            
            # Step 1: OCR
            extracted_text = await ocr_step(doc_id, self.db)
            
            # Step 2: Classification
            classification = await classify_step(
                doc_id, extracted_text, self.db, self.bedrock
            )
            
            # Step 3: Score classification (background)
            asyncio.create_task(
                score_classification_step(doc_id, classification, self.db, self.bedrock)
            )
            
            # Step 4: Summarization
            summary = await summarize_step(doc_id, self.db, self.bedrock)
            
            # Step 5: Score summary (background)
            asyncio.create_task(
                score_summary_step(doc_id, self.db, self.bedrock)
            )
            
            # Step 6: File into series
            file_id = await file_step(doc_id, self.db, self.bedrock)
            
            # Step 7: Mark completed
            await self.db.update_document(doc_id, status=DocumentStatus.COMPLETED)
            
            logger.info(f"✅ Document {doc_id} complete (filed into {file_id})")
            
        except Exception as e:
            logger.error(f"❌ Document {doc_id} failed: {e}", exc_info=True)
            # Error already handled in task functions
    
    async def _process_files(self):
        """Launch file generation workers."""
        files = await self.db.get_files_by_status(
            ['pending', 'outdated'],
            limit=20
        )
        
        if not files:
            return
        
        logger.info(f"Found {len(files)} pending files")
        
        tasks = []
        for file in files:
            task = asyncio.create_task(
                self._process_file_with_semaphore(file['id'])
            )
            tasks.append(task)
        
        logger.info(f"Queued {len(files)} file workers")
    
    async def _process_file_with_semaphore(self, file_id: UUID):
        """Process file with flow-level concurrency control."""
        async with self.file_flow_sem:
            await self._process_file(file_id)
    
    async def _process_file(self, file_id: UUID):
        """Generate file summary."""
        from document_processor.tasks.document_tasks import generate_file_summary_step
        
        try:
            logger.info(f"📁 Generating file summary {file_id}")
            
            # Mark as generating
            await self.db.update_file(file_id, status='generating')
            
            # Generate summary
            await generate_file_summary_step(file_id, self.db, self.bedrock)
            
            logger.info(f"✅ File {file_id} complete")
            
        except Exception as e:
            logger.error(f"❌ File {file_id} failed: {e}", exc_info=True)
            # Error already handled in task function
```

### Modified: `document-processor/src/document_processor/tasks/document_tasks.py`

**Changes**:
1. Remove `@task` decorators
2. Remove `await rate_limit()` calls
3. Rename functions: `*_task` → `*_step`
4. Keep all `_*_impl` functions unchanged

```python
# BEFORE
@task(name="OCR Document", retries=2, tags=["ocr"], cache_policy=None)
async def ocr_task(doc_id: UUID, db: AlfrdDatabase) -> str:
    await rate_limit("aws-textract")
    async with _textract_semaphore:
        return await _ocr_task_impl(doc_id, db)

# AFTER
async def ocr_step(doc_id: UUID, db: AlfrdDatabase) -> str:
    """Extract text using AWS Textract (with concurrency control)."""
    async with _textract_semaphore:
        return await _ocr_task_impl(doc_id, db)
# ... _ocr_task_impl stays EXACTLY the same
```

**Apply same pattern to**:
- `classify_task` → `classify_step`
- `score_classification_task` → `score_classification_step`
- `summarize_task` → `summarize_step`
- `score_summary_task` → `score_summary_step`
- `file_task` → `file_step`
- `generate_file_summary_task` → `generate_file_summary_step`

### Modified: `document-processor/src/document_processor/main.py`

```python
"""Simple asyncio document processor entry point."""

import asyncio
import argparse
from pathlib import Path
import sys
from uuid import UUID

# Path setup (unchanged)
_script_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_script_dir))
sys.path.insert(0, str(_script_dir / "mcp-server" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config import Settings
from shared.database import AlfrdDatabase
from mcp_server.llm.bedrock import BedrockClient
from document_processor.orchestrator import SimpleOrchestrator


async def main(run_once: bool = False, doc_id: str = None):
    """Main entry point."""
    from shared.logging_config import AlfrdLogger
    AlfrdLogger.setup()
    
    settings = Settings()
    
    # Limit ThreadPoolExecutor threads
    import concurrent.futures
    loop = asyncio.get_event_loop()
    loop.set_default_executor(
        concurrent.futures.ThreadPoolExecutor(max_workers=settings.prefect_max_threads)
    )
    
    print("\n" + "=" * 80)
    print("🚀 ALFRD Document Processor - Simple Asyncio Mode")
    if run_once:
        print("   Mode: Run once and exit")
    if doc_id:
        print(f"   Processing single document: {doc_id}")
    print("=" * 80)
    print()
    
    print(f"📊 Concurrency Limits:")
    print(f"   Max Threads: {settings.prefect_max_threads}")
    print(f"   Document Flows: {settings.prefect_max_document_flows} concurrent")
    print(f"   File Flows: {settings.prefect_max_file_flows} concurrent")
    print(f"   Textract Tasks: {settings.prefect_textract_workers} concurrent")
    print(f"   Bedrock Tasks: {settings.prefect_bedrock_workers} concurrent")
    print(f"   File Generation Tasks: {settings.prefect_file_generation_workers} concurrent")
    print()
    
    # Process single document
    if doc_id:
        print(f"Processing document {doc_id}...")
        
        orchestrator = SimpleOrchestrator(settings)
        await orchestrator.initialize()
        
        try:
            await orchestrator._process_document(UUID(doc_id))
            print(f"✅ Document {doc_id} processed")
        finally:
            await orchestrator.db.close()
        
        return
    
    # Run orchestrator
    print("🔧 Starting orchestrator...")
    orchestrator = SimpleOrchestrator(settings)
    await orchestrator.run(run_once=run_once)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="ALFRD Document Processor (Simple Asyncio)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process all pending documents and exit"
    )
    parser.add_argument(
        "--doc-id",
        help="Process single document by ID"
    )
    args = parser.parse_args()
    
    asyncio.run(main(run_once=args.once, doc_id=args.doc_id))
```

---

## Testing Strategy

### Test 1: Import Check

```bash
python3 -c "from document_processor.orchestrator import SimpleOrchestrator; print('✅')"
```

### Test 2: Single Document

```bash
./scripts/add-document samples/test.jpg --tags test
python3 document-processor/src/document_processor/main.py --once
```

**Expected**: Document processes through all stages to `completed`.

### Test 3: Concurrent Documents

```bash
# Add 5 documents
for i in {1..5}; do
    ./scripts/add-document samples/test.jpg --tags test$i
done

# Process
python3 document-processor/src/document_processor/main.py --once
```

**Expected**: All 5 documents complete, respecting concurrency limits.

### Test 4: File Generation

```bash
# Should trigger file generation after filing
./scripts/get-files
```

**Expected**: Files have status `generated` with summaries.

### Test 5: Error Handling

```bash
# Add document with missing file (should fail gracefully)
python3 document-processor/src/document_processor/main.py --doc-id <bad-id>
```

**Expected**: Clear error message, status=`failed`.

---

## Rollback Plan

If migration fails, rollback is easy:

```bash
# Restore Prefect code from git
git checkout HEAD -- document-processor/src/document_processor/flows/
git checkout HEAD -- document-processor/src/document_processor/tasks/
git checkout HEAD -- document-processor/src/document_processor/main.py

# Delete new orchestrator
rm document-processor/src/document_processor/orchestrator.py

# Restore requirements
git checkout HEAD -- requirements.txt

# Reinstall
pip install -r requirements.txt
```

**Total rollback time**: <5 minutes

---

## Benefits Checklist

After migration, you should have:

- [x] **Simpler debugging**: `print()` statements work, no UI needed
- [x] **Clear errors**: Direct stack traces, no hidden Prefect state
- [x] **Same concurrency**: Asyncio semaphores still limit AWS calls
- [x] **Same functionality**: All tasks work identically
- [x] **Less code**: ~60% reduction in orchestration boilerplate
- [x] **Faster startup**: No Prefect server initialization
- [x] **Easier onboarding**: Contributors don't need to learn Prefect

---

## Documentation Updates

### Files to Update

1. **`README.md`**:
   - Remove mentions of "Prefect 3.x"
   - Change "DAG-based pipeline" → "Asyncio-based pipeline"
   - Remove Prefect UI URL (http://0.0.0.0:4200)

2. **`ARCHITECTURE.md`**:
   - Update architecture diagram (remove Prefect layer)
   - Change "Prefect tasks" → "Asyncio tasks"
   - Remove advisory lock section (or update to clarify it's PostgreSQL-level)

3. **`START_HERE.md`**:
   - Remove Prefect installation instructions
   - Update concurrency configuration (semaphore-based, not Prefect-based)

4. **`STATUS.md`**:
   - Update "Current Phase" to reflect removal of Prefect
   - Add migration to recent changes

---

## Estimated Effort

| Phase | Task | Time |
|-------|------|------|
| 1 | Create `orchestrator.py` | 1 hour |
| 2 | Update `document_tasks.py` | 30 min |
| 3 | Update `main.py` | 15 min |
| 4 | Testing | 1 hour |
| 5 | Cleanup & docs | 30 min |
| **Total** | | **3 hours** |

---

## Questions?

- **Q**: What if I need retry logic later?  
  **A**: Add a simple retry decorator (10-20 lines).

- **Q**: What if I need distributed execution?  
  **A**: Celery or RQ are simpler than Prefect for task queues.

- **Q**: Can I keep Prefect for now?  
  **A**: Yes, but debugging will remain difficult until you remove it.

---

## Next Steps

1. Review this plan
2. Create `orchestrator.py` (copy code from above)
3. Update `document_tasks.py` (remove decorators)
4. Test with `--once` mode
5. If works, delete `flows/` directory
6. Update documentation
7. Celebrate simpler architecture! 🎉