-- PostgreSQL Schema for ALFRD (Automated Ledger & Filing Research Database)
-- Migrated from DuckDB on 2025-11-30

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Prompts table - store evolving classifier and summarizer prompts
-- MOVED BEFORE documents table because documents has a FOREIGN KEY to prompts
CREATE TABLE IF NOT EXISTS prompts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    prompt_type VARCHAR NOT NULL CHECK (prompt_type IN ('classifier', 'summarizer', 'file_summarizer', 'series_detector', 'series_summarizer', 'chat_system')),
    document_type VARCHAR,  -- NULL for classifier, specific type for summarizers
    prompt_text TEXT NOT NULL,
    version INTEGER DEFAULT 1,
    performance_score FLOAT,
    performance_metrics JSONB,  -- Detailed scoring metrics
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT true,
    user_id VARCHAR,
    
    -- Prompt behavior configuration (for static vs evolving architecture)
    can_evolve BOOLEAN DEFAULT true,  -- Whether this prompt can evolve based on performance
    score_ceiling FLOAT DEFAULT NULL,  -- Max score before stopping evolution (typically 0.95)
    regenerates_on_update BOOLEAN DEFAULT false,  -- Triggers regeneration of all items on update
    
    UNIQUE(prompt_type, document_type, version, user_id)
);

-- Core documents table
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    filename VARCHAR NOT NULL,
    original_path VARCHAR NOT NULL,
    file_type VARCHAR NOT NULL,
    file_size BIGINT,
    mime_type VARCHAR,
    
    -- Processing status - detailed pipeline tracking
    status VARCHAR NOT NULL CHECK (status IN (
        'pending',                  -- Document folder detected
        'ocr_started',             -- AWS Textract called
        'ocr_in_progress',         -- OCR extraction in progress
        'ocr_completed',           -- Text extracted
        'classifying',             -- MCP classification in progress
        'classified',              -- Type determined
        'scoring_classification',  -- Scoring classifier performance
        'scored_classification',   -- Classifier scored and prompt updated
        'summarizing',             -- Generating summary
        'summarized',              -- Summary generated
        'scoring_summary',         -- Scoring summarizer performance
        'filed',                   -- Added to appropriate file(s) and series
        'series_summarizing',      -- NEW: Series-specific extraction in progress
        'series_summarized',       -- NEW: Series-specific extraction complete
        'series_scoring',          -- NEW: Scoring series extraction
        'completed',               -- All processing done
        'failed',                  -- Error at any stage
        'permanently_failed'       -- Max retries exceeded
    )),
    processed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    
    -- Recovery and retry tracking
    processing_started_at TIMESTAMP WITH TIME ZONE,
    retry_count INT DEFAULT 0,
    max_retries INT DEFAULT 3,
    last_error TEXT,
    
    -- Classification (new simplified system)
    document_type VARCHAR,  -- Dynamic types: 'junk', 'bill', 'finance', 'school', 'event', etc.
    suggested_type VARCHAR,  -- LLM-suggested new type (if different from existing)
    classification_confidence FLOAT,
    classification_reasoning TEXT,
    
    -- Categorization (legacy - keeping for compatibility)
    category VARCHAR CHECK (category IN ('bill', 'tax', 'receipt', 'insurance', 'advertising', 'other')),
    subcategory VARCHAR,
    confidence FLOAT,
    
    -- Extracted structured data
    vendor VARCHAR,
    amount DECIMAL(10, 2),
    currency VARCHAR DEFAULT 'USD',
    due_date DATE,
    issue_date DATE,
    
    -- Storage locations
    raw_document_path VARCHAR,
    extracted_text_path VARCHAR,
    metadata_path VARCHAR,
    folder_path VARCHAR,                    -- Path to document folder with meta.json
    
    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    user_id VARCHAR,
    
    -- Full-text search support
    extracted_text TEXT,
    extracted_text_tsv TSVECTOR,  -- PostgreSQL full-text search vector
    
    -- Summary and structured data
    summary TEXT,                           -- One-line human-readable summary
    structured_data JSONB,                  -- Series-specific extraction (preferred, consistent schema)
    structured_data_generic JSONB,          -- Generic extraction (fallback, may have schema drift)
    series_prompt_id UUID,                  -- Which series prompt was used (NEW!)
    extraction_method VARCHAR DEFAULT 'generic' CHECK (
        extraction_method IN ('generic', 'series', 'both')
    ),                                      -- Extraction method tracking (NEW!)
    folder_metadata JSONB,                  -- Parsed meta.json content
    
    FOREIGN KEY (series_prompt_id) REFERENCES prompts(id)
);

