'use client';

import { useQuery } from '@tanstack/react-query';
import { obotKeys } from './keys';
import { obotApi } from './api';
import type { MCPCatalogEntry } from './types';

/**
 * Hook to list all MCP catalog entries
 * Replaces: useComposioToolkits
 */
export function useObotCatalog(options?: { enabled?: boolean }) {
    return useQuery({
        queryKey: obotKeys.catalog.list(),
        queryFn: obotApi.listCatalogEntries,
        enabled: options?.enabled ?? true,
        staleTime: 5 * 60 * 1000, // 5 minutes
        retry: 2,
    });
}

/**
 * Hook to get a specific catalog entry details
 * Replaces: useComposioToolkitDetails
 */
export function useObotCatalogEntry(entryId: string | null, options?: { enabled?: boolean }) {
    return useQuery({
        queryKey: obotKeys.catalog.entry(entryId || ''),
        queryFn: () => obotApi.getCatalogEntry(entryId!),
        enabled: (options?.enabled ?? true) && !!entryId,
        staleTime: 10 * 60 * 1000, // 10 minutes
        retry: 2,
    });
}

/**
 * Helper hook to get icon URL from catalog entry
 * Replaces: useComposioToolkitIcon
 */
export function useObotCatalogEntryIcon(entryId: string | null, options?: { enabled?: boolean }) {
    const { data: entry, isLoading, error } = useObotCatalogEntry(entryId, options);

    return {
        data: entry?.icon ? { success: true, icon_url: entry.icon } : { success: false },
        isLoading,
        error,
    };
}
