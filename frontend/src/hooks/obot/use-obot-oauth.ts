'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { obotKeys } from './keys';
import { obotApi } from './api';

/**
 * Hook to get OAuth URL for a server
 */
export function useObotOAuthUrl(serverId: string | null, options?: { enabled?: boolean }) {
    return useQuery({
        queryKey: [...obotKeys.servers.detail(serverId || ''), 'oauth-url'],
        queryFn: async () => {
            const result = await obotApi.getOAuthUrl(serverId!);
            return result.oauth_url;
        },
        enabled: (options?.enabled ?? false) && !!serverId,
        staleTime: 0, // Always fetch fresh OAuth URLs
        gcTime: 0,
        retry: 1,
    });
}

/**
 * Hook to configure server environment variables
 */
export function useConfigureObotServer() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ serverId, env }: { serverId: string; env: Record<string, string> }) =>
            obotApi.configureServer(serverId, env),
        onSuccess: (_, { serverId }) => {
            queryClient.invalidateQueries({ queryKey: obotKeys.servers.detail(serverId) });
            queryClient.invalidateQueries({ queryKey: obotKeys.servers.status(serverId) });
            toast.success('Server configured successfully');
        },
        onError: (error: Error) => {
            console.error('Failed to configure server:', error);
            toast.error(error.message || 'Failed to configure server');
        },
    });
}

/**
 * Hook to launch/start a server
 */
export function useLaunchObotServer() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (serverId: string) => obotApi.launchServer(serverId),
        onSuccess: (_, serverId) => {
            queryClient.invalidateQueries({ queryKey: obotKeys.servers.detail(serverId) });
            queryClient.invalidateQueries({ queryKey: obotKeys.servers.status(serverId) });
            toast.success('Server launched successfully');
        },
        onError: (error: Error) => {
            console.error('Failed to launch server:', error);
            toast.error(error.message || 'Failed to launch server');
        },
    });
}
