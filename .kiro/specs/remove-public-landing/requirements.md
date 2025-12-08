# Requirements Document

## Introduction

Remove the public landing page and enterprise page. Users should land on the dashboard or auth page. Legal pages remain accessible.

## Glossary

- **Landing Page**: Public homepage at `frontend/src/app/(home)/page.tsx`
- **Enterprise Page**: Public page at `frontend/src/app/(home)/enterprise/page.tsx`
- **Middleware**: Next.js middleware at `frontend/src/middleware.ts` handling routing

## Requirements

### Requirement 1

**User Story:** As a user visiting the root URL, I want to be redirected based on auth status, so that I skip the marketing page.

#### Acceptance Criteria

1. WHEN an unauthenticated user visits `/` THEN the System SHALL redirect to `/auth`
2. WHEN an authenticated user visits `/` THEN the System SHALL redirect to `/dashboard`
3. WHEN a user visits `/` with Supabase auth parameters THEN the System SHALL redirect to `/auth/callback` preserving query parameters

### Requirement 2

**User Story:** As a user, I want the enterprise page removed, so that marketing content is no longer exposed.

#### Acceptance Criteria

1. WHEN a user visits `/enterprise` THEN the System SHALL redirect based on auth status (to `/auth` or `/dashboard`)

### Requirement 3

**User Story:** As a user, I want legal pages to remain accessible without authentication.

#### Acceptance Criteria

1. WHEN a user visits `/legal` THEN the System SHALL display the legal content without requiring authentication
