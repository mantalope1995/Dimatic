# Implementation Plan

- [ ] 1. Update frontend site configuration files
  - [ ] 1.1 Update `frontend/src/lib/home.tsx` - Replace Kortix with Dimatic, update URLs to dimatic.com.au, remove social media links (twitter, github, discord, instagram), update email to hello@dimatic.com.au
    - _Requirements: 1.1, 1.3, 3.1, 3.2, 3.3, 4.1_
  - [ ] 1.2 Update `frontend/src/lib/site.ts` - Replace brand name, remove social media links
    - _Requirements: 1.1, 4.1_
  - [ ] 1.3 Update `frontend/src/lib/pricing-config.ts` - Replace "Kortix" in feature descriptions with "Dimatic"
    - _Requirements: 1.4_
  - [ ] 1.4 Write verification script for Property 1 (no Kortix in frontend)
    - **Property 1: No Kortix brand in frontend user-facing code**
    - **Validates: Requirements 1.1, 1.3, 1.4**

- [ ] 2. Update frontend agent-related components
  - [ ] 2.1 Update `frontend/src/components/thread/tool-call-side-panel.tsx` - Change "Suna's Computer" to "Dimatic's Computer"
    - _Requirements: 2.3_
  - [ ] 2.2 Update `frontend/src/components/thread/chat-input/unified-config-menu.tsx` - Replace "Suna" display names with generic "Agent" or remove
    - _Requirements: 2.1, 2.2_
  - [ ] 2.3 Update `frontend/src/components/thread/chat-input/chat-input.tsx` - Remove Suna-specific variable names from user-facing contexts
    - _Requirements: 2.1, 2.4_
  - [ ] 2.4 Update `frontend/src/components/thread/chat-input/floating-tool-preview.tsx` - Replace "Suna" fallback with generic agent name
    - _Requirements: 2.4_
  - [ ] 2.5 Write verification script for Property 3 (no Suna display name)
    - **Property 3: No Suna display name in frontend**
    - **Validates: Requirements 2.1, 2.4**

- [ ] 3. Update frontend navigation and help components
  - [ ] 3.1 Update `frontend/src/components/help/help-sidebar.tsx` - Remove GitHub and Discord links
    - _Requirements: 4.2_
  - [ ] 3.2 Update `frontend/src/app/layout.tsx` - Update metadata, remove social media meta tags (twitter:site, etc.)
    - _Requirements: 1.3, 4.3_
  - [ ] 3.3 Update or remove `frontend/src/app/suna/page.tsx` - Update page content to remove Suna branding or redirect
    - _Requirements: 2.1_
  - [ ] 3.4 Write verification script for Property 4 (no social media links)
    - **Property 4: No social media links in navigation/footer**
    - **Validates: Requirements 4.1, 4.3**

- [ ] 4. Update frontend model provider utilities
  - [ ] 4.1 Update `frontend/src/lib/model-provider-icons.tsx` - Rename "kortix" provider to "dimatic", update display name and comments
    - _Requirements: 1.1_
  - [ ] 4.2 Update `frontend/src/lib/utils/clear-local-storage.ts` - Rename localStorage keys from "suna-*" to "dimatic-*"
    - _Requirements: 8.1_

- [ ] 5. Checkpoint - Verify frontend builds
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Update frontend translations
  - [ ] 6.1 Update `frontend/translations/en.json` - Rename "suna" namespace to "agent", remove any Kortix/Suna brand references
    - _Requirements: 7.1, 7.2, 7.3_
  - [ ] 6.2 Update `frontend/translations/de.json` - Same changes as en.json
    - _Requirements: 7.1, 7.2, 7.3_
  - [ ] 6.3 Update `frontend/translations/es.json` - Same changes as en.json
    - _Requirements: 7.1, 7.2, 7.3_
  - [ ] 6.4 Update `frontend/translations/fr.json` - Same changes as en.json
    - _Requirements: 7.1, 7.2, 7.3_
  - [ ] 6.5 Update `frontend/translations/it.json` - Same changes as en.json
    - _Requirements: 7.1, 7.2, 7.3_
  - [ ] 6.6 Update `frontend/translations/ja.json` - Same changes as en.json
    - _Requirements: 7.1, 7.2, 7.3_
  - [ ] 6.7 Update `frontend/translations/pt.json` - Same changes as en.json
    - _Requirements: 7.1, 7.2, 7.3_
  - [ ] 6.8 Update `frontend/translations/zh.json` - Same changes as en.json
    - _Requirements: 7.1, 7.2, 7.3_
  - [ ] 6.9 Update any frontend code that references the "suna" translation namespace to use "agent"
    - _Requirements: 8.5_
  - [ ] 6.10 Write verification script for Property 5 (no old brand names in translations)
    - **Property 5: Translation files contain no old brand names**
    - **Validates: Requirements 7.1, 7.2, 7.3**

