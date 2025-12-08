import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as fc from 'fast-check';
import { middleware } from './middleware';
import { NextRequest, NextResponse } from 'next/server';

// Mock Supabase client
vi.mock('@supabase/ssr', () => ({
  createServerClient: vi.fn(() => ({
    auth: {
      getUser: vi.fn(),
    },
    schema: vi.fn(() => ({
      from: vi.fn(() => ({
        select: vi.fn(() => ({
          eq: vi.fn(() => ({
            eq: vi.fn(() => ({
              single: vi.fn(),
            })),
            single: vi.fn(),
          })),
        })),
      })),
    })),
    from: vi.fn(() => ({
      select: vi.fn(() => ({
        eq: vi.fn(() => ({
          single: vi.fn(),
        })),
      })),
    })),
  })),
}));

// Helper to create a mock NextRequest
function createMockRequest(pathname: string, searchParams?: Record<string, string>, cookies?: Record<string, string>): NextRequest {
  const url = new URL(pathname, 'http://localhost:3000');
  
  if (searchParams) {
    Object.entries(searchParams).forEach(([key, value]) => {
      url.searchParams.set(key, value);
    });
  }
  
  const request = new NextRequest(url);
  
  if (cookies) {
    Object.entries(cookies).forEach(([key, value]) => {
      request.cookies.set(key, value);
    });
  }
  
  return request;
}

// Helper to mock authenticated user
function mockAuthenticatedUser() {
  const { createServerClient } = require('@supabase/ssr');
  const mockClient = createServerClient();
  mockClient.auth.getUser.mockResolvedValue({
    data: { user: { id: 'test-user-id', email: 'test@example.com' } },
    error: null,
  });
}

// Helper to mock unauthenticated user
function mockUnauthenticatedUser() {
  const { createServerClient } = require('@supabase/ssr');
  const mockClient = createServerClient();
  mockClient.auth.getUser.mockResolvedValue({
    data: { user: null },
    error: new Error('Not authenticated'),
  });
}

describe('Middleware - Marketing Route Redirects', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Set local mode to skip billing checks
    process.env.NEXT_PUBLIC_ENV_MODE = 'local';
  });

  /**
   * Feature: remove-public-landing, Property 1: Unauthenticated marketing route redirect
   * Validates: Requirements 1.1, 2.1
   */
  it('Property 1: should redirect unauthenticated users from marketing routes to /auth', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.constantFrom('/', '/enterprise'),
        async (route) => {
          mockUnauthenticatedUser();
          
          const request = createMockRequest(route);
          const response = await middleware(request);
          
          // Verify redirect to /auth
          expect(response).toBeInstanceOf(NextResponse);
          expect(response.status).toBe(307); // Temporary redirect
          expect(response.headers.get('location')).toContain('/auth');
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Feature: remove-public-landing, Property 2: Authenticated marketing route redirect
   * Validates: Requirements 1.2, 2.1
   */
  it('Property 2: should redirect authenticated users from marketing routes to /dashboard', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.constantFrom('/', '/enterprise'),
        async (route) => {
          mockAuthenticatedUser();
          
          const request = createMockRequest(route);
          const response = await middleware(request);
          
          // Verify redirect to /dashboard
          expect(response).toBeInstanceOf(NextResponse);
          expect(response.status).toBe(307); // Temporary redirect
          expect(response.headers.get('location')).toContain('/dashboard');
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Feature: remove-public-landing, Property 3: Auth callback parameter preservation
   * Validates: Requirements 1.3
   */
  it('Property 3: should preserve auth callback parameters when redirecting to /auth/callback', async () => {
    await fc.assert(
      fc.asyncProperty(
        // Generate random combinations of auth parameters
        fc.record({
          code: fc.option(fc.string({ minLength: 10, maxLength: 50 }), { nil: undefined }),
          token: fc.option(fc.string({ minLength: 10, maxLength: 50 }), { nil: undefined }),
          type: fc.option(fc.constantFrom('signup', 'recovery', 'invite', 'magiclink'), { nil: undefined }),
          error: fc.option(fc.string({ minLength: 5, maxLength: 30 }), { nil: undefined }),
        }).filter(params => {
          // At least one auth parameter must be present
          return params.code !== undefined || 
                 params.token !== undefined || 
                 params.type !== undefined || 
                 params.error !== undefined;
        }),
        async (authParams) => {
          // Filter out undefined values
          const cleanParams: Record<string, string> = {};
          Object.entries(authParams).forEach(([key, value]) => {
            if (value !== undefined) {
              cleanParams[key] = value;
            }
          });
          
          const request = createMockRequest('/', cleanParams);
          const response = await middleware(request);
          
          // Verify redirect to /auth/callback
          expect(response).toBeInstanceOf(NextResponse);
          expect(response.status).toBe(307);
          const location = response.headers.get('location');
          expect(location).toContain('/auth/callback');
          
          // Verify all parameters are preserved
          const redirectUrl = new URL(location!, 'http://localhost:3000');
          Object.entries(cleanParams).forEach(([key, value]) => {
            expect(redirectUrl.searchParams.get(key)).toBe(value);
          });
        }
      ),
      { numRuns: 100 }
    );
  });
});
