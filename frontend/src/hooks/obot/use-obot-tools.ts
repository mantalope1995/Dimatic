'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { obotKeys } from './keys';
import { obotApi } from './api';
import type { MCPTool } from './types';

/**
 * Hook to list tools for a server
 * Replaces: useComposioTools
 */
export function useObotServerTools(serverId: string | null, options?: { enabled?: boolean }) {
    return useQuery({
        queryKey: obotKeys.servers.tools(serverId || ''),
        queryFn: () => obotApi.listServerTools(serverId!),
        enabled: (options?.enabled ?? true) && !!serverId,
        staleTime: 5 * 60 * 1000, // 5 minutes
        retry: 2,
    });
}

/**
 * Hook to set enabled tools for a server
 */
export function useSetObotServerTools() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ serverId, toolNames }: { serverId: string; toolNames: string[] }) =>
            obotApi.setServerTools(serverId, toolNames),
        onSuccess: (_, { serverId }) => {
            queryClient.invalidateQueries({ queryKey: obotKeys.servers.tools(serverId) });
            toast.success('Tools updated successfully');
        },
        onError: (error: Error) => {
            console.error('Failed to update tools:', error);
            toast.error(error.message || 'Failed to update tools');
        },
    });
}

/**
 * Hook to call/execute a tool
 */
export function useCallObotTool() {
    return useMutation({
        mutationFn: ({
            serverId,
            toolName,
            args
        }: {
            serverId: string;
            toolName: string;
            args: Record<string, unknown>;
        }) => obotApi.callServerTool(serverId, toolName, args),
        onError: (error: Error) => {
            console.error('Tool execution failed:', error);
            toast.error(error.message || 'Tool execution failed');
        },
    });
}
