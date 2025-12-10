-- Migration: Add recovery and retry tracking columns
-- Date: 2025-12-10
-- Purpose: Enable stuck document/file detection and automatic recovery

-- Add recovery columns to documents table
ALTER TABLE documents ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS retry_count INT DEFAULT 0;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS max_retries INT DEFAULT 3;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS last_error TEXT;

-- Add recovery columns to files table
ALTER TABLE files ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE files ADD COLUMN IF NOT EXISTS retry_count INT DEFAULT 0;
ALTER TABLE files ADD COLUMN IF NOT EXISTS max_retries INT DEFAULT 3;
ALTER TABLE files ADD COLUMN IF NOT EXISTS last_error TEXT;

-- Add index for efficient stale document queries
CREATE INDEX IF NOT EXISTS idx_documents_stale_check 
    ON documents(status, updated_at) 
    WHERE status IN ('ocr_in_progress', 'summarizing', 'generating');

-- Add index for efficient stale file queries
CREATE INDEX IF NOT EXISTS idx_files_stale_check 
    ON files(status, updated_at) 
    WHERE status IN ('generating', 'regenerating');

-- Add permanently_failed status to documents
ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_status_check;
ALTER TABLE documents ADD CONSTRAINT documents_status_check 
    CHECK (status IN (
        'pending', 'ocr_started', 'ocr_in_progress', 'ocr_completed',
        'classifying', 'classified', 'scoring_classification', 'scored_classification',
        'summarizing', 'summarized', 'scoring_summary',
        'filed', 'completed', 'failed', 'permanently_failed'
    ));

COMMENT ON COLUMN documents.processing_started_at IS 'Timestamp when processing started for current status';
COMMENT ON COLUMN documents.retry_count IS 'Number of retry attempts for this document';
COMMENT ON COLUMN documents.max_retries IS 'Maximum retry attempts before marking permanently_failed';
COMMENT ON COLUMN documents.last_error IS 'Most recent error message if processing failed';

COMMENT ON COLUMN files.processing_started_at IS 'Timestamp when file generation started';
COMMENT ON COLUMN files.retry_count IS 'Number of retry attempts for file generation';
COMMENT ON COLUMN files.max_retries IS 'Maximum retry attempts before marking failed';
COMMENT ON COLUMN files.last_error IS 'Most recent error message if generation failed';