/**
 * Query keys factory for Obot-related React Query hooks
 */
export const obotKeys = {
    all: ['obot'] as const,

    // Catalog
    catalog: {
        all: () => [...obotKeys.all, 'catalog'] as const,
        list: (search?: string) => [...obotKeys.catalog.all(), 'list', search || ''] as const,
        entry: (entryId: string) => [...obotKeys.catalog.all(), 'entry', entryId] as const,
    },

    // Servers
    servers: {
        all: () => [...obotKeys.all, 'servers'] as const,
        list: () => [...obotKeys.servers.all(), 'list'] as const,
        detail: (serverId: string) => [...obotKeys.servers.all(), 'detail', serverId] as const,
        tools: (serverId: string) => [...obotKeys.servers.all(), 'tools', serverId] as const,
        status: (serverId: string) => [...obotKeys.servers.all(), 'status', serverId] as const,
    },

    // Profiles
    profiles: {
        all: () => [...obotKeys.all, 'profiles'] as const,
        list: () => [...obotKeys.profiles.all(), 'list'] as const,
        detail: (profileId: string) => [...obotKeys.profiles.all(), 'detail', profileId] as const,
    },

    // Health
    health: () => [...obotKeys.all, 'health'] as const,
};
