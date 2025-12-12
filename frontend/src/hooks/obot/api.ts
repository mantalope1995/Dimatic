/**
 * Obot API client functions
 */
import { createClient } from '@/lib/supabase/client';
import type {
    MCPCatalogEntry,
    MCPServer,
    MCPTool,
    ObotProfile,
    CreateMCPServerRequest,
    ToolCallResponse,
    ObotHealthResponse,
} from './types';

const API_BASE = `${process.env.NEXT_PUBLIC_BACKEND_URL}/obot`;

async function getAuthHeaders(): Promise<HeadersInit> {
    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();

    if (!session) {
        throw new Error('You must be logged in');
    }

    return {
        'Authorization': `Bearer ${session.access_token}`,
        'Content-Type': 'application/json',
    };
}

async function handleResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
        const errorData = await response.json().catch(() => ({ message: 'Unknown error' }));
        throw new Error(errorData.detail || errorData.message || `HTTP ${response.status}: ${response.statusText}`);
    }
    return response.json();
}

// === Catalog API ===
export async function listCatalogEntries(): Promise<MCPCatalogEntry[]> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE}/catalog`, { headers });
    return handleResponse<MCPCatalogEntry[]>(response);
}

export async function getCatalogEntry(entryId: string): Promise<MCPCatalogEntry> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE}/catalog/${encodeURIComponent(entryId)}`, { headers });
    return handleResponse<MCPCatalogEntry>(response);
}

// === Server API ===
export async function listServers(): Promise<MCPServer[]> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE}/servers`, { headers });
    return handleResponse<MCPServer[]>(response);
}

export async function getServer(serverId: string): Promise<MCPServer> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE}/servers/${encodeURIComponent(serverId)}`, { headers });
    return handleResponse<MCPServer>(response);
}

export async function createServer(request: CreateMCPServerRequest): Promise<MCPServer> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE}/servers`, {
        method: 'POST',
        headers,
        body: JSON.stringify(request),
    });
    return handleResponse<MCPServer>(response);
}

export async function deleteServer(serverId: string): Promise<void> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE}/servers/${encodeURIComponent(serverId)}`, {
        method: 'DELETE',
        headers,
    });
    if (!response.ok) {
        const errorData = await response.json().catch(() => ({ message: 'Unknown error' }));
        throw new Error(errorData.detail || errorData.message || `HTTP ${response.status}`);
    }
}

// === Tool API ===
export async function listServerTools(serverId: string): Promise<MCPTool[]> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE}/servers/${encodeURIComponent(serverId)}/tools`, { headers });
    return handleResponse<MCPTool[]>(response);
}

export async function setServerTools(serverId: string, toolNames: string[]): Promise<void> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE}/servers/${encodeURIComponent(serverId)}/tools`, {
        method: 'PUT',
        headers,
        body: JSON.stringify(toolNames),
    });
    if (!response.ok) {
        const errorData = await response.json().catch(() => ({ message: 'Unknown error' }));
        throw new Error(errorData.detail || errorData.message || `HTTP ${response.status}`);
    }
}

export async function callServerTool(
    serverId: string,
    toolName: string,
    args: Record<string, unknown>
): Promise<ToolCallResponse> {
    const headers = await getAuthHeaders();
    const response = await fetch(
        `${API_BASE}/servers/${encodeURIComponent(serverId)}/tools/${encodeURIComponent(toolName)}/call`,
        {
            method: 'POST',
            headers,
            body: JSON.stringify(args),
        }
    );
    return handleResponse<ToolCallResponse>(response);
}

// === OAuth & Configuration API ===
export async function getOAuthUrl(serverId: string): Promise<{ oauth_url: string }> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE}/servers/${encodeURIComponent(serverId)}/oauth-url`, { headers });
    return handleResponse<{ oauth_url: string }>(response);
}

export async function configureServer(serverId: string, env: Record<string, string>): Promise<void> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE}/servers/${encodeURIComponent(serverId)}/configure`, {
        method: 'POST',
        headers,
        body: JSON.stringify(env),
    });
    if (!response.ok) {
        const errorData = await response.json().catch(() => ({ message: 'Unknown error' }));
        throw new Error(errorData.detail || errorData.message || `HTTP ${response.status}`);
    }
}

export async function launchServer(serverId: string): Promise<void> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE}/servers/${encodeURIComponent(serverId)}/launch`, {
        method: 'POST',
        headers,
    });
    if (!response.ok) {
        const errorData = await response.json().catch(() => ({ message: 'Unknown error' }));
        throw new Error(errorData.detail || errorData.message || `HTTP ${response.status}`);
    }
}

export async function getServerStatus(serverId: string): Promise<MCPServer> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE}/servers/${encodeURIComponent(serverId)}/status`, { headers });
    return handleResponse<MCPServer>(response);
}

// === Health API ===
export async function checkHealth(): Promise<ObotHealthResponse> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE}/health`, { headers });
    return handleResponse<ObotHealthResponse>(response);
}

// === Profile API (uses profile_service.py) ===
// Note: These may need adjustment based on actual backend routes
export async function listProfiles(): Promise<ObotProfile[]> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE}/profiles`, { headers });
    return handleResponse<ObotProfile[]>(response);
}

export async function getProfile(profileId: string): Promise<ObotProfile> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE}/profiles/${encodeURIComponent(profileId)}`, { headers });
    return handleResponse<ObotProfile>(response);
}

export async function deleteProfile(profileId: string): Promise<void> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE}/profiles/${encodeURIComponent(profileId)}`, {
        method: 'DELETE',
        headers,
    });
    if (!response.ok) {
        const errorData = await response.json().catch(() => ({ message: 'Unknown error' }));
        throw new Error(errorData.detail || errorData.message || `HTTP ${response.status}`);
    }
}

// Export all API functions as a single object for convenience
export const obotApi = {
    // Catalog
    listCatalogEntries,
    getCatalogEntry,
    // Servers
    listServers,
    getServer,
    createServer,
    deleteServer,
    // Tools
    listServerTools,
    setServerTools,
    callServerTool,
    // OAuth & Config
    getOAuthUrl,
    configureServer,
    launchServer,
    getServerStatus,
    // Health
    checkHealth,
    // Profiles
    listProfiles,
    getProfile,
    deleteProfile,
};