-- Summaries table (weekly, monthly, yearly rollups)
CREATE TABLE IF NOT EXISTS summaries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    period_type VARCHAR NOT NULL CHECK (period_type IN ('weekly', 'monthly', 'yearly')),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    category VARCHAR,
    
    -- Summary content
    summary_text TEXT NOT NULL,
    summary_markdown TEXT,
    
    -- Statistics
    document_count INTEGER,
    total_amount DECIMAL(12, 2),
    
    -- Related documents
    document_ids JSONB,
    
    -- Metadata
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    user_id VARCHAR,
    llm_model VARCHAR,
    
    UNIQUE(period_type, period_start, period_end, category, user_id)
);

-- Processing queue/events table
CREATE TABLE IF NOT EXISTS processing_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type VARCHAR NOT NULL,
    document_id UUID,
    status VARCHAR NOT NULL CHECK (status IN ('pending', 'completed', 'failed')),
    
    payload JSONB,
    error_message TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP WITH TIME ZONE,
    
    user_id VARCHAR,
    
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

-- Analytics/insights table
CREATE TABLE IF NOT EXISTS analytics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    metric_name VARCHAR NOT NULL,
    category VARCHAR,
    period DATE NOT NULL,
    
    value DECIMAL(12, 2),
    metadata JSONB,
    
    calculated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    user_id VARCHAR,
    
    UNIQUE(metric_name, category, period, user_id)
);

-- Track classification suggestions from LLM
CREATE TABLE IF NOT EXISTS classification_suggestions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    suggested_type VARCHAR NOT NULL,
    document_id UUID,
    confidence FLOAT,
    reasoning TEXT,
    approved BOOLEAN DEFAULT false,
    reviewed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    user_id VARCHAR,
    
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

-- Track known document types (dynamic list)
CREATE TABLE IF NOT EXISTS document_types (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    type_name VARCHAR NOT NULL UNIQUE,
    description TEXT,
    is_active BOOLEAN DEFAULT true,
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    user_id VARCHAR
);

