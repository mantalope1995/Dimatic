-- ============================================================================
-- CUGA Schema Migration
-- ============================================================================
-- Purpose: Set up database schema for CUGA (Configurable Generalist Agent)
-- integration with Suna's multi-tenant architecture.
--
-- This migration creates:
-- 1. Checkpoint storage for LangGraph state persistence
-- 2. Thread metadata for multi-tenant scoping
-- 3. Thread mappings between CUGA and Suna thread IDs
-- 4. Row Level Security (RLS) policies for tenant isolation
--
-- Version: 002
-- Date: 2025-12-24
-- ============================================================================

BEGIN;

-- ============================================================================
-- Schema Creation
-- ============================================================================

-- Create dedicated schema for CUGA tables
CREATE SCHEMA IF NOT EXISTS cuga;

-- Grant usage on schema (will be further restricted by RLS)
GRANT USAGE ON SCHEMA cuga TO authenticated, anon, service_role;

-- ============================================================================
-- Checkpoint Tables (LangGraph State Persistence)
-- ============================================================================

-- Main checkpoint storage table
-- Stores serialized agent state from LangGraph execution
CREATE TABLE IF NOT EXISTS cuga.checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type TEXT,
    checkpoint JSONB NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

-- Indexes for checkpoint queries
CREATE INDEX IF NOT EXISTS idx_checkpoints_thread_id ON cuga.checkpoints(thread_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_parent_id ON cuga.checkpoints(parent_checkpoint_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_created_at ON cuga.checkpoints(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_checkpoints_thread_created ON cuga.checkpoints(thread_id, created_at DESC);

-- Checkpoint writes table for tracking state updates
-- Stores individual channel writes for debugging and replay
CREATE TABLE IF NOT EXISTS cuga.checkpoint_writes (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    type TEXT,
    channel TEXT,
    value JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

-- Index for checkpoint writes
CREATE INDEX IF NOT EXISTS idx_checkpoint_writes_checkpoint_id ON cuga.checkpoint_writes(
    thread_id, checkpoint_ns, checkpoint_id
);

-- ============================================================================
-- Thread Metadata Tables
-- ============================================================================

-- Thread metadata for multi-tenant scoping
-- Links CUGA thread_id to Suna's account_id and project_id
CREATE TABLE IF NOT EXISTS cuga.thread_metadata (
    thread_id TEXT PRIMARY KEY,
    account_id UUID REFERENCES basejump.accounts(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(project_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for thread metadata lookups
CREATE INDEX IF NOT EXISTS idx_thread_metadata_account_id ON cuga.thread_metadata(account_id);
CREATE INDEX IF NOT EXISTS idx_thread_metadata_project_id ON cuga.thread_metadata(project_id);
CREATE INDEX IF NOT EXISTS idx_thread_metadata_account_project ON cuga.thread_metadata(account_id, project_id);

-- Thread mappings table
-- Maps CUGA's internal thread_id to Suna's thread UUID
CREATE TABLE IF NOT EXISTS cuga.thread_mappings (
    cuga_thread_id TEXT PRIMARY KEY,
    suna_thread_id UUID NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES basejump.accounts(id),
    project_id UUID REFERENCES projects(project_id),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for thread mapping lookups
CREATE INDEX IF NOT EXISTS idx_thread_mappings_suna ON cuga.thread_mappings(suna_thread_id);
CREATE INDEX IF NOT EXISTS idx_thread_mappings_account ON cuga.thread_mappings(account_id);
CREATE INDEX IF NOT EXISTS idx_thread_mappings_account_project ON cuga.thread_mappings(account_id, project_id);

-- Optional: Variables table for cross-thread shared variables
-- Only needed if you want global variables accessible across threads
CREATE TABLE IF NOT EXISTS cuga.variables (
    variable_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES basejump.accounts(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(project_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    value JSONB NOT NULL,
    description TEXT,
    type TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT variables_account_project_name UNIQUE(account_id, project_id, name)
);

CREATE INDEX IF NOT EXISTS idx_variables_account_project ON cuga.variables(account_id, project_id);

-- ============================================================================
-- Row Level Security (RLS)
-- ============================================================================

-- Enable RLS on all CUGA tables
ALTER TABLE cuga.checkpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE cuga.checkpoint_writes ENABLE ROW LEVEL SECURITY;
ALTER TABLE cuga.thread_metadata ENABLE ROW LEVEL SECURITY;
ALTER TABLE cuga.thread_mappings ENABLE ROW LEVEL SECURITY;
ALTER TABLE cuga.variables ENABLE ROW LEVEL SECURITY;

-- Checkpoints RLS policies
-- Users can only access checkpoints for threads in their account
CREATE POLICY checkpoints_select_policy ON cuga.checkpoints
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM cuga.thread_metadata tm
            WHERE tm.thread_id = cuga.checkpoints.thread_id
            AND basejump.has_role_on_account(tm.account_id) = true
        )
    );

CREATE POLICY checkpoints_insert_policy ON cuga.checkpoints
    FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM cuga.thread_metadata tm
            WHERE tm.thread_id = cuga.checkpoints.thread_id
            AND basejump.has_role_on_account(tm.account_id) = true
        )
    );

CREATE POLICY checkpoints_update_policy ON cuga.checkpoints
    FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM cuga.thread_metadata tm
            WHERE tm.thread_id = cuga.checkpoints.thread_id
            AND basejump.has_role_on_account(tm.account_id) = true
        )
    );

CREATE POLICY checkpoints_delete_policy ON cuga.checkpoints
    FOR DELETE
    USING (
        EXISTS (
            SELECT 1 FROM cuga.thread_metadata tm
            WHERE tm.thread_id = cuga.checkpoints.thread_id
            AND basejump.has_role_on_account(tm.account_id) = true
        )
    );

-- Allow public read access to checkpoints for shared threads (if needed)
CREATE POLICY checkpoints_public_select_policy ON cuga.checkpoints
    FOR SELECT
    TO anon
    USING (
        EXISTS (
            SELECT 1 FROM threads t
            JOIN cuga.thread_mappings tm ON tm.suna_thread_id = t.thread_id
            WHERE tm.cuga_thread_id = cuga.checkpoints.thread_id
            AND t.is_public = true
        )
    );

-- Checkpoint writes RLS policies
CREATE POLICY checkpoint_writes_select_policy ON cuga.checkpoint_writes
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM cuga.thread_metadata tm
            WHERE tm.thread_id = cuga.checkpoint_writes.thread_id
            AND basejump.has_role_on_account(tm.account_id) = true
        )
    );

CREATE POLICY checkpoint_writes_insert_policy ON cuga.checkpoint_writes
    FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM cuga.thread_metadata tm
            WHERE tm.thread_id = cuga.checkpoint_writes.thread_id
            AND basejump.has_role_on_account(tm.account_id) = true
        )
    );

