-- =====================================================
-- AGENTCORE RUNTIME DEPLOYMENT TRACKING
-- =====================================================
-- This migration adds AgentCore Runtime deployment tracking
-- to the agent_versions table. This enables tracking the
-- deployment status of agents to AWS Bedrock AgentCore Runtime.
--
-- Phase 1: Serverless agent execution in ap-southeast-2 region
-- =====================================================

BEGIN;

-- Add deployment tracking columns to agent_versions
ALTER TABLE agent_versions ADD COLUMN IF NOT EXISTS deployment_id TEXT;
ALTER TABLE agent_versions ADD COLUMN IF NOT EXISTS deployment_status VARCHAR(50) DEFAULT 'pending';
ALTER TABLE agent_versions ADD COLUMN IF NOT EXISTS deployed_at TIMESTAMPTZ;
ALTER TABLE agent_versions ADD COLUMN IF NOT EXISTS deployment_metadata JSONB DEFAULT '{}'::jsonb;

-- Add comment to columns
COMMENT ON COLUMN agent_versions.deployment_id IS 'AWS Bedrock AgentCore Runtime deployment identifier';
COMMENT ON COLUMN agent_versions.deployment_status IS 'Current deployment status: pending, deploying, deployed, failed, rolled_back';
COMMENT ON COLUMN agent_versions.deployed_at IS 'Timestamp when deployment was completed';
COMMENT ON COLUMN agent_versions.deployment_metadata IS 'Additional deployment metadata (ARN, region, etc.)';

-- Create indexes for deployment queries
CREATE INDEX IF NOT EXISTS idx_agent_versions_deployment_id ON agent_versions(deployment_id);
CREATE INDEX IF NOT EXISTS idx_agent_versions_deployment_status ON agent_versions(deployment_status);
CREATE INDEX IF NOT EXISTS idx_agent_versions_deployed_at ON agent_versions(deployed_at);

-- =====================================================
-- HELPER FUNCTIONS
-- =====================================================

-- Function to update deployment status
CREATE OR REPLACE FUNCTION update_deployment_status(
    p_version_id UUID,
    p_deployment_id TEXT,
    p_deployment_status VARCHAR(50),
    p_deployment_metadata JSONB DEFAULT '{}'::jsonb
)
RETURNS void
SECURITY DEFINER
LANGUAGE plpgsql
AS $$
BEGIN
    -- Update agent version deployment status
    UPDATE agent_versions
    SET
        deployment_id = p_deployment_id,
        deployment_status = p_deployment_status,
        deployment_metadata = p_deployment_metadata,
        deployed_at = CASE
            WHEN p_deployment_status = 'deployed' THEN NOW()
            ELSE deployed_at
        END,
        updated_at = NOW()
    WHERE version_id = p_version_id;

    -- Log to history if deployment status changed
    IF FOUND THEN
        INSERT INTO agent_version_history (
            agent_id,
            version_id,
            action,
            changed_by,
            change_description
        )
        SELECT
            av.agent_id,
            p_version_id,
            'deployment_' || p_deployment_status,
            av.created_by,
            'Deployment status updated to ' || p_deployment_status ||
            CASE
                WHEN p_deployment_id IS NOT NULL THEN ' (deployment_id: ' || p_deployment_id || ')'
                ELSE ''
            END
        FROM agent_versions av
        WHERE av.version_id = p_version_id;
    END IF;
END;
$$;

-- Function to mark deployment as started
CREATE OR REPLACE FUNCTION mark_deployment_started(
    p_version_id UUID,
    p_deployment_id TEXT
)
RETURNS void
SECURITY DEFINER
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE agent_versions
    SET
        deployment_id = p_deployment_id,
        deployment_status = 'deploying',
        updated_at = NOW()
    WHERE version_id = p_version_id;
END;
$$;

