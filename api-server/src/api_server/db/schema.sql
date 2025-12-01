-- PostgreSQL Schema for ALFRD (Automated Ledger & Filing Research Database)
-- Migrated from DuckDB on 2025-11-30

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

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
        'ocr_completed',           -- Text extracted
        'classifying',             -- MCP classification in progress
        'classified',              -- Type determined
        'scoring_classification',  -- Scoring classifier performance
        'scored_classification',   -- Classifier scored and prompt updated
        'summarizing',             -- Generating summary
        'summarized',              -- Summary generated
        'scoring_summary',         -- Scoring summarizer performance
        'completed',               -- All processing done
        'failed'                   -- Error at any stage
    )),
    processed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    
    -- Classification (new simplified system)
    document_type VARCHAR,  -- Dynamic types: 'junk', 'bill', 'finance', 'school', 'event', etc.
    suggested_type VARCHAR,  -- LLM-suggested new type (if different from existing)
    secondary_tags JSONB,    -- Array of secondary classification tags (binary JSON)
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
    structured_data JSONB,                  -- Extracted fields as JSON (binary)
    tags JSONB,
    folder_metadata JSONB                   -- Parsed meta.json content
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

-- Prompts table - store evolving classifier and summarizer prompts
CREATE TABLE IF NOT EXISTS prompts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    prompt_type VARCHAR NOT NULL CHECK (prompt_type IN ('classifier', 'summarizer')),
    document_type VARCHAR,  -- NULL for classifier, specific type for summarizers
    prompt_text TEXT NOT NULL,
    version INTEGER DEFAULT 1,
    performance_score FLOAT,
    performance_metrics JSONB,  -- Detailed scoring metrics
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT true,
    user_id VARCHAR,
    
    UNIQUE(prompt_type, document_type, version, user_id)
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
CREATE INDEX IF NOT EXISTS idx_documents_tags ON documents USING GIN(tags);

CREATE INDEX IF NOT EXISTS idx_summaries_period ON summaries(period_type, period_start DESC);
CREATE INDEX IF NOT EXISTS idx_summaries_category ON summaries(category);
CREATE INDEX IF NOT EXISTS idx_summaries_user ON summaries(user_id, period_start DESC);

CREATE INDEX IF NOT EXISTS idx_events_status ON processing_events(status, created_at);
CREATE INDEX IF NOT EXISTS idx_events_document ON processing_events(document_id);

CREATE INDEX IF NOT EXISTS idx_analytics_metric ON analytics(metric_name, period DESC);
CREATE INDEX IF NOT EXISTS idx_analytics_user ON analytics(user_id, period DESC);

CREATE INDEX IF NOT EXISTS idx_prompts_active ON prompts(prompt_type, document_type, is_active);
CREATE INDEX IF NOT EXISTS idx_prompts_performance ON prompts(prompt_type, performance_score DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_classification_suggestions_approved ON classification_suggestions(approved, created_at);
CREATE INDEX IF NOT EXISTS idx_document_types_active ON document_types(is_active, usage_count DESC);

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
    document_type VARCHAR NOT NULL,
    tags JSONB NOT NULL,              -- Array of tags defining this file
    tag_signature VARCHAR NOT NULL,    -- Sorted, lowercase "bill:lexus-tx-550"
    
    -- File metadata
    document_count INT DEFAULT 0,
    first_document_date TIMESTAMP WITH TIME ZONE,
    last_document_date TIMESTAMP WITH TIME ZONE,
    
    -- Generated content
    summary_text TEXT,
    summary_metadata JSONB,            -- Structured insights (totals, trends, etc.)
    
    -- Prompt tracking
    prompt_version UUID REFERENCES prompts(id),
    
    -- Status tracking
    status VARCHAR NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending',      -- Needs generation
        'generated',    -- Summary created
        'outdated',     -- New documents added since last generation
        'regenerating'  -- Being updated
    )),
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_generated_at TIMESTAMP WITH TIME ZONE,
    
    -- Multi-user support
    user_id VARCHAR,
    
    -- Ensure uniqueness per user
    UNIQUE(tag_signature, user_id)
);

-- File-document associations (many-to-many)
CREATE TABLE IF NOT EXISTS file_documents (
    file_id UUID REFERENCES files(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (file_id, document_id)
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_files_type_tags ON files USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
CREATE INDEX IF NOT EXISTS idx_files_signature ON files(tag_signature);
CREATE INDEX IF NOT EXISTS idx_files_user ON files(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_files_type ON files(document_type, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_file_documents_file ON file_documents(file_id);
CREATE INDEX IF NOT EXISTS idx_file_documents_document ON file_documents(document_id);

-- Extend prompts table to support file_summarizer
ALTER TABLE prompts DROP CONSTRAINT IF EXISTS prompts_prompt_type_check;
ALTER TABLE prompts ADD CONSTRAINT prompts_prompt_type_check
    CHECK (prompt_type IN ('classifier', 'summarizer', 'file_summarizer'));

-- Insert default file summarizer prompt
INSERT INTO prompts (prompt_type, document_type, prompt_text, version, is_active, performance_score)
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
    0.8
) ON CONFLICT (prompt_type, document_type, version, user_id) DO NOTHING;

-- Trigger to auto-update updated_at timestamp on files
CREATE TRIGGER files_updated_at
    BEFORE UPDATE ON files
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();