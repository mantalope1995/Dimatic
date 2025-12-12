# Design Document: Dimatic Rebranding

## Overview

This design document outlines the technical approach for rebranding the application from "Kortix" to "Dimatic". The rebranding is a text/configuration change effort that spans the frontend (Next.js), mobile app (React Native/Expo), and minimal configuration updates. The backend Python code is largely unchanged except where user-facing strings are generated.

The key principles are:
1. **User-facing changes only** - Backend internal references to "Suna" remain for data compatibility
2. **Preserve functionality** - All imports, dependencies, and code logic must continue working
3. **Consistent branding** - All languages and platforms show "Dimatic" consistently
4. **Remove social presence** - No links to GitHub, Twitter, Discord, or Instagram

## Architecture

The rebranding affects three main areas:

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (Next.js)                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ Site Config │  │ Components  │  │ Translations (8 langs)  │  │
│  │ home.tsx    │  │ UI/Agent    │  │ en, de, es, fr, it,     │  │
│  │ site.ts     │  │ Help/Footer │  │ ja, pt, zh              │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                     Mobile App (Expo/RN)                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ app.json    │  │ Components  │  │ Locales (8 langs)       │  │
│  │ package.json│  │ Agent/Chat  │  │ Native configs          │  │
│  │ eas.json    │  │ Billing     │  │ Android/iOS             │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                    Backend (Python/FastAPI)                      │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ No changes required - internal "Suna" references preserved  ││
│  │ is_suna_default flag continues to work for agent detection  ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### Frontend Components to Modify

| File | Changes Required |
|------|------------------|
| `src/lib/home.tsx` | Replace Kortix→Dimatic, remove social links, update URLs |
| `src/lib/site.ts` | Update site name, remove social links |
| `src/lib/pricing-config.ts` | Replace "Kortix" in feature descriptions |
| `src/lib/model-provider-icons.tsx` | Rename kortix provider to dimatic |
| `src/components/thread/tool-call-side-panel.tsx` | "Suna's Computer" → "Dimatic's Computer" |
| `src/components/thread/chat-input/unified-config-menu.tsx` | Remove "Suna" display names |
| `src/components/thread/chat-input/chat-input.tsx` | Remove "Suna" references |
| `src/components/thread/chat-input/floating-tool-preview.tsx` | Generic agent name |
| `src/components/help/help-sidebar.tsx` | Remove GitHub/Discord links |
| `src/app/layout.tsx` | Update metadata, remove social meta tags |
| `src/app/suna/page.tsx` | Update or remove Suna-specific page |
| `translations/*.json` (8 files) | Rename "suna" keys, update brand names |

### Mobile App Components to Modify

| File | Changes Required |
|------|------------------|
| `app.json` | name, slug, scheme, bundleIdentifier |
| `package.json` | package name |
| `eas.json` | Update environment URLs if needed |
| `android/settings.gradle` | rootProject.name |
| `android/app/src/main/AndroidManifest.xml` | URL schemes |
| `android/app/src/main/java/com/kortix/app/` | Package directory rename |
| `ios/` | Bundle identifier updates |
| `lib/billing/pricing.ts` | Replace "Kortix" in descriptions |
| `lib/utils/model-provider.ts` | Rename kortix provider |
| `components/agents/AgentAvatar.tsx` | Update Suna detection comments |
| `components/chat/ThreadContent.tsx` | Default agent name |
| `contexts/AgentContext.tsx` | Update comments only |
| `locales/*.json` (8 files) | Update brand references |

### Translation Key Changes

The `suna` translation namespace will be renamed to `agent`:

```json
// Before
{
  "suna": {
    "samplePrompts": "Sample prompts",
    "chooseStyle": "Choose a style"
  }
}

// After
{
  "agent": {
    "samplePrompts": "Sample prompts",
    "chooseStyle": "Choose a style"
  }
}
```

## Data Models

No database schema changes are required. The `is_suna_default` metadata flag in agent records continues to function for identifying the default agent, but the frontend will not display "Suna" as the name.