-- Function to mark deployment as completed
CREATE OR REPLACE FUNCTION mark_deployment_completed(
    p_version_id UUID,
    p_deployment_arn TEXT DEFAULT NULL,
    p_metadata JSONB DEFAULT '{}'::jsonb
)
RETURNS void
SECURITY DEFINER
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE agent_versions
    SET
        deployment_status = 'deployed',
        deployed_at = NOW(),
        deployment_metadata = COALESCE(
            agent_versions.deployment_metadata::jsonb ||
            jsonb_build_object(
                'deployment_arn', p_deployment_arn,
                'completed_at', NOW()
            ) || p_metadata,
            agent_versions.deployment_metadata
        ),
        updated_at = NOW()
    WHERE version_id = p_version_id;

    -- Log to history
    INSERT INTO agent_version_history (
        agent_id,
        version_id,
        action,
        changed_by,
        change_description
    )
    SELECT
        av.agent_id,
        p_version_id,
        'deployment_completed',
        av.created_by,
        'Agent deployment completed successfully' ||
        CASE
            WHEN p_deployment_arn IS NOT NULL THEN ' (ARN: ' || p_deployment_arn || ')'
            ELSE ''
        END
    FROM agent_versions av
    WHERE av.version_id = p_version_id;
END;
$$;

-- Function to mark deployment as failed
CREATE OR REPLACE FUNCTION mark_deployment_failed(
    p_version_id UUID,
    p_error_message TEXT DEFAULT NULL,
    p_metadata JSONB DEFAULT '{}'::jsonb
)
RETURNS void
SECURITY DEFINER
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE agent_versions
    SET
        deployment_status = 'failed',
        deployment_metadata = COALESCE(
            agent_versions.deployment_metadata::jsonb ||
            jsonb_build_object(
                'error_message', p_error_message,
                'failed_at', NOW()
            ) || p_metadata,
            agent_versions.deployment_metadata
        ),
        updated_at = NOW()
    WHERE version_id = p_version_id;

    -- Log to history
    INSERT INTO agent_version_history (
        agent_id,
        version_id,
        action,
        changed_by,
        change_description
    )
    SELECT
        av.agent_id,
        p_version_id,
        'deployment_failed',
        av.created_by,
        'Agent deployment failed' ||
        CASE
            WHEN p_error_message IS NOT NULL THEN ': ' || p_error_message
            ELSE ''
        END
    FROM agent_versions av
    WHERE av.version_id = p_version_id;
END;
$$;

-- Function to mark deployment as rolled back
CREATE OR REPLACE FUNCTION mark_deployment_rolled_back(
    p_version_id UUID,
    p_previous_deployment_id TEXT DEFAULT NULL,
    p_metadata JSONB DEFAULT '{}'::jsonb
)
RETURNS void
SECURITY DEFINER
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE agent_versions
    SET
        deployment_status = 'rolled_back',
        deployment_metadata = COALESCE(
            agent_versions.deployment_metadata::jsonb ||
            jsonb_build_object(
                'rolled_back_to', p_previous_deployment_id,
                'rolled_back_at', NOW()
            ) || p_metadata,
            agent_versions.deployment_metadata
        ),
        updated_at = NOW()
    WHERE version_id = p_version_id;

    -- Log to history
    INSERT INTO agent_version_history (
        agent_id,
        version_id,
        action,
        changed_by,
        change_description
    )
    SELECT
        av.agent_id,
        p_version_id,
        'deployment_rolled_back',
        av.created_by,
        'Agent deployment rolled back' ||
        CASE
            WHEN p_previous_deployment_id IS NOT NULL THEN ' to ' || p_previous_deployment_id
            ELSE ''
        END
    FROM agent_versions av
    WHERE av.version_id = p_version_id;
END;
$$;

-- Function to get active deployment for an agent
CREATE OR REPLACE FUNCTION get_agent_deployment(
    p_agent_id UUID
)
RETURNS TABLE (
    version_id UUID,
    deployment_id TEXT,
    deployment_status VARCHAR(50),
    deployed_at TIMESTAMPTZ,
    deployment_metadata JSONB
)
SECURITY DEFINER
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        av.version_id,
        av.deployment_id,
        av.deployment_status,
        av.deployed_at,
        av.deployment_metadata
    FROM agent_versions av
    WHERE av.agent_id = p_agent_id
        AND av.is_active = TRUE
    ORDER BY av.created_at DESC
    LIMIT 1;
END;
$$;

