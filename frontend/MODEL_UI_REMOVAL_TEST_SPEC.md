# Model UI Removal Test Specification

## Overview
This document specifies the tests that should be performed to verify that model selection UI has been properly removed from the frontend.

## Test Requirements

### Requirement 11.1: Agent Creation UI
**Requirement**: WHEN the agent creation UI loads THEN the system SHALL not display any model selection or configuration UI

**Test Cases**:
1. **Test: No model selector in creation modal**
   - Open agent creation modal
   - Verify no dropdown or selector for model selection appears
   - Verify no "Model" label or field is visible
   - Expected: Agent creation proceeds without model selection

2. **Test: Agent created without model parameter**
   - Create a new agent through the UI
   - Verify agent is created successfully
   - Verify no model-related errors occur
   - Expected: Agent uses Minimax-m2 automatically (backend assigns)

### Requirement 11.2: Agent Settings UI
**Requirement**: WHEN the agent settings UI loads THEN the system SHALL not show any model information or configuration options

**Test Cases**:
1. **Test: No model display in settings**
   - Open agent configuration dialog
   - Navigate through all tabs (Instructions, Tools, Integrations, Knowledge, Triggers)
   - Verify no "Model" section or field appears
   - Expected: No model information visible

2. **Test: Settings save without model field**
   - Open agent configuration
   - Modify agent settings (name, instructions, tools)
   - Save changes
   - Verify save succeeds without model field
   - Expected: Changes saved successfully

### Requirement 11.3: Agent Information Display
**Requirement**: WHEN displaying agent information THEN the system SHALL not show any model name or identifier

**Test Cases**:
1. **Test: Agent cards show no model**
   - View agents list/grid
   - Inspect each agent card
   - Verify no model name or identifier is displayed
   - Expected: Only agent name, description, and icon visible

2. **Test: Agent details show no model**
   - Open agent configuration page
   - View agent header and details
   - Verify no model information in any section
   - Expected: No model name or identifier visible

### Requirement 11.4: Model Tier Selection Removed
**Requirement**: WHERE model tier selection existed (basic/power) THEN the system SHALL remove these UI elements completely

**Test Cases**:
1. **Test: No tier selection in agent config**
   - Open agent configuration
   - Search for any "Basic" or "Power" mode toggles
   - Verify no tier selection UI exists
   - Expected: No tier selection visible

2. **Test: No tier badges on agents**
   - View agents list
   - Check for "Basic" or "Power" badges on agent cards
   - Verify no tier indicators appear
   - Expected: No tier badges visible

## Manual Testing Checklist

### Pre-Test Setup
- [ ] Ensure backend is running with Minimax-m2 configuration
- [ ] Clear browser cache and local storage
- [ ] Log in to the application

### Agent Creation Tests
- [ ] Open "Create New Worker" modal
- [ ] Verify no model selection dropdown
- [ ] Create agent via "Configure Manually"
- [ ] Verify agent created successfully
- [ ] Create agent via "Configure by Chat"
- [ ] Verify agent created successfully

### Agent Configuration Tests
- [ ] Open existing agent configuration
- [ ] Check Instructions tab - no model field
- [ ] Check Tools tab - no model field
- [ ] Check Integrations tab - no model field
- [ ] Check Knowledge tab - no model field
- [ ] Check Triggers tab - no model field
- [ ] Modify agent name and save
- [ ] Verify save succeeds

### Agent Display Tests
- [ ] View agents grid/list
- [ ] Verify no model names on cards
- [ ] Verify no tier badges (Basic/Power)
- [ ] Open agent details
- [ ] Verify no model information in header
- [ ] Verify no model information in any section

### Regression Tests
- [ ] Create new agent - works
- [ ] Edit existing agent - works
- [ ] Delete agent - works
- [ ] Start chat with agent - works
- [ ] Agent responds correctly - works

## Expected Results

All tests should pass with the following outcomes:
1. No model selection UI visible anywhere in agent creation or configuration
2. No model information displayed in agent cards or details
3. No model tier selection (Basic/Power) UI elements
4. All agent operations (create, edit, delete, chat) work correctly
5. Backend automatically assigns Minimax-m2 to all agents

## Notes

- These tests verify UI changes only
- Backend model assignment is tested separately
- Billing/subscription "Power mode" features are separate and should remain
- Chat input model selector (for conversations) is separate from agent model configuration
