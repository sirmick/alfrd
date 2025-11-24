-- DuckDB Schema for esec Document Secretary
-- Core documents table
CREATE TABLE IF NOT EXISTS documents (
    id VARCHAR PRIMARY KEY,
    filename VARCHAR NOT NULL,
    original_path VARCHAR NOT NULL,
    file_type VARCHAR NOT NULL,
    file_size BIGINT,
    mime_type VARCHAR,
    
    -- Processing status
    status VARCHAR NOT NULL CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    processed_at TIMESTAMP,
    error_message VARCHAR,
    
    -- Categorization
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
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id VARCHAR,
    
    -- Full-text search support
    extracted_text TEXT,
    
    -- JSON for flexible data
    structured_data JSON,
    tags JSON
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
CREATE INDEX IF NOT EXISTS idx_documents_due_date ON documents(due_date) WHERE due_date IS NOT NULL;
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