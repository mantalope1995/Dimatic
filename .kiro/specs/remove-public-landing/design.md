# Design Document

## Overview

This feature removes the public landing page and enterprise page by:
1. Updating the middleware to redirect `/` and `/enterprise` to auth/dashboard based on authentication
2. Deleting the `(home)` route group directory
3. Keeping `/legal` as a public route

The approach is minimal - we modify the existing middleware routing logic rather than restructuring the application.

## Architecture

No architectural changes. The existing Next.js middleware pattern handles all routing decisions.

```
User Request → Middleware → Route Decision
                  ↓
         Check auth status
                  ↓
    ┌─────────────┴─────────────┐
    │                           │
  Unauth                      Auth
    ↓                           ↓
  /auth                     /dashboard
```

## Components and Interfaces

### Modified Components

1. **Middleware** (`frontend/src/middleware.ts`)
   - Remove `/` and `/enterprise` from `PUBLIC_ROUTES`
   - Remove `/` and `/enterprise` from `MARKETING_ROUTES`
   - Add explicit redirect logic for `/` and `/enterprise` to redirect based on auth status
   - Preserve existing auth callback parameter handling for `/`

2. **File Deletions**
   - `frontend/src/app/(home)/` - entire directory (page.tsx, layout.tsx, layout-client.tsx, enterprise/, support/)

### Unchanged Components

- `frontend/src/app/legal/` - remains as public route
- `frontend/src/app/auth/` - unchanged
- `frontend/src/app/(dashboard)/` - unchanged
- All other routes - unchanged

## Data Models

No data model changes required.

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property Reflection

After analysing the acceptance criteria:
- Properties 1.1 and 2.1 (unauthenticated redirects) can be combined - both test that unauthenticated users on removed marketing routes get redirected to `/auth`
- Properties 1.2 and 2.1 (authenticated redirects) can be combined - both test that authenticated users on removed marketing routes get redirected to `/dashboard`
- Property 1.3 is unique - tests auth callback parameter preservation
- Property 3.1 is an example test - verifies legal page accessibility

### Properties

**Property 1: Unauthenticated marketing route redirect**
*For any* request to `/` or `/enterprise` without authentication, the middleware SHALL return a redirect response to `/auth`
**Validates: Requirements 1.1, 2.1**

**Property 2: Authenticated marketing route redirect**
*For any* request to `/` or `/enterprise` with valid authentication, the middleware SHALL return a redirect response to `/dashboard`
**Validates: Requirements 1.2, 2.1**

**Property 3: Auth callback parameter preservation**
*For any* request to `/` with Supabase auth parameters (code, token, type, or error), the middleware SHALL redirect to `/auth/callback` with all original query parameters preserved
**Validates: Requirements 1.3**

## Error Handling

- If middleware encounters an error during auth check, fall through to default behavior (redirect to auth)
- 404 handling for removed routes is automatic via Next.js when files are deleted

## Testing Strategy

### Unit Tests
- Test middleware redirect logic for `/` and `/enterprise` routes
- Test that `/legal` remains accessible without auth

### Property-Based Tests
- Use a property-based testing library (e.g., fast-check) to verify:
  - Property 1: Generate random unauthenticated requests to marketing routes → verify redirect to `/auth`
  - Property 2: Generate random authenticated requests to marketing routes → verify redirect to `/dashboard`
  - Property 3: Generate random combinations of auth query params → verify preservation in redirect

Given the minimal scope of this change (middleware updates only), manual verification after implementation is also appropriate.
