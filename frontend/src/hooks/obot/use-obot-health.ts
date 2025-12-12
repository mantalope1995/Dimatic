'use client';

import { useQuery } from '@tanstack/react-query';
import { obotKeys } from './keys';
import { obotApi } from './api';

/**
 * Hook to check Obot service health
 */
export function useObotHealth(options?: { enabled?: boolean; refetchInterval?: number }) {
    return useQuery({
        queryKey: obotKeys.health(),
        queryFn: obotApi.checkHealth,
        enabled: options?.enabled ?? true,
        staleTime: 30 * 1000, // 30 seconds
        refetchInterval: options?.refetchInterval,
        retry: 1,
    });
}

/**
 * Hook to check if Obot service is available
 */
export function useIsObotAvailable() {
    const { data, isLoading, error } = useObotHealth({ enabled: true });
    return {
        isAvailable: !error && data?.status === 'healthy',
        isLoading,
        error,
    };
}
