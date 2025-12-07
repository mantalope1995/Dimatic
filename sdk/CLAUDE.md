# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is the **Kortix SDK** - a Python SDK for creating, managing, and interacting with AI Workers on the Suna platform (formerly Dimatic/Kortix). The SDK provides a programmatic interface to create AI agents, manage conversation threads, and integrate external tools via the Model Context Protocol (MCP).

## Development Commands

### SDK Installation & Setup

```bash
# Install the SDK from the repository
pip install "kortix @ git+https://github.com/kortix-ai/suna.git@main#subdirectory=sdk"

# Or using uv (recommended)
uv add "kortix @ git+https://github.com/kortix-ai/suna.git@main#subdirectory=sdk"

# Install dependencies for development
uv sync

# Run the example with proper Python path
PYTHONPATH=$(pwd) uv run example/example.py
```

### Testing and Development

```bash
# No formal test suite currently exists
# Test changes using the example application

# Run example with MCP server integration
PYTHONPATH=$(pwd) uv run example/example.py

# Example includes local MCP server on port 4000
# Requires API key: export KORTIX_API_KEY="pk_xxx:sk_xxx"
```

## High-Level Architecture

### SDK Structure

The SDK follows a layered architecture with clear separation of concerns:

1. **Client Layer** (`kortix/kortix.py`)
   - Main entry point and client initialization
   - Creates and manages API clients for agents and threads
   - Provides unified interface to SDK functionality

2. **API Layer** (`kortix/api/`)
   - `agents.py`: Low-level agent API client (16K lines)
   - `threads.py`: Low-level thread/message API client (17K lines)
   - `utils.py`: HTTP streaming utilities with timeout handling
   - Handles all HTTP communication with Suna API endpoints

3. **Domain Models** (`kortix/models.py`)
   - Type definitions for messages, threads, agent runs
   - Enums for roles and message types
   - Dataclasses for structured data handling

4. **High-Level Abstractions**
   - `agent.py`: Agent management and execution wrapper
   - `thread.py`: Thread management and conversation handling
   - `tools.py`: Tool integration (MCP and AgentPress tools)

5. **Tool Integration** (`kortix/tools.py`)
   - **MCP (Model Context Protocol)**: External tool integration via HTTP endpoints
   - **AgentPress Tools**: Built-in tools (file ops, shell, web browsing, etc.)
   - Tool filtering and allowlist management

### Key Design Patterns

1. **Async-First Design**: All I/O operations use async/await patterns
2. **Streaming Support**: Real-time response streaming via HTTP chunked encoding
3. **Tool Extensibility**: Protocol-agnostic tool integration (MCP + AgentPress)
4. **Type Safety**: Comprehensive dataclasses and type annotations
5. **Client-Server Separation**: Low-level API clients separate from high-level abstractions

### Agent Execution Flow

1. **Initialization**: Create Kortix client with API key and endpoint
2. **Agent Creation**: Define agent with prompt, tools, and configuration
3. **Thread Management**: Create conversation threads for persistent context
4. **Tool Integration**: Connect MCP servers or enable AgentPress tools
5. **Execution**: Run agent with async streaming responses
6. **Message Handling**: Process structured messages with type safety

### MCP Integration

The SDK provides built-in MCP support for external tool integration:

```python
# MCP tool client initialization
mcp_tools = kortix.MCPTools(
    "http://localhost:4000/mcp/",  # MCP server endpoint
    "ToolName",                     # Human-readable name
    allowed_tools=["tool1", "tool2"]  # Optional allowlist
)
await mcp_tools.initialize()
```

### Message Types and Flow

The SDK handles multiple message types with structured data:
- **User Messages**: Direct user input
- **Assistant Messages**: AI responses with content objects
- **Tool Messages**: Tool execution results
- **Status Messages**: Execution status updates
- **Assistant Response End**: End-of-response metadata

### Built-in Tools (AgentPress)

Pre-configured tools available without external setup:
- File operations (read, write, edit)
- Shell command execution
- Web browsing and automation
- Web search capabilities
- Image analysis and editing
- Local service exposure (tunneling)

### Configuration and Customization

1. **Agent Configuration**:
   - Custom system prompts
   - Tool selection and allowlists
   - Model selection (default: Claude Sonnet 4)
   - Custom branding (icons, colors)

2. **Thread Configuration**:
   - Persistent conversation history
   - Message CRUD operations
   - Agent run tracking
   - Project association

3. **API Configuration**:
   - Custom API endpoints (localhost:8000 for local, suna.so for production)
   - Timeout configuration (300s for streaming)
   - Authentication via API keys

### Error Handling

- Structured error responses from API
- Timeout handling for long-running operations
- JSON parsing utilities for safe data extraction
- XML formatting for structured responses

### Important Implementation Details

1. **Streaming Implementation**: Uses httpx with configurable timeouts
2. **Message Serialization**: JSON-based content with type markers
3. **Tool Discovery**: Dynamic tool listing via MCP protocol
4. **State Management**: Client objects maintain API state and configuration
5. **Async Generators**: Streaming responses via async generators

### External Dependencies

- **httpx**: Async HTTP client for API communication
- **fastmcp**: MCP client implementation
- **Python 3.11+**: Required for modern async features

### Development Notes

- No formal testing framework currently implemented
- Example application serves as integration test
- MCP server runs locally in example for testing
- API endpoints differ between local and production environments
- Tool initialization must be awaited before use

### API Key Format

API keys follow the format: `pk_xxx:sk_xxx`
- Get keys from: https://suna.so/settings/api-keys
- Required for all SDK operations