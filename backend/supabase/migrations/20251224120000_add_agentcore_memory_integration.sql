-- =====================================================
-- AGENTCORE MEMORY INTEGRATION
-- =====================================================
-- This migration adds AWS Bedrock AgentCore Memory integration
-- to the threads table. This enables semantic conversation storage
-- with vector-based retrieval capabilities.
--
-- Phase 4: Memory integration for persistent conversation storage
-- Region: ap-southeast-2 (Australia)
-- =====================================================

BEGIN;

-- =====================================================
-- ADD MEMORY COLUMNS TO THREADS TABLE
-- =====================================================

-- Add memory_resource_id column (references AWS AgentCore Memory resource)
ALTER TABLE threads ADD COLUMN IF NOT EXISTS memory_resource_id TEXT;

-- Add memory_metadata column for Memory resource state tracking
ALTER TABLE threads ADD COLUMN IF NOT EXISTS memory_metadata JSONB DEFAULT '{}'::jsonb;

-- Add comments for documentation
COMMENT ON COLUMN threads.memory_resource_id IS 'AWS Bedrock AgentCore Memory resource ID for semantic conversation storage with vector-based retrieval';
COMMENT ON COLUMN threads.memory_metadata IS 'Memory resource metadata (status, semantic_search_enabled, retention_days, created_at, etc.)';

-- =====================================================
-- INDEXES FOR MEMORY QUERIES
-- =====================================================

-- Index for memory_resource_id lookups
CREATE INDEX IF NOT EXISTS idx_threads_memory_resource_id ON threads(memory_resource_id);

-- Index for memory metadata queries (e.g., finding threads with Memory enabled)
CREATE INDEX IF NOT EXISTS idx_threads_memory_metadata ON threads USING GIN(memory_metadata);

-- =====================================================
-- HELPER FUNCTIONS
-- =====================================================

-- Function to update memory metadata for a thread
CREATE OR REPLACE FUNCTION update_thread_memory_metadata(
    p_thread_id UUID,
    p_memory_resource_id TEXT DEFAULT NULL,
    p_memory_status VARCHAR(50) DEFAULT 'ready',
    p_semantic_search_enabled BOOLEAN DEFAULT TRUE,
    p_retention_days INTEGER DEFAULT 90,
    p_created_at TIMESTAMPTZ DEFAULT NULL
)
RETURNS void
SECURITY DEFINER
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE threads
    SET
        memory_resource_id = COALESCE(p_memory_resource_id, threads.memory_resource_id),
        memory_metadata = COALESCE(
            threads.memory_metadata::jsonb ||
            jsonb_build_object(
                'status', p_memory_status,
                'semantic_search_enabled', p_semantic_search_enabled,
                'retention_days', p_retention_days,
                'created_at', COALESCE(p_created_at, NOW()),
                'updated_at', NOW()
            ),
            threads.memory_metadata
        ) || jsonb_build_object(
            'status', p_memory_status,
            'semantic_search_enabled', p_semantic_search_enabled,
            'updated_at', NOW()
        ),
        updated_at = NOW()
    WHERE thread_id = p_thread_id;
END;
$$;

-- Function to check if thread has Memory enabled
CREATE OR REPLACE FUNCTION has_thread_memory_enabled(
    p_thread_id UUID
)
RETURNS BOOLEAN
SECURITY DEFINER
LANGUAGE plpgsql
AS $$
DECLARE
    v_has_memory BOOLEAN;
BEGIN
    SELECT
        (memory_resource_id IS NOT NULL AND memory_resource_id != '') AND
        (memory_metadata->>'semantic_search_enabled' = 'true' OR memory_metadata->>'semantic_search_enabled' IS NULL)
    INTO v_has_memory
    FROM threads
    WHERE thread_id = p_thread_id;

    RETURN COALESCE(v_has_memory, FALSE);
END;
$$;

-- Function to get memory resource status for a thread
CREATE OR REPLACE FUNCTION get_thread_memory_status(
    p_thread_id UUID
)
RETURNS TABLE (
    memory_resource_id TEXT,
    memory_status VARCHAR(50),
    semantic_search_enabled BOOLEAN,
    retention_days INTEGER,
    created_at TIMESTAMPTZ
)
SECURITY DEFINER
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        t.memory_resource_id,
        t.memory_metadata->>'status' as memory_status,
        (t.memory_metadata->>'semantic_search_enabled')::BOOLEAN as semantic_search_enabled,
        (t.memory_metadata->>'retention_days')::INTEGER as retention_days,
        (t.memory_metadata->>'created_at')::TIMESTAMPTZ as created_at
    FROM threads t
    WHERE t.thread_id = p_thread_id
        AND t.memory_resource_id IS NOT NULL;
END;
$$;

