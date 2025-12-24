-- =====================================================
-- AGENTCORE RUNTIME DEPLOYMENT INTEGRATION
-- =====================================================
-- This migration adds AWS Bedrock AgentCore Runtime integration
-- to the threads table. This enables serverless tool execution
-- with centralized tool registration and lifecycle management.
--
-- Phase 6: Runtime deployment integration for tool execution
-- Region: ap-southeast-2 (Australia)
-- =====================================================

BEGIN;

-- =====================================================
-- ADD RUNTIME COLUMNS TO THREADS TABLE
-- =====================================================

-- Add runtime_deployment_id column (references AWS AgentCore Runtime deployment)
ALTER TABLE threads ADD COLUMN IF NOT EXISTS runtime_deployment_id TEXT;

-- Add runtime_metadata column for Runtime deployment state tracking
ALTER TABLE threads ADD COLUMN IF NOT EXISTS runtime_metadata JSONB DEFAULT '{}'::jsonb;

-- Add comments for documentation
COMMENT ON COLUMN threads.runtime_deployment_id IS 'AWS Bedrock AgentCore Runtime deployment ID for serverless tool execution with centralized tool registry';
COMMENT ON COLUMN threads.runtime_metadata IS 'Runtime deployment metadata (status, registered_tools, execution_timeout, created_at, etc.)';

-- =====================================================
-- INDEXES FOR RUNTIME QUERIES
-- =====================================================

-- Index for runtime_deployment_id lookups
CREATE INDEX IF NOT EXISTS idx_threads_runtime_deployment_id ON threads(runtime_deployment_id);

-- Index for runtime metadata queries (e.g., finding threads with Runtime enabled)
CREATE INDEX IF NOT EXISTS idx_threads_runtime_metadata ON threads USING GIN(runtime_metadata);

-- =====================================================
-- HELPER FUNCTIONS
-- =====================================================

-- Function to update runtime metadata for a thread
CREATE OR REPLACE FUNCTION update_thread_runtime_metadata(
    p_thread_id UUID,
    p_runtime_deployment_id TEXT DEFAULT NULL,
    p_runtime_status VARCHAR(50) DEFAULT 'ready',
    p_registered_tools JSONB DEFAULT '[]'::jsonb,
    p_execution_timeout_seconds INTEGER DEFAULT 120,
    p_created_at TIMESTAMPTZ DEFAULT NULL
)
RETURNS void
SECURITY DEFINER
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE threads
    SET
        runtime_deployment_id = COALESCE(p_runtime_deployment_id, threads.runtime_deployment_id),
        runtime_metadata = COALESCE(
            threads.runtime_metadata::jsonb ||
            jsonb_build_object(
                'status', p_runtime_status,
                'registered_tools', p_registered_tools,
                'execution_timeout_seconds', p_execution_timeout_seconds,
                'created_at', COALESCE(p_created_at, NOW()),
                'updated_at', NOW()
            ),
            threads.runtime_metadata
        ) || jsonb_build_object(
            'status', p_runtime_status,
            'registered_tools', p_registered_tools,
            'updated_at', NOW()
        ),
        updated_at = NOW()
    WHERE thread_id = p_thread_id;
END;
$$;

-- Function to check if thread has Runtime enabled
CREATE OR REPLACE FUNCTION has_thread_runtime_enabled(
    p_thread_id UUID
)
RETURNS BOOLEAN
SECURITY DEFINER
LANGUAGE plpgsql
AS $$
DECLARE
    v_has_runtime BOOLEAN;
BEGIN
    SELECT
        (runtime_deployment_id IS NOT NULL AND runtime_deployment_id != '')
    INTO v_has_runtime
    FROM threads
    WHERE thread_id = p_thread_id;

    RETURN COALESCE(v_has_runtime, FALSE);
END;
$$;

-- Function to get runtime deployment status for a thread
CREATE OR REPLACE FUNCTION get_thread_runtime_status(
    p_thread_id UUID
)
RETURNS TABLE (
    runtime_deployment_id TEXT,
    runtime_status VARCHAR(50),
    registered_tools JSONB,
    execution_timeout_seconds INTEGER,
    created_at TIMESTAMPTZ
)
SECURITY DEFINER
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        t.runtime_deployment_id,
        t.runtime_metadata->>'status' as runtime_status,
        (t.runtime_metadata->>'registered_tools')::JSONB as registered_tools,
        (t.runtime_metadata->>'execution_timeout_seconds')::INTEGER as execution_timeout_seconds,
        (t.runtime_metadata->>'created_at')::TIMESTAMPTZ as created_at
    FROM threads t
    WHERE t.thread_id = p_thread_id
        AND t.runtime_deployment_id IS NOT NULL;
END;
$$;

-- Function to add tool to runtime registered tools list
CREATE OR REPLACE FUNCTION add_tool_to_runtime(
    p_thread_id UUID,
    p_tool_name TEXT,
    p_tool_category VARCHAR(50) DEFAULT NULL
)
RETURNS boolean
SECURITY DEFINER
LANGUAGE plpgsql
AS $$
DECLARE
    v_current_tools JSONB;
    v_new_tools JSONB;
    v_tool_entry JSONB;