### Agent Display Logic

```typescript
// Current behavior (to preserve internally)
const isDefaultAgent = agent?.metadata?.is_suna_default === true;

// Display logic (to change)
// Before: displayName = isDefaultAgent ? "Suna" : agent.name
// After:  displayName = isDefaultAgent ? "Dimatic Agent" : agent.name
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: No Kortix brand in frontend user-facing code
*For any* source file in the frontend `src/` directory (excluding test fixtures and example data), the file content SHALL NOT contain the string "Kortix" in user-visible contexts (strings, JSX text, metadata).
**Validates: Requirements 1.1, 1.3, 1.4**

### Property 2: No Kortix brand in mobile app user-facing code
*For any* source file in the mobile `apps/mobile/` directory (excluding node_modules), the file content SHALL NOT contain the string "Kortix" in user-visible contexts.
**Validates: Requirements 1.2, 5.1, 5.2, 5.3**

### Property 3: No Suna display name in frontend
*For any* frontend component that displays agent names, the displayed text SHALL NOT be "Suna" for the default agent.
**Validates: Requirements 2.1, 2.4**

### Property 4: No social media links in navigation/footer
*For any* navigation or footer component, the rendered output SHALL NOT contain URLs matching patterns for twitter.com, github.com, discord.gg, or instagram.com.
**Validates: Requirements 4.1, 4.3**

### Property 5: Translation files contain no old brand names
*For any* translation JSON file in frontend or mobile, the file content SHALL NOT contain "Kortix" or "Suna" as display values (keys may reference internal identifiers).
**Validates: Requirements 7.1, 7.2, 7.3**

### Property 6: Frontend-backend Suna flag translation
*For any* agent with `is_suna_default: true` metadata, the frontend SHALL display a generic name (e.g., "Dimatic Agent") instead of "Suna".
**Validates: Requirements 6.3**

### Property 7: Build integrity after changes
*For any* modified file, the application SHALL build successfully without import errors or missing reference errors.
**Validates: Requirements 8.1, 8.2, 8.3, 8.5**

### Property 8: Translation key consistency
*For any* translation key used in code (via `t('key')` or similar), the key SHALL exist in all translation files.
**Validates: Requirements 8.5**

## Error Handling

### Missing Translation Keys
If a translation key is renamed but not updated in code, the i18n library will typically show the key name as fallback. This should be caught during development/testing.

### Import Errors
If file renames break imports, TypeScript/build will fail immediately, preventing deployment of broken code.

### Asset Loading Failures
If asset paths are updated incorrectly, the build process or runtime will show missing asset errors.

## Testing Strategy

### Dual Testing Approach

This rebranding effort uses both verification scripts and manual review:

1. **Automated Verification (Property-Based)**
   - Grep-based searches to verify no old brand names exist
   - Build verification to ensure no broken imports
   - Translation key consistency checks

2. **Manual Review**
   - Visual inspection of key pages
   - Mobile app testing on simulators

### Property-Based Testing Library

For automated verification, we will use shell scripts with `grep` and `find` commands to verify properties across the codebase. These are not traditional PBT but serve the same purpose of verifying properties hold across all instances.

### Test Configuration

Each verification script will:
- Search relevant directories
- Exclude test fixtures, example data, and node_modules
- Report any violations with file paths and line numbers
- Exit with non-zero status if violations found

### Test Annotations

Each verification script will be annotated with:
```bash
# **Feature: dimatic-rebranding, Property N: <property_text>**
# **Validates: Requirements X.Y**
```

### Unit Tests

Minimal unit tests are needed since this is primarily a text replacement effort. The main verification is:
1. Build succeeds (frontend: `npm run build`, mobile: `npx expo prebuild`)
2. No old brand names in user-facing code
3. Translation keys are consistent

### Integration Testing

After changes:
1. Run frontend dev server and visually verify key pages
2. Run mobile app in simulator and verify branding
3. Verify all navigation links work (no 404s from removed social links)