-- Function to clear memory resource from thread (for cleanup)
CREATE OR REPLACE FUNCTION clear_thread_memory(
    p_thread_id UUID
)
RETURNS boolean
SECURITY DEFINER
LANGUAGE plpgsql
AS $$
DECLARE
    v_cleared_resource_id TEXT;
BEGIN
    -- Get the memory resource ID before clearing
    SELECT memory_resource_id INTO v_cleared_resource_id
    FROM threads
    WHERE thread_id = p_thread_id;

    -- Clear memory columns
    UPDATE threads
    SET
        memory_resource_id = NULL,
        memory_metadata = '{}'::jsonb,
        updated_at = NOW()
    WHERE thread_id = p_thread_id;

    -- Return TRUE if a resource was cleared
    RETURN (v_cleared_resource_id IS NOT NULL);
END;
$$;

-- =====================================================
-- VIEWS FOR MEMORY MONITORING
-- =====================================================

-- View for threads with Memory enabled
CREATE OR REPLACE VIEW threads_with_memory AS
SELECT
    t.thread_id,
    t.account_id,
    t.project_id,
    t.memory_resource_id,
    t.memory_metadata->>'status' as memory_status,
    (t.memory_metadata->>'semantic_search_enabled')::BOOLEAN as semantic_search_enabled,
    (t.memory_metadata->>'retention_days')::INTEGER as retention_days,
    (t.memory_metadata->>'created_at')::TIMESTAMPTZ as memory_created_at,
    (t.memory_metadata->>'updated_at')::TIMESTAMPTZ as memory_updated_at,
    t.created_at,
    t.updated_at,
    p.name as project_name,
    acc.email as account_email
FROM threads t
LEFT JOIN projects p ON t.project_id = p.project_id
LEFT JOIN basejump.accounts acc ON t.account_id = acc.id
WHERE t.memory_resource_id IS NOT NULL
ORDER BY t.created_at DESC;

-- View for threads without Memory (fallback to database)
CREATE OR REPLACE VIEW threads_without_memory AS
SELECT
    t.thread_id,
    t.account_id,
    t.project_id,
    t.created_at,
    t.updated_at,
    p.name as project_name,
    acc.email as account_email
FROM threads t
LEFT JOIN projects p ON t.project_id = p.project_id
LEFT JOIN basejump.accounts acc ON t.account_id = acc.id
WHERE t.memory_resource_id IS NULL
ORDER BY t.created_at DESC;

-- =====================================================
-- TRIGGER FOR MEMORY METADATA VALIDATION
-- =====================================================

-- Function to validate memory_metadata structure
CREATE OR REPLACE FUNCTION validate_memory_metadata()
RETURNS TRIGGER
SECURITY DEFINER
LANGUAGE plpgsql
AS $$
BEGIN
    -- If memory_resource_id is NULL, clear memory_metadata
    IF NEW.memory_resource_id IS NULL THEN
        NEW.memory_metadata = '{}'::jsonb;
    END IF;

    -- If memory_resource_id is set but memory_metadata is empty, initialize it
    IF NEW.memory_resource_id IS NOT NULL AND jsonb_typeof(NEW.memory_metadata) = 'null' THEN
        NEW.memory_metadata = jsonb_build_object(
            'status', 'ready',
            'semantic_search_enabled', TRUE,
            'created_at', NOW(),
            'updated_at', NOW()
        );
    END IF;

    -- Always update the updated_at timestamp in memory_metadata
    IF NEW.memory_resource_id IS NOT NULL AND jsonb_typeof(NEW.memory_metadata) != 'null' THEN
        NEW.memory_metadata = NEW.memory_metadata || jsonb_build_object('updated_at', NOW());
    END IF;

    RETURN NEW;
END;
$$;

-- Create trigger
DROP TRIGGER IF EXISTS trigger_validate_memory_metadata ON threads;
CREATE TRIGGER trigger_validate_memory_metadata
    BEFORE INSERT OR UPDATE OF memory_resource_id, memory_metadata ON threads
    FOR EACH ROW
    EXECUTE FUNCTION validate_memory_metadata();

COMMIT;

-- =====================================================
-- VERIFICATION QUERIES
-- =====================================================
-- Run these after migration to verify:

-- Check columns were added
-- SELECT column_name, data_type, column_default, is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'threads'
-- AND column_name LIKE '%memory%';

-- Check indexes were created
-- SELECT indexname, indexdef
-- FROM pg_indexes
-- WHERE tablename = 'threads'
-- AND indexname LIKE '%memory%';

-- Check functions were created
-- SELECT routine_name, routine_type
-- FROM information_schema.routines
-- WHERE routine_schema = 'public'
-- AND routine_name LIKE '%memory%';

-- Check views were created
-- SELECT table_name
-- FROM information_schema.views
-- WHERE table_name LIKE '%memory%';
