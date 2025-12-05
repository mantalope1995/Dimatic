# Agent Model Assignment Changes

## Overview

This document summarizes the changes made to ensure all agents automatically use Minimax-m2 as their model, regardless of user input or existing configuration.

## Requirements Addressed

- **Requirement 1.2**: WHEN an agent is created or updated THEN the system SHALL automatically assign Minimax-m2 as the model
- **Requirement 1.4**: WHEN existing agents are loaded THEN the system SHALL override their model configuration to use Minimax-m2
- **Requirement 9.5**: WHEN migrating agent configurations THEN the system SHALL update the default model to Minimax-m2 while preserving other settings

## Changes Made

### 1. Agent Creation (`backend/core/agent_crud.py`)

**Location**: `create_agent` function, line ~600

**Change**: Replaced dynamic model selection with hardcoded Minimax-m2:

```python
# Before:
default_model = await model_manager.get_default_model_for_user(client, user_id)

# After:
# Always use Minimax-m2 as the model (Requirements 1.2)
default_model = "minimax/minimax-m2"
```

**Impact**: All newly created agents will use Minimax-m2, regardless of user tier or preferences.

### 2. Agent Update (`backend/core/agent_crud.py`)

**Location**: `update_agent` function, line ~350

**Change**: Replaced conditional model assignment with hardcoded Minimax-m2:

```python
# Before:
current_model = agent_data.model if agent_data.model is not None else current_version_data.get('model')

# After:
# Always use Minimax-m2 as the model (Requirements 1.4)
current_model = "minimax/minimax-m2"
```

**Impact**: All agent updates will use Minimax-m2, ignoring any model parameter in the update request.

### 3. Agent Loading - Custom Config (`backend/core/agent_loader.py`)

**Location**: `_load_custom_config` method, lines ~450-480

**Change**: Override model to Minimax-m2 when loading agent configuration:

```python
# New config format:
agent.model = "minimax/minimax-m2"  # Always override (Requirements 1.4, 9.5)

# Old config format:
agent.model = "minimax/minimax-m2"  # Always override (Requirements 1.4, 9.5)
```

**Impact**: When agents are loaded from the database, their model is overridden to Minimax-m2, preserving all other settings.

### 4. Agent Loading - Suna Config (`backend/core/agent_loader.py`)

**Location**: `_load_suna_config` method, line ~400

**Change**: Override Suna's model to Minimax-m2:

```python
# Before:
agent.model = static_config['model']

# After:
# Always override model to Minimax-m2 (Requirements 1.4, 9.5)
agent.model = "minimax/minimax-m2"
```

**Impact**: Even Suna (the default agent) will use Minimax-m2.

### 5. Agent Loading - Version Config (`backend/core/agent_loader.py`)

**Location**: `_apply_version_config` method, line ~550

**Change**: Override model when applying version configuration:

```python
# Before:
agent.model = config.get('model')

# After:
# Always override model to Minimax-m2 (Requirements 1.4, 9.5)
agent.model = "minimax/minimax-m2"
```

**Impact**: Batch loading operations will also use Minimax-m2.

### 6. Agent Loading - Fallback Config (`backend/core/agent_loader.py`)

**Location**: `_load_fallback_config` method, line ~570

**Change**: Use Minimax-m2 in fallback configuration:

```python
# Before:
agent.model = None

# After:
# Always use Minimax-m2 as the model (Requirements 1.4, 9.5)
agent.model = "minimax/minimax-m2"
```

**Impact**: Agents without valid configuration will default to Minimax-m2.

### 7. Agent Setup from Chat (`backend/core/agent_setup.py`)

**Location**: `setup_agent_from_chat` function, line ~222

**Change**: Use Minimax-m2 when creating agents from chat:

```python
# Before:
default_model = await model_manager.get_default_model_for_user(client, user_id)

# After:
# Always use Minimax-m2 as the model (Requirements 1.2)
default_model = "minimax/minimax-m2"
```

**Impact**: Agents created through the chat interface will use Minimax-m2.

### 8. Agent Creation Tool (`backend/core/tools/agent_creation_tool.py`)

**Location**: `create_agent` tool function, line ~169

**Change**: Use Minimax-m2 when agents are created via tool:

```python
# Before:
default_model = await model_manager.get_default_model_for_user(client, account_id)

# After:
# Always use Minimax-m2 as the model (Requirements 1.2)
default_model = "minimax/minimax-m2"
```

**Impact**: Agents created by other agents (via tool) will use Minimax-m2.

## Property-Based Tests

Two comprehensive property-based test suites were created to validate these changes:

### 1. `test_agent_model_assignment.py`

**Property 2: Agent Model Assignment**

Tests that verify:
- Agent creation always assigns Minimax-m2 (100 random test cases)
- Agent updates always assign Minimax-m2 (100 random test cases)
- Model assignment works regardless of requested model (gpt-4, claude-3, etc.)

### 2. `test_agent_configuration_migration.py`

**Property 20: Agent Configuration Migration**

Tests that verify:
- Agent loading overrides model to Minimax-m2 (100 random test cases)
- All other configuration settings are preserved during migration
- Settings preserved include:
  - Name, description, system prompt
  - Configured MCPs and custom MCPs
  - AgentPress tools
  - Tags, default status, and other metadata

## Migration Path

The changes ensure a seamless migration:

1. **Existing agents**: When loaded, their model is automatically overridden to Minimax-m2
2. **New agents**: Created with Minimax-m2 from the start
3. **Agent updates**: Any update operation will use Minimax-m2
4. **All settings preserved**: Only the model field is changed; all other configuration remains intact

## Verification

To verify the changes are working:

1. Create a new agent → Check that `model` field is `minimax/minimax-m2`
2. Load an existing agent → Check that `model` field is overridden to `minimax/minimax-m2`
3. Update an agent → Check that `model` field remains `minimax/minimax-m2`
4. Check agent execution → Verify that Minimax-m2 API is being called

## Notes

- The model registry already has Minimax-m2 configured with `enabled=True`
- Other models remain in the registry but are disabled
- The `get_default_model_for_user` function is no longer used for agent operations
- Agent runs will use the model from agent configuration (which is now always Minimax-m2)