- [ ] 7. Checkpoint - Verify frontend translations work
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Update mobile app configuration
  - [ ] 8.1 Update `apps/mobile/app.json` - Change name to "Dimatic", slug to "dimatic", scheme to "dimatic", bundleIdentifier to "com.dimatic.app"
    - _Requirements: 5.1, 5.2, 5.4_
  - [ ] 8.2 Update `apps/mobile/package.json` - Change package name to "dimatic"
    - _Requirements: 5.1_
  - [ ] 8.3 Update `apps/mobile/android/settings.gradle` - Change rootProject.name to "Dimatic"
    - _Requirements: 5.1, 8.4_
  - [ ] 8.4 Update `apps/mobile/android/app/src/main/AndroidManifest.xml` - Update URL schemes from "kortix" to "dimatic"
    - _Requirements: 5.2, 8.4_
  - [ ] 8.5 Rename Android package directory from `com/kortix/app` to `com/dimatic/app` and update MainActivity.kt package declaration
    - _Requirements: 5.4, 8.4_

- [ ] 9. Update mobile app components and utilities
  - [ ] 9.1 Update `apps/mobile/lib/billing/pricing.ts` - Replace "Kortix" in feature descriptions, update revenueCatId prefixes if needed
    - _Requirements: 5.3_
  - [ ] 9.2 Update `apps/mobile/lib/utils/model-provider.ts` - Rename "kortix" provider to "dimatic"
    - _Requirements: 1.2_
  - [ ] 9.3 Update `apps/mobile/lib/utils/i18n.ts` - Rename LANGUAGE_KEY from "@kortix_language" to "@dimatic_language"
    - _Requirements: 8.1_
  - [ ] 9.4 Update `apps/mobile/components/chat/ThreadContent.tsx` - Change default agentName from "Suna" to "Agent"
    - _Requirements: 2.1_
  - [ ] 9.5 Update `apps/mobile/components/agents/AgentAvatar.tsx` - Update comments, keep is_suna_default logic but remove "suna" from name checks
    - _Requirements: 6.3_
  - [ ] 9.6 Update `apps/mobile/components/settings/BillingPage.tsx` - Update URLs from kortix.com/suna.so to dimatic.com.au
    - _Requirements: 3.2_
  - [ ] 9.7 Write verification script for Property 2 (no Kortix in mobile)
    - **Property 2: No Kortix brand in mobile app user-facing code**
    - **Validates: Requirements 1.2, 5.1, 5.2, 5.3**

- [ ] 10. Update mobile app translations
  - [ ] 10.1 Update `apps/mobile/locales/en.json` - Remove any Kortix/Suna brand references
    - _Requirements: 7.1, 7.2_
  - [ ] 10.2 Update remaining mobile locale files (de, es, fr, it, ja, pt, zh) - Same changes
    - _Requirements: 7.1, 7.2_

- [ ] 11. Checkpoint - Verify mobile app builds
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. Final verification and cleanup
  - [ ] 12.1 Run all verification scripts to confirm no old brand names remain
    - _Requirements: 1.1, 1.2, 2.1, 4.1, 7.1_
  - [ ] 12.2 Verify frontend builds successfully with `npm run build`
    - _Requirements: 8.1, 8.2, 8.3_
  - [ ] 12.3 Write verification script for Property 7 (build integrity)
    - **Property 7: Build integrity after changes**
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.5**
  - [ ] 12.4 Write verification script for Property 8 (translation key consistency)
    - **Property 8: Translation key consistency**
    - **Validates: Requirements 8.5**

- [ ] 13. Final Checkpoint - Ensure all verifications pass
  - Ensure all tests pass, ask the user if questions arise.
