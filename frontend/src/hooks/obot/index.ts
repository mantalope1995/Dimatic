/**
 * Obot MCP Gateway hooks
 * 
 * This module provides React Query hooks for interacting with the Obot MCP Gateway API.
 * It replaces the deprecated Composio hooks.
 */

// Query keys
export { obotKeys } from './keys';

// Types
export type {
    MCPCatalogEntry,
    MCPCatalogEntryManifest,
    MCPServer,
    MCPTool,
    MCPResource,
    MCPPrompt,
    ObotProfile,
    CreateMCPServerRequest,
    UpdateMCPServerRequest,
    ToolCallRequest,
    ToolCallResponse,
    ObotHealthResponse,
} from './types';

// API client
export { obotApi } from './api';

// Catalog hooks
export {
    useObotCatalog,
    useObotCatalogEntry,
    useObotCatalogEntryIcon,
} from './use-obot-catalog';

// Server hooks
export {
    useObotServers,
    useObotServer,
    useCreateObotServer,
    useDeleteObotServer,
    useObotServerStatus,
} from './use-obot-servers';

// Tool hooks
export {
    useObotServerTools,
    useSetObotServerTools,
    useCallObotTool,
} from './use-obot-tools';

// Profile hooks
export {
    useObotProfiles,
    useObotProfile,
    useDeleteObotProfile,
    useHasObotProfiles,
    useInvalidateObotQueries,
} from './use-obot-profiles';

// OAuth hooks
export {
    useObotOAuthUrl,
    useConfigureObotServer,
    useLaunchObotServer,
} from './use-obot-oauth';

// Health hooks
export {
    useObotHealth,
    useIsObotAvailable,
} from './use-obot-health';
