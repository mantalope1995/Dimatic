# Frontend Model Selection UI Removal

## Overview
This document describes the changes made to remove model selection UI from the frontend as part of the Minimax-m2 migration.

## Changes Made

### 1. Removed Model Selector Component
- **File Deleted**: `frontend/src/components/agents/config/model-selector.tsx`
- **Reason**: Model selection is no longer needed as Minimax-m2 is the only model

### 2. Updated Agent Configuration Dialog
- **File**: `frontend/src/components/agents/agent-configuration-dialog.tsx`
- **Changes**:
  - Removed `model` field from form data state
  - Removed `handleModelChange` function
  - Removed model from form initialization
  - Removed model from update data
  - Commented out import of `AgentModelSelector` (kept for reference)
  - Model selector UI remains commented out (was already commented)

### 3. Existing State
The following were already in the correct state:
- Agent creation modal (`agent-creation-modal.tsx`) - No model selection UI
- Agent config page (`app/(dashboard)/agents/config/[agentId]/page.tsx`) - No model display
- New agent dialog (`new-agent-dialog.tsx`) - No model selection

## What Was NOT Removed

### Billing/Subscription Related
The following model-related UI elements were intentionally kept as they relate to subscription tiers, not agent model selection:
- `frontend/src/components/billing/pricing/pricing-section.tsx` - "Kortix Power mode" in pricing features
- `frontend/src/components/thread/chat-input/upgrade-preview.tsx` - "Kortix Power mode" in upgrade preview
- `frontend/src/components/thread/chat-input/unified-config-menu.tsx` - Model toggle for chat (separate from agent config)

## Testing Requirements

Since there is no testing framework configured in the frontend, manual testing should verify:

### Test Cases
1. **Agent Creation**
   - ✓ Verify no model selection dropdown appears when creating a new agent
   - ✓ Verify agents are created successfully without model selection

2. **Agent Configuration**
   - ✓ Verify agent settings page does not show model information
   - ✓ Verify agent settings page does not show model configuration options
   - ✓ Verify no model tier selection (basic/power) appears

3. **Agent Display**
   - ✓ Verify agent cards/lists do not display model information
   - ✓ Verify agent details do not show model name or identifier

4. **Existing Functionality**
   - ✓ Verify agents can still be created and configured
   - ✓ Verify agent settings can be saved without model field
   - ✓ Verify existing agents continue to work

## Requirements Validated

This implementation satisfies the following requirements from the spec:

- **Requirement 11.1**: Agent creation UI does not display model selection
- **Requirement 11.2**: Agent settings UI does not show model information
- **Requirement 11.3**: Agent information does not show model name or identifier
- **Requirement 11.4**: Model tier selection (basic/power) UI elements are removed

## Notes

- The model selector component was completely removed rather than just hidden, as it will not be needed in the future
- Form data and handlers were cleaned up to remove model-related code
- Commented code was preserved for reference
- The backend will automatically assign Minimax-m2 to all agents