-- Thread metadata RLS policies
CREATE POLICY thread_metadata_select_policy ON cuga.thread_metadata
    FOR ALL
    USING (basejump.has_role_on_account(account_id) = true);

CREATE POLICY thread_metadata_insert_policy ON cuga.thread_metadata
    FOR INSERT
    WITH CHECK (basejump.has_role_on_account(account_id) = true);

-- Thread mappings RLS policies
CREATE POLICY thread_mappings_select_policy ON cuga.thread_mappings
    FOR ALL
    USING (basejump.has_role_on_account(account_id) = true);

CREATE POLICY thread_mappings_insert_policy ON cuga.thread_mappings
    FOR INSERT
    WITH CHECK (basejump.has_role_on_account(account_id) = true);

-- Variables RLS policies
CREATE POLICY variables_select_policy ON cuga.variables
    FOR ALL
    USING (basejump.has_role_on_account(account_id) = true);

CREATE POLICY variables_insert_policy ON cuga.variables
    FOR INSERT
    WITH CHECK (basejump.has_role_on_account(account_id) = true);

CREATE POLICY variables_update_policy ON cuga.variables
    FOR UPDATE
    USING (basejump.has_role_on_account(account_id) = true);

CREATE POLICY variables_delete_policy ON cuga.variables
    FOR DELETE
    USING (basejump.has_role_on_account(account_id) = true);

-- ============================================================================
-- Grant Permissions
-- ============================================================================