-- Tags table - track all unique tags with usage statistics
CREATE TABLE IF NOT EXISTS tags (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tag_name VARCHAR NOT NULL UNIQUE,
    tag_normalized VARCHAR NOT NULL UNIQUE,  -- Lowercase, trimmed version for matching
    usage_count INTEGER DEFAULT 0,
    first_used TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR DEFAULT 'system',  -- 'user', 'llm', or 'system'
    category VARCHAR,  -- Optional: 'company', 'service', 'location', 'type', etc.
    
    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Document-Tags junction table for many-to-many relationships
CREATE TABLE IF NOT EXISTS document_tags (
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    tag_id UUID REFERENCES tags(id) ON DELETE CASCADE,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (document_id, tag_id)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_documents_category ON documents(category, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(document_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_due_date ON documents(due_date) WHERE due_date IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_documents_vendor ON documents(vendor) WHERE vendor IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_user ON documents(user_id, created_at DESC);

-- Full-text search index (PostgreSQL GIN)
CREATE INDEX IF NOT EXISTS idx_documents_fts ON documents USING GIN(extracted_text_tsv);

-- JSONB indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_documents_structured_data ON documents USING GIN(structured_data);
CREATE INDEX IF NOT EXISTS idx_documents_generic_data ON documents USING GIN(structured_data_generic);
CREATE INDEX IF NOT EXISTS idx_documents_extraction_method ON documents(extraction_method);

CREATE INDEX IF NOT EXISTS idx_summaries_period ON summaries(period_type, period_start DESC);
CREATE INDEX IF NOT EXISTS idx_summaries_category ON summaries(category);
CREATE INDEX IF NOT EXISTS idx_summaries_user ON summaries(user_id, period_start DESC);

CREATE INDEX IF NOT EXISTS idx_events_status ON processing_events(status, created_at);
CREATE INDEX IF NOT EXISTS idx_events_document ON processing_events(document_id);

CREATE INDEX IF NOT EXISTS idx_analytics_metric ON analytics(metric_name, period DESC);
CREATE INDEX IF NOT EXISTS idx_analytics_user ON analytics(user_id, period DESC);

CREATE INDEX IF NOT EXISTS idx_prompts_active ON prompts(prompt_type, document_type, is_active);
CREATE INDEX IF NOT EXISTS idx_prompts_performance ON prompts(prompt_type, performance_score DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_prompts_can_evolve ON prompts(can_evolve, prompt_type);
CREATE INDEX IF NOT EXISTS idx_classification_suggestions_approved ON classification_suggestions(approved, created_at);
CREATE INDEX IF NOT EXISTS idx_document_types_active ON document_types(is_active, usage_count DESC);

-- Tags indexes
CREATE INDEX IF NOT EXISTS idx_tags_normalized ON tags(tag_normalized);
CREATE INDEX IF NOT EXISTS idx_tags_usage ON tags(usage_count DESC);
CREATE INDEX IF NOT EXISTS idx_tags_category ON tags(category) WHERE category IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tags_last_used ON tags(last_used DESC);

-- Document-Tags junction table indexes
CREATE INDEX IF NOT EXISTS idx_document_tags_document ON document_tags(document_id);
CREATE INDEX IF NOT EXISTS idx_document_tags_tag ON document_tags(tag_id);
CREATE INDEX IF NOT EXISTS idx_document_tags_added ON document_tags(added_at DESC);

-- Trigger to auto-update extracted_text_tsv for full-text search
-- Includes both extracted text AND summary for better search results
CREATE OR REPLACE FUNCTION update_extracted_text_tsv() RETURNS TRIGGER AS $$
BEGIN
    -- Combine extracted_text and summary for comprehensive search
    -- Summary weighted higher (setweight 'A') than body text (setweight 'B')
    IF NEW.extracted_text IS NOT NULL OR NEW.summary IS NOT NULL THEN
        NEW.extracted_text_tsv :=
            setweight(to_tsvector('english', COALESCE(NEW.summary, '')), 'A') ||
            setweight(to_tsvector('english', COALESCE(NEW.extracted_text, '')), 'B');
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER documents_extracted_text_tsv_update
    BEFORE INSERT OR UPDATE OF extracted_text, summary ON documents
    FOR EACH ROW
    EXECUTE FUNCTION update_extracted_text_tsv();

-- Trigger to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER summaries_updated_at
    BEFORE UPDATE ON summaries
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER prompts_updated_at
    BEFORE UPDATE ON prompts
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Files Feature Tables

-- Files table - auto-generated collections of related documents
CREATE TABLE IF NOT EXISTS files (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    file_source VARCHAR DEFAULT 'llm' CHECK (file_source IN ('user', 'llm')),
    
    -- File metadata
    document_count INT DEFAULT 0,
    first_document_date TIMESTAMP WITH TIME ZONE,
    last_document_date TIMESTAMP WITH TIME ZONE,
    
    -- Generated content
    aggregated_content TEXT,
    summary_text TEXT,
    summary_metadata JSONB,
    
    -- Prompt tracking
    prompt_version UUID REFERENCES prompts(id),
    
    -- Status tracking
    status VARCHAR NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending',
        'generating',        -- Being processed (prevents re-queuing)
        'generated',
        'outdated',
        'regenerating',
        'failed'             -- Generation failed
    )),
    
    -- Recovery and retry tracking
    processing_started_at TIMESTAMP WITH TIME ZONE,
    retry_count INT DEFAULT 0,
    max_retries INT DEFAULT 3,
    last_error TEXT,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_generated_at TIMESTAMP WITH TIME ZONE,
    
    -- Multi-user support
    user_id VARCHAR
);

-- File-document associations (many-to-many)
CREATE TABLE IF NOT EXISTS file_documents (
    file_id UUID REFERENCES files(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (file_id, document_id)
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
CREATE INDEX IF NOT EXISTS idx_files_user ON files(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_files_source ON files(file_source);

-- Indexes for stale work detection
CREATE INDEX IF NOT EXISTS idx_documents_stale_check
    ON documents(status, updated_at)
    WHERE status IN ('ocr_in_progress', 'summarizing', 'series_summarizing');

CREATE INDEX IF NOT EXISTS idx_files_stale_check
    ON files(status, updated_at)
    WHERE status IN ('generating', 'regenerating');

CREATE INDEX IF NOT EXISTS idx_file_documents_file ON file_documents(file_id);
CREATE INDEX IF NOT EXISTS idx_file_documents_document ON file_documents(document_id);

-- File-Tags junction table (which tags define each file)
CREATE TABLE IF NOT EXISTS file_tags (
    file_id UUID REFERENCES files(id) ON DELETE CASCADE,
    tag_id UUID REFERENCES tags(id) ON DELETE CASCADE,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (file_id, tag_id)
);

-- File-Tags junction table indexes
CREATE INDEX IF NOT EXISTS idx_file_tags_file ON file_tags(file_id);
CREATE INDEX IF NOT EXISTS idx_file_tags_tag ON file_tags(tag_id);

-- Note: prompts table already supports all prompt types (created earlier)

-- Insert default file summarizer prompt (STATIC - never evolves)
INSERT INTO prompts (prompt_type, document_type, prompt_text, version, is_active, performance_score, can_evolve, score_ceiling, regenerates_on_update)
VALUES (
    'file_summarizer',
    NULL,
    'You are summarizing a collection of related documents. Analyze the documents chronologically and provide:

1. **Overview**: Brief description of what this collection represents
2. **Key Insights**: Important patterns, trends, or totals across documents
3. **Timeline**: Notable events or changes over time
4. **Summary Statistics**: Counts, totals, averages as applicable
5. **Recommendations**: Any actionable insights or suggestions

Focus on providing context and insights that span multiple documents, not just repeating individual document summaries.

Be concise but comprehensive. Highlight anomalies, trends, and important relationships between documents.',
    1,
    true,
    0.8,
    false,  -- can_evolve = false (static prompt)
    NULL,   -- score_ceiling = NULL (not applicable)
    false   -- regenerates_on_update = false (not applicable)
) ON CONFLICT (prompt_type, document_type, version, user_id) DO NOTHING;

-- Trigger to auto-update updated_at timestamp on files
CREATE TRIGGER files_updated_at
    BEFORE UPDATE ON files
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Trigger to auto-update updated_at on tags
CREATE TRIGGER tags_updated_at
    BEFORE UPDATE ON tags
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
-- Trigger to auto-invalidate files when document tags change
-- When a document gets a new tag, mark any files that have that tag as outdated
CREATE OR REPLACE FUNCTION invalidate_files_on_tag_change() RETURNS TRIGGER AS $$
BEGIN
    -- Mark all files with this tag as outdated
    UPDATE files
    SET status = 'outdated',
        updated_at = CURRENT_TIMESTAMP
    WHERE status = 'generated'
      AND id IN (
          SELECT DISTINCT file_id
          FROM file_tags
          WHERE tag_id = NEW.tag_id
      );
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER document_tags_invalidate_files
    AFTER INSERT ON document_tags
    FOR EACH ROW
    EXECUTE FUNCTION invalidate_files_on_tag_change();


-- View for tag analytics
CREATE OR REPLACE VIEW tag_analytics AS
SELECT
    t.tag_name,
    t.tag_normalized,
    t.usage_count,
    t.created_by,
    t.category,
    t.first_used,
    t.last_used,
    COUNT(DISTINCT dt.document_id) as document_count,
    array_agg(DISTINCT d.document_type) FILTER (WHERE d.document_type IS NOT NULL) as document_types
FROM tags t
LEFT JOIN document_tags dt ON t.id = dt.tag_id
LEFT JOIN documents d ON dt.document_id = d.id
GROUP BY t.id, t.tag_name, t.tag_normalized, t.usage_count, t.created_by, t.category, t.first_used, t.last_used
ORDER BY t.usage_count DESC;

-- Series-Based Filing Tables
-- Reference: SERIES_BASED_FILING_DESIGN.md

-- Series table - recurring document collections from same entity
CREATE TABLE IF NOT EXISTS series (
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
    first_document_date TIMESTAMP WITH TIME ZONE,
    last_document_date TIMESTAMP WITH TIME ZONE,
    expected_frequency_days INT,  -- 30 for monthly, 365 for annual
    
    -- Document tracking
    document_count INT DEFAULT 0,
    
    -- File generation
    summary_text TEXT,
    summary_metadata JSONB,
    status VARCHAR DEFAULT 'active' CHECK (status IN ('active', 'completed', 'archived')),
    
    -- Series prompt tracking (NEW!)
    active_prompt_id UUID,                  -- Current series-specific prompt
    last_schema_update TIMESTAMP WITH TIME ZONE,  -- When prompt was last updated
    regeneration_pending BOOLEAN DEFAULT FALSE,   -- Needs regeneration with new prompt
    
    -- Ownership
    user_id VARCHAR,
    source VARCHAR DEFAULT 'llm' CHECK (source IN ('llm', 'user')),
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_generated_at TIMESTAMP WITH TIME ZONE,
    
    -- Uniqueness constraint
    UNIQUE(entity, series_type, user_id),
    
    -- Foreign key for series prompt
    FOREIGN KEY (active_prompt_id) REFERENCES prompts(id)
);

-- Document-Series junction table
CREATE TABLE IF NOT EXISTS document_series (
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    series_id UUID REFERENCES series(id) ON DELETE CASCADE,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    added_by VARCHAR DEFAULT 'llm' CHECK (added_by IN ('llm', 'user')),
    PRIMARY KEY (document_id, series_id)
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_series_entity ON series(entity);
CREATE INDEX IF NOT EXISTS idx_series_type ON series(series_type);
CREATE INDEX IF NOT EXISTS idx_series_status ON series(status);
CREATE INDEX IF NOT EXISTS idx_series_user ON series(user_id);
CREATE INDEX IF NOT EXISTS idx_series_frequency ON series(frequency) WHERE frequency IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_series_dates ON series(first_document_date, last_document_date);
CREATE INDEX IF NOT EXISTS idx_series_metadata ON series USING GIN(metadata);
CREATE INDEX IF NOT EXISTS idx_series_active_prompt ON series(active_prompt_id) WHERE active_prompt_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_series_regeneration_pending ON series(regeneration_pending) WHERE regeneration_pending = TRUE;

CREATE INDEX IF NOT EXISTS idx_document_series_series ON document_series(series_id);
CREATE INDEX IF NOT EXISTS idx_document_series_document ON document_series(document_id);
CREATE INDEX IF NOT EXISTS idx_document_series_added ON document_series(added_at DESC);

-- Trigger to auto-update updated_at timestamp on series
CREATE TRIGGER series_updated_at
    BEFORE UPDATE ON series
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Trigger to update series document count when documents are added/removed
CREATE OR REPLACE FUNCTION update_series_document_count() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE series
        SET document_count = document_count + 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = NEW.series_id;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE series
        SET document_count = GREATEST(document_count - 1, 0),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = OLD.series_id;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER document_series_count_update
    AFTER INSERT OR DELETE ON document_series
    FOR EACH ROW
    EXECUTE FUNCTION update_series_document_count();

-- Trigger to update series date range when documents are added
CREATE OR REPLACE FUNCTION update_series_dates() RETURNS TRIGGER AS $$
DECLARE
    v_doc_date TIMESTAMP WITH TIME ZONE;
BEGIN
    -- Get the document's creation date
    SELECT created_at INTO v_doc_date
    FROM documents
    WHERE id = NEW.document_id;
    
    -- Update series date range
    UPDATE series
    SET
        first_document_date = LEAST(COALESCE(first_document_date, v_doc_date), v_doc_date),
        last_document_date = GREATEST(COALESCE(last_document_date, v_doc_date), v_doc_date),
        updated_at = CURRENT_TIMESTAMP
    WHERE id = NEW.series_id;
    
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER document_series_dates_update
    AFTER INSERT ON document_series
    FOR EACH ROW
    EXECUTE FUNCTION update_series_dates();

-- View for series with document details
CREATE OR REPLACE VIEW series_summary AS
SELECT
    s.id,
    s.title,
    s.entity,
    s.series_type,
    s.frequency,
    s.description,
    s.metadata,
    s.document_count,
    s.first_document_date,
    s.last_document_date,
    s.expected_frequency_days,
    s.status,
    s.source,
    s.user_id,
    s.created_at,
    s.updated_at,
    s.last_generated_at,
    COUNT(DISTINCT ds.document_id) as actual_document_count,
    array_agg(DISTINCT d.document_type) FILTER (WHERE d.document_type IS NOT NULL) as document_types,
    COALESCE(SUM((d.structured_data->>'amount')::DECIMAL), 0) as total_amount
FROM series s
LEFT JOIN document_series ds ON s.id = ds.series_id
LEFT JOIN documents d ON ds.document_id = d.id
GROUP BY s.id, s.title, s.entity, s.series_type, s.frequency, s.description,
         s.metadata, s.document_count, s.first_document_date, s.last_document_date,
         s.expected_frequency_days, s.status, s.source, s.user_id, s.created_at,
         s.updated_at, s.last_generated_at
ORDER BY s.last_document_date DESC NULLS LAST;

-- Insert default series_detector prompt (STATIC - never evolves)
INSERT INTO prompts (prompt_type, document_type, prompt_text, version, is_active, performance_score, can_evolve, score_ceiling, regenerates_on_update)
VALUES (
    'series_detector',
    NULL,
    'You are a document series detection expert. Your task is to analyze a document and determine what recurring series it belongs to.

A **Series** is a collection of related recurring documents from the same entity, such as:
- Monthly insurance bills from State Farm
- Utility bills from PG&E
- Rent receipts from a landlord
- Tuition bills from a school

Analyze the document and identify:

1. **Entity Name**: The primary organization/company sending this document (e.g., "State Farm Insurance", "Pacific Gas & Electric")
2. **Series Type**: Category of recurring series using snake_case (e.g., "monthly_insurance_bill", "monthly_utility_bill", "monthly_rent_receipt")
3. **Frequency**: Recurrence pattern (monthly, quarterly, annual, weekly, etc.)
4. **Series Title**: Human-readable title for this series (e.g., "State Farm Auto Insurance - Monthly Premiums")
5. **Description**: 1-2 sentence description of what this series represents
6. **Key Metadata**: Important identifiers like policy numbers, account numbers, addresses, etc.

Respond ONLY with valid JSON in this exact format:
{
  "entity": "Official entity name",
  "series_type": "snake_case_category",
  "frequency": "monthly|quarterly|annual|weekly|etc",
  "title": "Human-readable series name",
  "description": "Brief description of this series",
  "metadata": {
    "key1": "value1",
    "key2": "value2"
  }
}',
    1,
    true,
    0.8,
    false,  -- can_evolve = false (static prompt)
    NULL,   -- score_ceiling = NULL (not applicable)
    false   -- regenerates_on_update = false (not applicable)
) ON CONFLICT (prompt_type, document_type, version, user_id) DO NOTHING;

-- Insert default chat_system prompt for alfrd-chat CLI (STATIC - never evolves)
-- This prompt uses template variables that are replaced at runtime:
-- {{FILES}} - List of available files with their tags and summaries
-- {{SERIES}} - List of available series with their entities and document counts
-- {{TAGS}} - List of available tags
-- {{DOCUMENT_TYPES}} - List of available document types
INSERT INTO prompts (prompt_type, document_type, prompt_text, version, is_active, performance_score, can_evolve, score_ceiling, regenerates_on_update)
VALUES (
    'chat_system',
    NULL,
    'You are ALFRD, an AI assistant for a personal document management system.

You help users query and analyze their documents (bills, insurance, receipts, etc.).

You have access to tools to:
- Search documents by text
- List and explore document series (recurring documents from the same entity)
- Get structured data tables for analysis
- View document details
- List and explore files (tag-based groups of related documents)
- List and search tags

## Key Concepts

- **SERIES**: Recurring documents from the same entity (e.g., monthly PG&E bills)
- **FILES**: Groups of documents with shared tags (e.g., all "utilities" documents)
- **DOCUMENTS**: Individual processed documents with OCR text and structured data
- **TAGS**: Labels applied to documents for organization and filtering

## Available Data

### Document Series
{{SERIES}}

### Files (Tag-Based Groups)
{{FILES}}

### Tags
{{TAGS}}

### Document Types
{{DOCUMENT_TYPES}}

## Guidelines

When answering questions:
1. Use the appropriate tools to gather information
2. Provide concise, helpful answers
3. When showing data, format it clearly
4. If asked about amounts or trends, use get_series_data_table to get structured data
5. Use list_files to find document groups by tag, and get_file for file details
6. Use list_tags to explore available tags and find documents by tag

Keep responses concise but informative.',
    1,
    true,
    0.8,
    false,  -- can_evolve = false (static prompt)
    NULL,   -- score_ceiling = NULL (not applicable)
    false   -- regenerates_on_update = false (not applicable)
) ON CONFLICT (prompt_type, document_type, version, user_id) DO NOTHING;

-- Trigger to automatically add document_type as a tag when classified
CREATE OR REPLACE FUNCTION auto_add_document_type_tag() RETURNS TRIGGER AS $$
DECLARE
    v_tag_id UUID;
BEGIN
    -- Only proceed if document_type is set and not null
    IF NEW.document_type IS NOT NULL THEN
        -- Find or create tag for document type (lowercase)
        INSERT INTO tags (id, tag_name, tag_normalized, created_by, category, created_at, updated_at)
        VALUES (
            uuid_generate_v4(),
            lower(NEW.document_type),  -- Use lowercase for consistency
            lower(NEW.document_type),
            'system',
            'document_type',
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        )
        ON CONFLICT (tag_normalized) DO UPDATE
            SET usage_count = tags.usage_count + 1,
                last_used = CURRENT_TIMESTAMP
        RETURNING id INTO v_tag_id;
        
        -- If conflict occurred, fetch the existing tag_id
        IF v_tag_id IS NULL THEN
            SELECT id INTO v_tag_id FROM tags WHERE tag_normalized = lower(NEW.document_type);
        END IF;
        
        -- Add to document_tags junction table
        INSERT INTO document_tags (document_id, tag_id)
        VALUES (NEW.id, v_tag_id)
        ON CONFLICT (document_id, tag_id) DO NOTHING;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger fires AFTER document type is set
CREATE TRIGGER document_type_auto_tag
    AFTER INSERT OR UPDATE OF document_type ON documents
    FOR EACH ROW
    WHEN (NEW.document_type IS NOT NULL)
    EXECUTE FUNCTION auto_add_document_type_tag();

-- ===========================================================
-- EVENT LOG TABLE - Comprehensive event tracking
-- ===========================================================

-- Events table - unified log for documents, files, and series events
-- Tracks state transitions, LLM usage, processing events, and errors
CREATE TABLE IF NOT EXISTS events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Entity reference (at least one must be set)
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    file_id UUID REFERENCES files(id) ON DELETE CASCADE,
    series_id UUID REFERENCES series(id) ON DELETE CASCADE,

    -- Event classification
    event_category VARCHAR NOT NULL CHECK (event_category IN (
        'state_transition',
        'llm_request',
        'processing',
        'error',
        'user_action'
    )),
    event_type VARCHAR(100) NOT NULL,  -- e.g., 'status_change', 'llm_classify', 'llm_summarize'

    -- State transition fields
    old_status VARCHAR(50),
    new_status VARCHAR(50),

    -- LLM usage fields
    llm_model VARCHAR(100),
    llm_prompt_text TEXT,
    llm_response_text TEXT,
    llm_request_tokens INTEGER,
    llm_response_tokens INTEGER,
    llm_latency_ms INTEGER,
    llm_cost_usd DECIMAL(10, 6),  -- Track costs with high precision

    -- Processing details
    task_name VARCHAR(100),
    details JSONB,  -- Flexible field for additional context
    error_message TEXT,

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    user_id VARCHAR(100)  -- For multi-user support
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_events_document_id ON events(document_id) WHERE document_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_events_file_id ON events(file_id) WHERE file_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_events_series_id ON events(series_id) WHERE series_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_event_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_event_category ON events(event_category);
CREATE INDEX IF NOT EXISTS idx_events_user_id ON events(user_id) WHERE user_id IS NOT NULL;

-- Composite index for common query patterns
CREATE INDEX IF NOT EXISTS idx_events_document_created ON events(document_id, created_at DESC) WHERE document_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_events_file_created ON events(file_id, created_at DESC) WHERE file_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_events_series_created ON events(series_id, created_at DESC) WHERE series_id IS NOT NULL;

COMMENT ON TABLE events IS 'Unified event log for documents, files, and series processing';
COMMENT ON COLUMN events.event_category IS 'Category: state_transition, llm_request, processing, error, user_action';
COMMENT ON COLUMN events.event_type IS 'Specific event type (e.g., status_change, llm_classify, ocr_complete)';
COMMENT ON COLUMN events.details IS 'JSONB field for additional context specific to the event type';