BEGIN
    -- Get current registered tools
    SELECT runtime_metadata->>'registered_tools' INTO v_current_tools
    FROM threads
    WHERE thread_id = p_thread_id
        AND runtime_deployment_id IS NOT NULL;

    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    -- Create tool entry
    v_tool_entry := jsonb_build_object(
        'name', p_tool_name,
        'category', p_tool_category,
        'registered_at', NOW()
    );

    -- Add tool to list (avoiding duplicates)
    IF jsonb_array_length(v_current_tools) > 0 THEN
        -- Check if tool already exists
        IF EXISTS (
            SELECT 1 FROM jsonb_array_elements(v_current_tools) as tool
            WHERE tool->>'name' = p_tool_name
        ) THEN
            RETURN TRUE;  -- Already registered
        END IF;

        -- Append new tool
        SELECT v_current_tools || v_tool_entry INTO v_new_tools;
    ELSE
        -- First tool
        SELECT jsonb_build_array(v_tool_entry) INTO v_new_tools;
    END IF;

    -- Update thread metadata
    UPDATE threads
    SET runtime_metadata = runtime_metadata || jsonb_build_object(
        'registered_tools', v_new_tools,
        'updated_at', NOW()
    )
    WHERE thread_id = p_thread_id;

    RETURN TRUE;
END;
$$;

-- Function to clear runtime deployment from thread (for cleanup)
CREATE OR REPLACE FUNCTION clear_thread_runtime(
    p_thread_id UUID
)
RETURNS boolean
SECURITY DEFINER
LANGUAGE plpgsql
AS $$
DECLARE
    v_cleared_deployment_id TEXT;
BEGIN
    -- Get the runtime deployment ID before clearing
    SELECT runtime_deployment_id INTO v_cleared_deployment_id
    FROM threads
    WHERE thread_id = p_thread_id;

    -- Clear runtime columns
    UPDATE threads
    SET
        runtime_deployment_id = NULL,
        runtime_metadata = '{}'::jsonb,
        updated_at = NOW()
    WHERE thread_id = p_thread_id;

    -- Return TRUE if a deployment was cleared
    RETURN (v_cleared_deployment_id IS NOT NULL);
END;
$$;

-- =====================================================
-- VIEWS FOR RUNTIME MONITORING
-- =====================================================

-- View for threads with Runtime enabled
CREATE OR REPLACE VIEW threads_with_runtime AS
SELECT
    t.thread_id,
    t.account_id,
    t.project_id,
    t.runtime_deployment_id,
    t.runtime_metadata->>'status' as runtime_status,
    (t.runtime_metadata->>'registered_tools')::JSONB as registered_tools,
    (t.runtime_metadata->>'execution_timeout_seconds')::INTEGER as execution_timeout_seconds,
    jsonb_array_length((t.runtime_metadata->>'registered_tools')::JSONB) as registered_tool_count,
    (t.runtime_metadata->>'created_at')::TIMESTAMPTZ as runtime_created_at,
    (t.runtime_metadata->>'updated_at')::TIMESTAMPTZ as runtime_updated_at,
    t.created_at,
    t.updated_at,
    p.name as project_name,
    acc.email as account_email
FROM threads t
LEFT JOIN projects p ON t.project_id = p.project_id
LEFT JOIN basejump.accounts acc ON t.account_id = acc.id
WHERE t.runtime_deployment_id IS NOT NULL
ORDER BY t.created_at DESC;

-- View for threads without Runtime (local execution only)
CREATE OR REPLACE VIEW threads_without_runtime AS
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
WHERE t.runtime_deployment_id IS NULL
ORDER BY t.created_at DESC;

-- =====================================================
-- TRIGGER FOR RUNTIME METADATA VALIDATION
-- =====================================================

-- Function to validate runtime_metadata structure
CREATE OR REPLACE FUNCTION validate_runtime_metadata()
RETURNS TRIGGER
SECURITY DEFINER
LANGUAGE plpgsql
AS $$
BEGIN
    -- If runtime_deployment_id is NULL, clear runtime_metadata
    IF NEW.runtime_deployment_id IS NULL THEN
        NEW.runtime_metadata = '{}'::jsonb;
    END IF;

    -- If runtime_deployment_id is set but runtime_metadata is empty, initialize it
    IF NEW.runtime_deployment_id IS NOT NULL AND jsonb_typeof(NEW.runtime_metadata) = 'null' THEN
        NEW.runtime_metadata = jsonb_build_object(
            'status', 'ready',
            'registered_tools', '[]'::jsonb,
            'execution_timeout_seconds', 120,
            'created_at', NOW(),
            'updated_at', NOW()
        );
    END IF;

    -- Always update the updated_at timestamp in runtime_metadata
    IF NEW.runtime_deployment_id IS NOT NULL AND jsonb_typeof(NEW.runtime_metadata) != 'null' THEN
        NEW.runtime_metadata = NEW.runtime_metadata || jsonb_build_object('updated_at', NOW());
    END IF;

    RETURN NEW;
END;
$$;

-- Create trigger
DROP TRIGGER IF EXISTS trigger_validate_runtime_metadata ON threads;
CREATE TRIGGER trigger_validate_runtime_metadata
    BEFORE INSERT OR UPDATE OF runtime_deployment_id, runtime_metadata ON threads
    FOR EACH ROW
    EXECUTE FUNCTION validate_runtime_metadata();

COMMIT;

-- =====================================================
-- VERIFICATION QUERIES
-- =====================================================
-- Run these after migration to verify:

-- Check columns were added
-- SELECT column_name, data_type, column_default, is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'threads'
-- AND column_name LIKE '%runtime%';

-- Check indexes were created
-- SELECT indexname, indexdef
-- FROM pg_indexes
-- WHERE tablename = 'threads'
-- AND indexname LIKE '%runtime%';

-- Check functions were created
-- SELECT routine_name, routine_type
-- FROM information_schema.routines
-- WHERE routine_schema = 'public'
-- AND routine_name LIKE '%runtime%';

-- Check views were created
-- SELECT table_name
-- FROM information_schema.views
-- WHERE table_name LIKE '%runtime%';
