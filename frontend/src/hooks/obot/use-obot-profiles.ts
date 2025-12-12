'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { obotKeys } from './keys';
import { obotApi } from './api';
import type { ObotProfile } from './types';

/**
 * Hook to list user's Obot profiles
 * Replaces: useComposioProfiles, useCredentialProfiles
 */
export function useObotProfiles(options?: { enabled?: boolean }) {
    return useQuery({
        queryKey: obotKeys.profiles.list(),
        queryFn: obotApi.listProfiles,
        enabled: options?.enabled ?? true,
        staleTime: 2 * 60 * 1000, // 2 minutes
        retry: 2,
    });
}

/**
 * Hook to get a specific profile
 */
export function useObotProfile(profileId: string | null, options?: { enabled?: boolean }) {
    return useQuery({
        queryKey: obotKeys.profiles.detail(profileId || ''),
        queryFn: () => obotApi.getProfile(profileId!),
        enabled: (options?.enabled ?? true) && !!profileId,
        staleTime: 5 * 60 * 1000,
        retry: 2,
    });
}

/**
 * Hook to delete an Obot profile
 * Replaces: useDeleteProfile
 */
export function useDeleteObotProfile() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (profileId: string) => obotApi.deleteProfile(profileId),
        onSuccess: (_, profileId) => {
            queryClient.invalidateQueries({ queryKey: obotKeys.profiles.all() });
            queryClient.invalidateQueries({ queryKey: obotKeys.servers.all() });
            queryClient.removeQueries({ queryKey: obotKeys.profiles.detail(profileId) });
            toast.success('Profile deleted successfully');
        },
        onError: (error: Error) => {
            console.error('Failed to delete profile:', error);
            toast.error(error.message || 'Failed to delete profile');
        },
    });
}

/**
 * Hook to check if user has any profiles
 */
export function useHasObotProfiles() {
    const { data: profiles, isLoading } = useObotProfiles();
    return {
        hasProfiles: (profiles?.length || 0) > 0,
        profileCount: profiles?.length || 0,
        isLoading,
    };
}

/**
 * Hook to invalidate all Obot-related queries
 */
export function useInvalidateObotQueries() {
    const queryClient = useQueryClient();

    return () => {
        queryClient.invalidateQueries({ queryKey: obotKeys.all });
    };
}