-- =====================================================
-- TRIGGER FOR DEPLOYMENT STATUS CHANGES
-- =====================================================

-- Function to log deployment status changes to history
CREATE OR REPLACE FUNCTION log_deployment_status_change()
RETURNS TRIGGER
SECURITY DEFINER
LANGUAGE plpgsql
AS $$
BEGIN
    -- Only log if deployment_status actually changed
    IF (OLD.deployment_status IS DISTINCT FROM NEW.deployment_status) AND
       (NEW.deployment_status IS NOT NULL) THEN
        INSERT INTO agent_version_history (
            agent_id,
            version_id,
            action,
            changed_by,
            change_description
        )
        VALUES (
            NEW.agent_id,
            NEW.version_id,
            'deployment_status_changed',
            NEW.created_by,
            'Deployment status changed from ' ||
            COALESCE(OLD.deployment_status, 'none') ||
            ' to ' || NEW.deployment_status
        );
    END IF;

    RETURN NEW;
END;
$$;

-- Create trigger
DROP TRIGGER IF EXISTS trigger_deployment_status_change ON agent_versions;
CREATE TRIGGER trigger_deployment_status_change
    AFTER UPDATE OF deployment_status ON agent_versions
    FOR EACH ROW
    EXECUTE FUNCTION log_deployment_status_change();

-- =====================================================
-- VIEWS FOR DEPLOYMENT MONITORING
-- =====================================================

-- View for pending deployments
CREATE OR REPLACE VIEW pending_agent_deployments AS
SELECT
    av.version_id,
    av.agent_id,
    av.version_number,
    av.version_name,
    av.deployment_id,
    av.deployment_status,
    av.created_at,
    a.name as agent_name,
    acc.email as created_by_email
FROM agent_versions av
JOIN agents a ON av.agent_id = a.agent_id
LEFT JOIN basejump.accounts acc ON av.created_by = acc.id
WHERE av.deployment_status IN ('pending', 'deploying')
ORDER BY av.created_at ASC;

-- View for failed deployments
CREATE OR REPLACE VIEW failed_agent_deployments AS
SELECT
    av.version_id,
    av.agent_id,
    av.version_number,
    av.version_name,
    av.deployment_id,
    av.deployment_metadata->>'error_message' as error_message,
    av.created_at,
    a.name as agent_name,
    acc.email as created_by_email
FROM agent_versions av
JOIN agents a ON av.agent_id = a.agent_id
LEFT JOIN basejump.accounts acc ON av.created_by = acc.id
WHERE av.deployment_status = 'failed'
ORDER BY av.created_at DESC;

-- View for deployment statistics
CREATE OR REPLACE VIEW agent_deployment_stats AS
SELECT
    a.agent_id,
    a.name as agent_name,
    COUNT(*) as total_versions,
    SUM(CASE WHEN av.deployment_status = 'deployed' THEN 1 ELSE 0 END) as deployed_count,
    SUM(CASE WHEN av.deployment_status = 'failed' THEN 1 ELSE 0 END) as failed_count,
    SUM(CASE WHEN av.deployment_status = 'pending' THEN 1 ELSE 0 END) as pending_count,
    MAX(av.deployed_at) as last_deployed_at
FROM agents a
LEFT JOIN agent_versions av ON a.agent_id = av.agent_id
GROUP BY a.agent_id, a.name
ORDER BY a.name;

COMMIT;

-- =====================================================
-- VERIFICATION QUERIES
-- =====================================================
-- Run these after migration to verify:

-- Check columns were added
-- SELECT column_name, data_type, column_default
-- FROM information_schema.columns
-- WHERE table_name = 'agent_versions'
-- AND column_name LIKE '%deployment%';

-- Check indexes were created
-- SELECT indexname, indexdef
-- FROM pg_indexes
-- WHERE tablename = 'agent_versions'
-- AND indexname LIKE '%deployment%';

-- Check functions were created
-- SELECT routine_name, routine_type
-- FROM information_schema.routines
-- WHERE routine_schema = 'public'
-- AND routine_name LIKE '%deployment%';

-- Check views were created
-- SELECT table_name, view_definition
-- FROM information_schema.views
-- WHERE table_name LIKE '%deployment%';