-- Grant full permissions to authenticated and service_role
GRANT SELECT, INSERT, UPDATE, DELETE ON cuga.checkpoints TO authenticated, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON cuga.checkpoint_writes TO authenticated, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON cuga.thread_metadata TO authenticated, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON cuga.thread_mappings TO authenticated, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON cuga.variables TO authenticated, service_role;

-- Grant limited read access to anon (public) for shared threads
GRANT SELECT ON cuga.checkpoints TO anon;
GRANT SELECT ON cuga.thread_metadata TO anon;
GRANT SELECT ON cuga.thread_mappings TO anon;

-- ============================================================================
-- Helper Functions
-- ============================================================================

-- Function to get storage stats for an account
CREATE OR REPLACE FUNCTION cuga.get_account_storage_stats(p_account_id UUID)
RETURNS TABLE (
    checkpoint_count BIGINT,
    checkpoint_size_bytes BIGINT,
    thread_count BIGINT,
    variable_count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(*) AS checkpoint_count,
        pg_total_relation_size('cuga.checkpoints') AS checkpoint_size_bytes,
        (SELECT COUNT(*) FROM cuga.thread_metadata WHERE account_id = p_account_id) AS thread_count,
        (SELECT COUNT(*) FROM cuga.variables WHERE account_id = p_account_id) AS variable_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

GRANT EXECUTE ON FUNCTION cuga.get_account_storage_stats TO authenticated, service_role;

-- Function to clean up old checkpoints
CREATE OR REPLACE FUNCTION cuga.cleanup_old_checkpoints(p_days INTEGER DEFAULT 7)
RETURNS INTEGER AS $$
DECLARE
    v_deleted_count INTEGER;
    v_cutoff_date TIMESTAMPTZ;
BEGIN
    v_cutoff_date := NOW() - (p_days || ' days')::INTERVAL;

    -- Get the latest checkpoint for each thread
    WITH latest_checkpoints AS (
        SELECT DISTINCT ON (thread_id)
            thread_id,
            checkpoint_id
        FROM cuga.checkpoints
        WHERE created_at >= v_cutoff_date
        ORDER BY thread_id, created_at DESC
    )

    -- Delete old checkpoints, keeping the latest one
    DELETE FROM cuga.checkpoints
    WHERE created_at < v_cutoff_date
    AND (thread_id, checkpoint_id) NOT IN (
        SELECT thread_id, checkpoint_id FROM latest_checkpoints
    );

    GET DIAGNOSTICS v_deleted_count = ROW_COUNT;

    -- Also clean up old checkpoint writes
    DELETE FROM cuga.checkpoint_writes
    WHERE created_at < v_cutoff_date;

    RETURN v_deleted_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

GRANT EXECUTE ON FUNCTION cuga.cleanup_old_checkpoints TO service_role;

-- Trigger to update updated_at on thread_metadata
CREATE OR REPLACE FUNCTION cuga.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER thread_metadata_updated_at
    BEFORE UPDATE ON cuga.thread_metadata
    FOR EACH ROW
    EXECUTE FUNCTION cuga.update_updated_at();

-- ============================================================================
-- Comments for Documentation
-- ============================================================================

COMMENT ON SCHEMA cuga IS 'Schema for CUGA (Configurable Generalist Agent) integration with Suna';

COMMENT ON TABLE cuga.checkpoints IS 'LangGraph checkpoint storage for agent state persistence';
COMMENT ON TABLE cuga.checkpoint_writes IS 'Individual channel writes for debugging and replay';
COMMENT ON TABLE cuga.thread_metadata IS 'Maps CUGA thread_id to Suna account_id and project_id for multi-tenancy';
COMMENT ON TABLE cuga.thread_mappings IS 'Maps CUGA thread_id (TEXT) to Suna thread_id (UUID)';
COMMENT ON TABLE cuga.variables IS 'Optional global variables accessible across threads within an account/project';

COMMIT;

-- ============================================================================
-- Verification Queries
-- ============================================================================

-- Verify schema creation
-- SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'cuga';

-- Verify tables
-- SELECT table_name FROM information_schema.tables WHERE table_schema = 'cuga';

-- Verify RLS policies
-- SELECT tablename, policyname FROM pg_policies WHERE schemaname = 'cuga';
