-- Migration: Add Files Feature Tables
-- Date: 2025-12-01
-- Description: Add files and file_documents tables for auto-generated document collections

BEGIN;

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

-- Add file_summarizer prompt type to existing prompts table
-- (Extends the CHECK constraint on prompt_type)
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

COMMIT;