-- ============================================================================
-- Obot Integration Tables
-- ============================================================================
-- Migration: 20251212000000_obot_integration.sql
-- Description: Creates tables for Obot MCP Gateway integration
-- Requirements: 7.1, 7.2, 8.1 (Database schema and RLS)
-- ============================================================================

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- Table: obot_user_mappings
-- Purpose: Maps Suna user IDs to Obot user identities
-- Requirements: 2.1, 2.2, 2.3 (User identity mapping)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.obot_user_mappings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    suna_user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    obot_user_id VARCHAR(255) NOT NULL,
    obot_username VARCHAR(255) NOT NULL,
    -- Encrypted token cache to avoid repeated API calls
    -- Encrypted using Fernet with OBOT_TOKEN_ENCRYPTION_KEY
    encrypted_token TEXT,
    token_expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    
    -- Constraints
    CONSTRAINT obot_user_mappings_suna_user_unique UNIQUE(suna_user_id),
    CONSTRAINT obot_user_mappings_obot_user_unique UNIQUE(obot_user_id)
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_obot_user_mappings_suna_user 
    ON public.obot_user_mappings(suna_user_id);
CREATE INDEX IF NOT EXISTS idx_obot_user_mappings_obot_user 
    ON public.obot_user_mappings(obot_user_id);
CREATE INDEX IF NOT EXISTS idx_obot_user_mappings_token_expires 
    ON public.obot_user_mappings(token_expires_at);

-- Enable RLS
ALTER TABLE public.obot_user_mappings ENABLE ROW LEVEL SECURITY;

-- RLS Policies: Users can only access their own mapping
CREATE POLICY "obot_user_mappings_select_own" 
    ON public.obot_user_mappings 
    FOR SELECT 
    USING (suna_user_id = auth.uid());

CREATE POLICY "obot_user_mappings_insert_own" 
    ON public.obot_user_mappings 
    FOR INSERT 
    WITH CHECK (suna_user_id = auth.uid());

CREATE POLICY "obot_user_mappings_update_own" 
    ON public.obot_user_mappings 
    FOR UPDATE 
    USING (suna_user_id = auth.uid())
    WITH CHECK (suna_user_id = auth.uid());

CREATE POLICY "obot_user_mappings_delete_own" 
    ON public.obot_user_mappings 
    FOR DELETE 
    USING (suna_user_id = auth.uid());

-- Trigger for updated_at
CREATE OR REPLACE FUNCTION public.update_obot_mapping_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER obot_user_mappings_updated
    BEFORE UPDATE ON public.obot_user_mappings
    FOR EACH ROW
    EXECUTE FUNCTION public.update_obot_mapping_timestamp();


-- ============================================================================
-- Table: obot_profiles
-- Purpose: Stores user's MCP server connection profiles
-- Requirements: 4.1, 4.2, 4.3, 7.2, 7.3 (Profile management)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.obot_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    obot_server_id VARCHAR(255) NOT NULL,
    catalog_entry_id VARCHAR(255) NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    icon_url TEXT,
    -- Status: 'pending', 'connected', 'error', 'oauth_required', 'configuring'
    status VARCHAR(50) DEFAULT 'pending' NOT NULL,
    -- Additional metadata
    last_error TEXT,
    last_connected_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    
    -- Constraints
    CONSTRAINT obot_profiles_server_unique UNIQUE(account_id, obot_server_id)
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_obot_profiles_account 
    ON public.obot_profiles(account_id);
CREATE INDEX IF NOT EXISTS idx_obot_profiles_server 
    ON public.obot_profiles(obot_server_id);
CREATE INDEX IF NOT EXISTS idx_obot_profiles_catalog 
    ON public.obot_profiles(catalog_entry_id);
CREATE INDEX IF NOT EXISTS idx_obot_profiles_status 
    ON public.obot_profiles(status);
CREATE INDEX IF NOT EXISTS idx_obot_profiles_created 
    ON public.obot_profiles(created_at DESC);

-- Enable RLS
ALTER TABLE public.obot_profiles ENABLE ROW LEVEL SECURITY;

-- RLS Policies: Users can only access their own profiles
CREATE POLICY "obot_profiles_select_own" 
    ON public.obot_profiles 
    FOR SELECT 
    USING (account_id = auth.uid());

CREATE POLICY "obot_profiles_insert_own" 
    ON public.obot_profiles 
    FOR INSERT 
    WITH CHECK (account_id = auth.uid());

CREATE POLICY "obot_profiles_update_own" 
    ON public.obot_profiles 
    FOR UPDATE 
    USING (account_id = auth.uid())
    WITH CHECK (account_id = auth.uid());

