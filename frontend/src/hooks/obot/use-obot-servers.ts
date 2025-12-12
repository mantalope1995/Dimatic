'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { obotKeys } from './keys';
import { obotApi } from './api';
import type { MCPServer, CreateMCPServerRequest } from './types';

/**
 * Hook to list user's MCP servers
 */
export function useObotServers(options?: { enabled?: boolean }) {
    return useQuery({
        queryKey: obotKeys.servers.list(),
        queryFn: obotApi.listServers,
        enabled: options?.enabled ?? true,
        staleTime: 2 * 60 * 1000, // 2 minutes
        retry: 2,
    });
}

/**
 * Hook to get a specific server's details
 */
export function useObotServer(serverId: string | null, options?: { enabled?: boolean }) {
    return useQuery({
        queryKey: obotKeys.servers.detail(serverId || ''),
        queryFn: () => obotApi.getServer(serverId!),
        enabled: (options?.enabled ?? true) && !!serverId,
        staleTime: 2 * 60 * 1000,
        retry: 2,
    });
}

/**
 * Hook to create a new MCP server from catalog entry
 */
export function useCreateObotServer() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (request: CreateMCPServerRequest) => obotApi.createServer(request),
        onSuccess: (server) => {
            queryClient.invalidateQueries({ queryKey: obotKeys.servers.all() });
            queryClient.invalidateQueries({ queryKey: obotKeys.profiles.all() });
            toast.success(`Server "${server.name}" created successfully`);
        },
        onError: (error: Error) => {
            console.error('Failed to create server:', error);
            toast.error(error.message || 'Failed to create server');
        },
    });
}

/**
 * Hook to delete an MCP server
 */
export function useDeleteObotServer() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (serverId: string) => obotApi.deleteServer(serverId),
        onSuccess: (_, serverId) => {
            queryClient.invalidateQueries({ queryKey: obotKeys.servers.all() });
            queryClient.invalidateQueries({ queryKey: obotKeys.profiles.all() });
            queryClient.removeQueries({ queryKey: obotKeys.servers.detail(serverId) });
            toast.success('Server deleted successfully');
        },
        onError: (error: Error) => {
            console.error('Failed to delete server:', error);
            toast.error(error.message || 'Failed to delete server');
        },
    });
}

/**
 * Hook to get server status
 */
export function useObotServerStatus(serverId: string | null, options?: { enabled?: boolean; refetchInterval?: number }) {
    return useQuery({
        queryKey: obotKeys.servers.status(serverId || ''),
        queryFn: () => obotApi.getServerStatus(serverId!),
        enabled: (options?.enabled ?? true) && !!serverId,
        staleTime: 10 * 1000, // 10 seconds
        refetchInterval: options?.refetchInterval,
        retry: 1,
    });
}
