-- DuckDB Schema for ALFRD (Automated Ledger & Filing Research Database)
-- Core documents table
CREATE TABLE IF NOT EXISTS documents (
    id VARCHAR PRIMARY KEY,
    filename VARCHAR NOT NULL,
    original_path VARCHAR NOT NULL,
    file_type VARCHAR NOT NULL,
    file_size BIGINT,
    mime_type VARCHAR,
    
    -- Processing status - detailed pipeline tracking
    status VARCHAR NOT NULL CHECK (status IN (
        'pending',           -- Document folder detected
        'ocr_started',       -- AWS Textract called
        'ocr_completed',     -- Text extracted
        'classifying',       -- MCP classification in progress
        'classified',        -- Type determined
        'processing',        -- Type-specific handler processing
        'completed',         -- All processing done
        'failed'            -- Error at any stage
    )),
    processed_at TIMESTAMP,
    error_message VARCHAR,
    
    -- Classification (new simplified system)
    document_type VARCHAR CHECK (document_type IN ('junk', 'bill', 'finance')),
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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id VARCHAR,
    
    -- Full-text search support
    extracted_text TEXT,
    
    -- JSON for flexible data
    structured_data JSON,
    tags JSON,
    folder_metadata JSON                    -- Parsed meta.json content
);

-- Summaries table (weekly, monthly, yearly rollups)
CREATE TABLE IF NOT EXISTS summaries (
    id VARCHAR PRIMARY KEY,
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
    document_ids JSON,
    
    -- Metadata
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id VARCHAR,
    llm_model VARCHAR,
    
    UNIQUE(period_type, period_start, period_end, category, user_id)
);

-- Processing queue/events table
CREATE TABLE IF NOT EXISTS processing_events (
    id VARCHAR PRIMARY KEY,
    event_type VARCHAR NOT NULL,
    document_id VARCHAR,
    status VARCHAR NOT NULL CHECK (status IN ('pending', 'completed', 'failed')),
    
    payload JSON,
    error_message VARCHAR,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP,
    
    user_id VARCHAR,
    
    FOREIGN KEY (document_id) REFERENCES documents(id)
);

-- Analytics/insights table
CREATE TABLE IF NOT EXISTS analytics (
    id VARCHAR PRIMARY KEY,
    metric_name VARCHAR NOT NULL,
    category VARCHAR,
    period DATE NOT NULL,
    
    value DECIMAL(12, 2),
    metadata JSON,
    
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id VARCHAR,
    
    UNIQUE(metric_name, category, period, user_id)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_documents_category ON documents(category, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(document_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_due_date ON documents(due_date);
CREATE INDEX IF NOT EXISTS idx_documents_vendor ON documents(vendor);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_user ON documents(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_summaries_period ON summaries(period_type, period_start DESC);
CREATE INDEX IF NOT EXISTS idx_summaries_category ON summaries(category);
CREATE INDEX IF NOT EXISTS idx_summaries_user ON summaries(user_id, period_start DESC);

CREATE INDEX IF NOT EXISTS idx_events_status ON processing_events(status, created_at);
CREATE INDEX IF NOT EXISTS idx_events_document ON processing_events(document_id);

CREATE INDEX IF NOT EXISTS idx_analytics_metric ON analytics(metric_name, period DESC);
CREATE INDEX IF NOT EXISTS idx_analytics_user ON analytics(user_id, period DESC);