CREATE POLICY "obot_profiles_delete_own" 
    ON public.obot_profiles 
    FOR DELETE 
    USING (account_id = auth.uid());

-- Trigger for updated_at
CREATE TRIGGER obot_profiles_updated
    BEFORE UPDATE ON public.obot_profiles
    FOR EACH ROW
    EXECUTE FUNCTION public.update_obot_mapping_timestamp();


-- ============================================================================
-- Table: obot_audit_logs
-- Purpose: Records all MCP operations for compliance and debugging
-- Requirements: 8.4 (Audit logging)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.obot_audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    -- Action types: 'server_create', 'server_delete', 'server_update', 
    --               'tool_call', 'oauth_start', 'oauth_complete', 
    --               'admin_proxy_access'
    action VARCHAR(50) NOT NULL,
    server_id VARCHAR(255),
    tool_name VARCHAR(255),
    success BOOLEAN NOT NULL DEFAULT true,
    error_message TEXT,
    -- Request context
    ip_address INET,
    user_agent TEXT,
    -- Additional context as JSONB
    additional_context JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

-- Indexes for querying audit logs
CREATE INDEX IF NOT EXISTS idx_obot_audit_logs_user 
    ON public.obot_audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_obot_audit_logs_action 
    ON public.obot_audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_obot_audit_logs_server 
    ON public.obot_audit_logs(server_id);
CREATE INDEX IF NOT EXISTS idx_obot_audit_logs_created 
    ON public.obot_audit_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_obot_audit_logs_success 
    ON public.obot_audit_logs(success);
-- Combined index for common query pattern
CREATE INDEX IF NOT EXISTS idx_obot_audit_logs_user_created 
    ON public.obot_audit_logs(user_id, created_at DESC);

-- Enable RLS
ALTER TABLE public.obot_audit_logs ENABLE ROW LEVEL SECURITY;

-- RLS Policies: Users can only see their own audit logs
-- Admins can see all (handled via service role key in backend)
CREATE POLICY "obot_audit_logs_select_own" 
    ON public.obot_audit_logs 
    FOR SELECT 
    USING (user_id = auth.uid());

-- Insert is typically done by service role, but allow users to insert their own
CREATE POLICY "obot_audit_logs_insert_own" 
    ON public.obot_audit_logs 
    FOR INSERT 
    WITH CHECK (user_id = auth.uid());

-- No update or delete policies - audit logs are immutable
-- Service role can bypass RLS if needed for admin operations


-- ============================================================================
-- Function: get_obot_audit_summary
-- Purpose: Get audit statistics for a user over a time period
-- ============================================================================
CREATE OR REPLACE FUNCTION public.get_obot_audit_summary(
    p_user_id UUID,
    p_days INTEGER DEFAULT 30
)
RETURNS JSONB AS $$
DECLARE
    v_result JSONB;
    v_start_date TIMESTAMP WITH TIME ZONE;
    v_total INTEGER;
    v_success INTEGER;
    v_failed INTEGER;
BEGIN
    v_start_date := NOW() - (p_days || ' days')::INTERVAL;
    
    SELECT 
        COUNT(*),
        COUNT(*) FILTER (WHERE success = true),
        COUNT(*) FILTER (WHERE success = false)
    INTO v_total, v_success, v_failed
    FROM public.obot_audit_logs
    WHERE user_id = p_user_id
      AND created_at >= v_start_date;
    
    v_result := jsonb_build_object(
        'user_id', p_user_id,
        'period_days', p_days,
        'period_start', v_start_date,
        'period_end', NOW(),
        'total_operations', v_total,
        'successful_operations', v_success,
        'failed_operations', v_failed,
        'success_rate', CASE WHEN v_total > 0 THEN (v_success::NUMERIC / v_total * 100) ELSE 0 END
    );
    
    RETURN v_result;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Grant execute permissions
GRANT EXECUTE ON FUNCTION public.get_obot_audit_summary(UUID, INTEGER) TO authenticated;


-- ============================================================================
-- Comment migrations for documentation
-- ============================================================================
COMMENT ON TABLE public.obot_user_mappings IS 
    'Maps Suna users to Obot user identities for MCP Gateway integration';
COMMENT ON TABLE public.obot_profiles IS 
    'Stores user MCP server connection profiles for the Obot integration';
COMMENT ON TABLE public.obot_audit_logs IS 
    'Immutable audit log of all MCP operations for compliance and debugging';
COMMENT ON FUNCTION public.get_obot_audit_summary IS 
    'Returns audit statistics for a user over a specified time period';
