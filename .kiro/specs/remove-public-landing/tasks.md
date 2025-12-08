# Implementation Plan

- [x] 1. Update middleware routing logic
  - [x] 1.1 Remove `/` and `/enterprise` from PUBLIC_ROUTES array
    - Remove the homepage and enterprise entries from the public routes list
    - _Requirements: 1.1, 1.2, 2.1_
  - [x] 1.2 Update MARKETING_ROUTES to remove `/` and `/enterprise`
    - Remove these routes from locale-based marketing route handling
    - _Requirements: 1.1, 2.1_
  - [x] 1.3 Add redirect logic for `/` route
    - Before public route checks, add logic to redirect `/` to `/auth` (unauth) or `/dashboard` (auth)
    - Preserve existing Supabase auth callback parameter handling
    - _Requirements: 1.1, 1.2, 1.3_
  - [x] 1.4 Add redirect logic for `/enterprise` route
    - Redirect `/enterprise` to `/auth` (unauth) or `/dashboard` (auth)
    - _Requirements: 2.1_
  - [x] 1.5 Write property test for unauthenticated redirect
    - **Property 1: Unauthenticated marketing route redirect**
    - **Validates: Requirements 1.1, 2.1**
  - [x] 1.6 Write property test for authenticated redirect
    - **Property 2: Authenticated marketing route redirect**
    - **Validates: Requirements 1.2, 2.1**
  - [x] 1.7 Write property test for auth callback parameter preservation
    - **Property 3: Auth callback parameter preservation**
    - **Validates: Requirements 1.3**

- [x] 2. Remove (home) route group
  - [x] 2.1 Delete the `frontend/src/app/(home)/` directory
    - Remove page.tsx, layout.tsx, layout-client.tsx, enterprise/, support/
    - _Requirements: 1.1, 2.1_

- [x] 3. Verify legal page accessibility
  - [x] 3.1 Confirm `/legal` remains in PUBLIC_ROUTES
    - Verify the legal route is still accessible without authentication
    - _Requirements: 3.1_

- [x] 4. Final verification
  - Ensure all tests pass, ask the user if questions arise.
