# Requirements Document

## Introduction

This document specifies the requirements for rebranding the application from "Kortix" to "Dimatic". Dimatic is an Australian company (dimatic.com.au, hello@dimatic.com.au) marketing to non-technical users. The rebranding includes:
- Replacing "Kortix" with "Dimatic" throughout the frontend and mobile applications
- Removing the "Suna" agent name from user-facing interfaces (backend references may remain for tracking)
- Renaming "Suna's Computer" to "Dimatic's Computer"
- Removing social media links (GitHub, Twitter, Discord, Instagram) as Dimatic has no social media presence
- Updating contact information and legal URLs to Dimatic domains

The obot and qwen-agent directories are excluded from this rebranding effort.

## Glossary

- **Dimatic**: The new company name replacing Kortix, an Australian company operating at dimatic.com.au
- **Frontend**: The Next.js web application in the `frontend/` directory
- **Mobile App**: The React Native/Expo application in the `apps/mobile/` directory
- **Backend**: The Python FastAPI backend in the `backend/` directory (minimal changes required)
- **Agent**: An AI assistant configuration; the default agent was previously named "Suna"
- **Social Media Links**: External links to GitHub, Twitter/X, Discord, and Instagram

## Requirements

### Requirement 1

**User Story:** As a user, I want to see the Dimatic brand throughout the application, so that I recognize the company I am interacting with.

#### Acceptance Criteria

1. WHEN a user views any page in the frontend application THEN the System SHALL display "Dimatic" instead of "Kortix" in all visible text, titles, and metadata
2. WHEN a user views the mobile application THEN the System SHALL display "Dimatic" instead of "Kortix" in all visible text and app configuration
3. WHEN a user views page metadata (title, description, Open Graph tags) THEN the System SHALL reference "Dimatic" and "dimatic.com.au" instead of "Kortix" and "kortix.com"
4. WHEN a user views pricing or feature descriptions THEN the System SHALL reference "Dimatic" instead of "Kortix" in feature names and descriptions

### Requirement 2

**User Story:** As a user, I want the default AI agent to be unnamed, so that the interface feels like a generic Dimatic service rather than a named character.

#### Acceptance Criteria

1. WHEN a user interacts with the default agent in the frontend THEN the System SHALL display generic text instead of "Suna" as the agent name
2. WHEN a user views the agent selection interface THEN the System SHALL display "Dimatic Agent" or similar generic naming instead of "Suna"
3. WHEN a user views the computer/sandbox panel THEN the System SHALL display "Dimatic's Computer" instead of "Suna's Computer"
4. WHEN a user views placeholder text or loading states THEN the System SHALL use generic agent references instead of "Suna"
5. WHEN the frontend displays agent-related UI elements THEN the System SHALL use the `isSunaDefault` flag only for internal logic, not for displaying the name "Suna"

### Requirement 3

**User Story:** As a user, I want to see accurate contact information for Dimatic, so that I can reach the company through correct channels.

#### Acceptance Criteria

1. WHEN a user views contact information THEN the System SHALL display "hello@dimatic.com.au" as the contact email
2. WHEN a user views the company website URL THEN the System SHALL display "dimatic.com.au" as the primary domain
3. WHEN a user views legal pages (Privacy Policy, Terms of Service) THEN the System SHALL link to Dimatic's legal pages at dimatic.com.au

### Requirement 4

**User Story:** As a user, I want the application to not display social media links, so that I am not directed to non-existent social profiles.

#### Acceptance Criteria

1. WHEN a user views the footer or navigation THEN the System SHALL NOT display links to Twitter/X, GitHub, Discord, or Instagram
2. WHEN a user views the help sidebar THEN the System SHALL NOT display links to external social media or code repositories
3. WHEN a user views any page THEN the System SHALL NOT display social media icons or "follow us" type content
4. WHEN a user views documentation links THEN the System SHALL either remove them or redirect to Dimatic's own documentation

### Requirement 5

**User Story:** As a user of the mobile app, I want to see consistent Dimatic branding, so that my experience matches the web application.

#### Acceptance Criteria

1. WHEN a user views the mobile app name in their device THEN the System SHALL display "Dimatic" as the app name
2. WHEN a user views the mobile app configuration THEN the System SHALL use "dimatic" as the app scheme and slug
3. WHEN a user views mobile app billing or pricing THEN the System SHALL reference "Dimatic" in plan names and descriptions
4. WHEN a user views the mobile app bundle identifier THEN the System SHALL use "com.dimatic.app" instead of "com.kortix.app"

### Requirement 6

**User Story:** As a developer maintaining the backend, I want to keep internal "Suna" references for agent tracking, so that existing data and logic remain functional.

#### Acceptance Criteria

1. WHEN the backend processes agent data THEN the System SHALL continue to use `is_suna_default` metadata flags for internal logic
2. WHEN the backend stores or retrieves agent configurations THEN the System SHALL maintain backward compatibility with existing "Suna" references in the database
3. WHEN the frontend communicates with the backend THEN the System SHALL translate internal "Suna" references to generic display names

### Requirement 7

**User Story:** As a user viewing translations, I want all languages to reflect the Dimatic brand, so that the experience is consistent regardless of language.

#### Acceptance Criteria

1. WHEN a user views the application in any supported language THEN the System SHALL display "Dimatic" branding consistently
2. WHEN a user views translated content THEN the System SHALL NOT display "Suna" or "Kortix" in any translation file
3. WHEN translation keys reference "suna" THEN the System SHALL rename or update those keys to use generic agent terminology

### Requirement 8

**User Story:** As a developer, I want the rebranding to preserve all code functionality, so that the application continues to work correctly after changes.

#### Acceptance Criteria

1. WHEN renaming files or directories THEN the System SHALL update all import statements that reference the renamed paths
2. WHEN renaming exported functions or variables THEN the System SHALL update all references to those exports throughout the codebase
3. WHEN modifying package.json or app.json configurations THEN the System SHALL ensure all dependent configurations remain valid
4. WHEN updating URL schemes or bundle identifiers THEN the System SHALL update all references in native code (Android/iOS) and configuration files
5. WHEN changing translation keys THEN the System SHALL update all code references that use those translation keys
6. WHEN modifying asset paths or filenames THEN the System SHALL update all references to those assets in code and configuration
