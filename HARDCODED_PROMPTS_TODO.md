# Hardcoded Prompts Migration TODO

## Overview
Currently, 4 prompts are hardcoded in MCP tool files. These should be migrated to the database to enable the self-improving prompt evolution architecture.

## Status
- ✅ **Series Detector** - Added to database in schema.sql
- ❌ **Classifier** - Still hardcoded
- ❌ **Bill Summarizer** - Still hardcoded  
- ❌ **File Summarizer** - Still hardcoded

## Hardcoded Prompts to Migrate

### 1. Classification Prompt
**File**: `mcp-server/src/mcp_server/tools/classify_document.py:13`
**Current**: Hardcoded constant `CLASSIFICATION_SYSTEM_PROMPT`
**Target**: `prompts` table with `prompt_type='classifier'`, `document_type=NULL`

**Migration Steps**:
1. Add INSERT statement to schema.sql for classifier prompt
2. Update `classify_document()` to fetch from database instead of using constant
3. Add caching/memoization for performance
4. Keep hardcoded constant as fallback

### 2. Bill Summary Prompt
**File**: `mcp-server/src/mcp_server/tools/summarize_bill.py:32`
**Current**: Hardcoded constant `BILL_SUMMARY_SYSTEM_PROMPT`
**Target**: `prompts` table with `prompt_type='summarizer'`, `document_type='bill'`

**Migration Steps**:
1. Add INSERT statement to schema.sql for bill summarizer prompt
2. Update `summarize_bill()` to fetch from database
3. Add caching/memoization for performance
4. Keep hardcoded constant as fallback

### 3. File Summary Scoring Prompt
**File**: `mcp-server/src/mcp_server/tools/summarize_file.py:172`
**Current**: Hardcoded inline prompt in `score_file_summary()`
**Status**: **KEEP HARDCODED** - This is a meta-prompt for evaluating other prompts, not a user-facing prompt that should evolve

**Rationale**: Scoring prompts are infrastructure, not content. They evaluate OTHER prompts, so they should remain stable and hardcoded.

### 4. File Summary Prompt (Deprecated)
**File**: `mcp-server/src/mcp_server/tools/summarize_file.py:86`
**Current**: Hardcoded inline system prompt
**Status**: **ALREADY MIGRATED** - Uses database prompt fetched via `prompt` parameter

**Note**: The `summarize_file()` function already receives a `prompt` parameter from the database. The hardcoded system message on line 86 is just a generic wrapper, not the actual prompt content.

## Final Count

**Prompts to migrate**: 2 (Classifier + Bill Summarizer)  
**Already migrated**: 2 (Series Detector + File Summarizer)  
**Keep hardcoded**: 1 (Scoring meta-prompts)

## Implementation Plan

### Phase 1: Database Schema (✅ DONE)
- [x] Add `series_detector` to prompt_type constraint
- [x] Insert default series_detector prompt

### Phase 2: Add Default Prompts
- [ ] Add classifier prompt INSERT to schema.sql
- [ ] Add bill summarizer prompt INSERT to schema.sql

### Phase 3: Update MCP Tools
- [ ] Update `classify_document.py` to fetch prompt from DB
- [ ] Update `summarize_bill.py` to fetch prompt from DB
- [ ] Add fallback logic for missing prompts
- [ ] Add caching layer for performance

### Phase 4: Testing
- [ ] Test prompt loading from database
- [ ] Test fallback to hardcoded prompts
- [ ] Test prompt evolution workflow
- [ ] Verify performance with caching

## Benefits of Migration

1. **Self-Improving**: Prompts can evolve based on performance scoring
2. **Version Control**: Track prompt changes in database
3. **A/B Testing**: Can compare different prompt versions
4. **Centralized Management**: All prompts in one place
5. **Runtime Updates**: Change prompts without code deployment

## Notes

- Keep hardcoded constants as fallbacks for safety
- Add caching to avoid database hits on every LLM call
- Document the migration in PROGRESS.md when complete
- Consider adding a prompt management UI later