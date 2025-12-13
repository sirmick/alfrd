-- Migration: Add prompt behavior columns to prompts table
-- This enables static vs evolving prompt architecture
-- Reference: docs/PROMPT_ARCHITECTURE_REDESIGN.md Phase 1

-- Add new columns for prompt behavior configuration
ALTER TABLE prompts 
ADD COLUMN IF NOT EXISTS can_evolve BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS score_ceiling FLOAT DEFAULT NULL,
ADD COLUMN IF NOT EXISTS regenerates_on_update BOOLEAN DEFAULT false;

-- Create index for querying prompts by evolution capability
CREATE INDEX IF NOT EXISTS idx_prompts_can_evolve ON prompts(can_evolve, prompt_type);

-- Update existing prompts with appropriate behavior flags
-- Based on prompt_type, set the correct behavior

-- 1. Classifier: STATIC (never evolve) - will use context injection
UPDATE prompts 
SET can_evolve = false,
    score_ceiling = NULL,
    regenerates_on_update = false
WHERE prompt_type = 'classifier';

-- 2. Series Detector: STATIC (never evolve) - will use context injection
UPDATE prompts 
SET can_evolve = false,
    score_ceiling = NULL,
    regenerates_on_update = false
WHERE prompt_type = 'series_detector';

-- 3. File Summarizer: STATIC (never evolve) - generic summarization
UPDATE prompts 
SET can_evolve = false,
    score_ceiling = NULL,
    regenerates_on_update = false
WHERE prompt_type = 'file_summarizer';

-- 4. Generic Summarizer: EVOLVING with ceiling (0.95) - no regeneration
UPDATE prompts 
SET can_evolve = true,
    score_ceiling = 0.95,
    regenerates_on_update = false
WHERE prompt_type = 'summarizer';

-- 5. Series Summarizer: EVOLVING with ceiling (0.95) - WITH regeneration
UPDATE prompts 
SET can_evolve = true,
    score_ceiling = 0.95,
    regenerates_on_update = true
WHERE prompt_type = 'series_summarizer';

-- Add comment to table describing the new columns
COMMENT ON COLUMN prompts.can_evolve IS 'Whether this prompt can evolve based on performance scores (false = static)';
COMMENT ON COLUMN prompts.score_ceiling IS 'Maximum performance score before stopping evolution (NULL = no ceiling, typically 0.95)';
COMMENT ON COLUMN prompts.regenerates_on_update IS 'Whether updating this prompt triggers regeneration of all items using it (true for series_summarizer)';