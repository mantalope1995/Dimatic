# AWS AgentCore Integration

This module provides integration with AWS Bedrock AgentCore for the Kortix AI agent platform. It includes configuration management and adapter classes for all AgentCore primitives.

> **📘 Developer Guide**: For detailed guidance on working with the AgentCore migration, see **[CLAUDE.md](CLAUDE.md)**. It includes migration status, architecture overview, testing strategies, and AWS SDK patterns.

## Overview

## Implementation Status

| Migration | Tasks Complete | Progress |
|-----------|----------------|----------|
| **Phase 1** (Runtime Integration) | 15 / 15 | **100%** ✅ |
| **Phase 2** (Code Interpreter & Browser) | 15 / 15 | **100%** ✅ |
| **Phase 4** (Memory Integration) | 15 / 15 | **100%** ✅ |
| **Phase 5** (MCP Integration) | 8 / 8 | **100%** ✅ |
| **Phase 6** (ThreadManager & Tool Registry) | 4 / 4 | **100%** ✅ |
| **Full Migration** (Complete Platform) | 57 / 77 | ~74% |

**Phase 1 Runtime Integration Complete** (Tasks 1-5):
- ✅ Task 1: AgentCore SDK integration (boto3 dependency, config.py)
- ✅ Task 2: Runtime Adapter implementation (deploy_agent, invoke_agent, cancel_execution)
- ✅ Task 3: Agent packaging and deployment automation
- ✅ Task 4: Execution Manager with SSE streaming
- ✅ Task 5: Integration tests and property tests

**Phase 2 Code Interpreter & Browser Complete** (Tasks 6-9):
- ✅ Task 6: Code Interpreter Adapter (execute_code, execute_shell_command, file operations)
- ✅ Task 7: Browser Adapter (navigate, extract_content, fill_form, screenshot)
- ✅ Task 8: Property tests (Properties 1-6, 9-17)
- ✅ Task 9: Integration tests and fallback verification

**Phase 4 Memory Integration Complete** (Tasks 10-13):
- ✅ Task 10: Memory Adapter Implementation (create_memory_resource, store_message, retrieve_messages)
- ✅ Task 11: ThreadManager Memory Integration (create Memory on thread creation, store/retrieve messages)
- ✅ Task 12: Memory cleanup on thread deletion
- ✅ Task 13: Property tests (Properties 7, 8, 20, 24)

**Phase 5 MCP Integration Complete** (Tasks 14-21):
- ✅ Task 14: Gateway Adapter Implementation (deploy_mcp_server, invoke_mcp_tool, list_tools)
- ✅ Task 15: OAuth flow management (generate_auth_url, exchange_code_for_tokens, refresh_tokens)
- ✅ Task 16: MCP catalog and deployment tracking (DynamoDB tables, CRUD operations)
- ✅ Task 17: Tool discovery and registration (list_mcp_tools, register_tool_with_gateway)
- ✅ Task 18: Credential management (Secrets Manager integration, OAuth token storage)
- ✅ Task 19: MCP server deployment automation (deploy_server, update_config, delete_deployment)
- ✅ Task 20: Property tests (Properties 21-24: OAuth flow, credential storage, server deployment)
- ✅ Task 21: Integration tests (end-to-end MCP tool execution via Gateway)

**Phase 6 ThreadManager & Tool Registry Complete** (Tasks 22-25):
- ✅ Task 22: Tool Registry Service (centralized tool discovery and metadata management)
- ✅ Task 23: ThreadManager Runtime Integration (create Runtime deployment on thread creation)
- ✅ Task 24: Tool Execution Coordination (unified execute() path via Runtime with fallback)
- ✅ Task 25: Integration tests and verification (end-to-end flows, tool registry discovery)

**Remaining Phases**: Advanced features and optimization (see CLAUDE.md for details)

**See**: [CLAUDE.md](CLAUDE.md) for detailed migration status and next steps.

AWS Bedrock AgentCore provides serverless infrastructure for AI agents with the following primitives:

- **Runtime**: Serverless agent execution with automatic scaling
- **Memory**: Persistent knowledge storage with semantic search
- **Code Interpreter**: Secure code execution in isolated sandboxes
- **Browser**: Cloud-based browser automation
- **Gateway**: MCP server integration and API connectivity

## Installation

The AgentCore SDK integration is included in the backend. Dependencies are managed via `pyproject.toml`:

```bash
# Install dependencies
uv sync

# Or using pip
pip install boto3>=1.40.74
```

## Configuration

### Environment Variables

Configure AgentCore using environment variables in your `.env` file:

```bash
# Environment: local, development, production
AGENTCORE_ENVIRONMENT=local

# AWS Configuration
# CRITICAL: Phase 1 requires ap-southeast-2 for data residency
AGENTCORE_AWS_REGION=ap-southeast-2
AGENTCORE_AWS_ACCESS_KEY_ID=your-access-key
AGENTCORE_AWS_SECRET_ACCESS_KEY=your-secret-key

# Feature Flags (default: true)
AGENTCORE_RUNTIME_ENABLED=true           # ✅ Phase 1 Complete
AGENTCORE_MEMORY_ENABLED=true             # ✅ Phase 4 Complete
AGENTCORE_CODE_INTERPRETER_ENABLED=true # ✅ Phase 2 Complete
AGENTCORE_BROWSER_ENABLED=true            # ✅ Phase 2 Complete
AGENTCORE_GATEWAY_ENABLED=false          # Phase 5

# S3 Configuration (required for Code Interpreter and Browser)
AGENTCORE_S3_BUCKET_NAME=your-bucket-name
AGENTCORE_S3_BUCKET_REGION=ap-southeast-2

# Runtime Configuration (Phase 1)
AGENTCORE_RUNTIME_MEMORY_LIMIT_MB=2048
AGENTCORE_RUNTIME_TIMEOUT_SECONDS=900

# Deployment Automation (Phase 1)
AGENTCORE_AUTO_DEPLOY_ENABLED=true
AGENTCORE_DEPLOYMENT_RETRY_ATTEMPTS=3
AGENTCORE_ROLLBACK_ON_FAILURE=true

# Timeouts (in seconds)
AGENTCORE_CODE_INTERPRETER_TIMEOUT_SECONDS=30
AGENTCORE_BROWSER_TIMEOUT_SECONDS=60
AGENTCORE_GATEWAY_TIMEOUT_SECONDS=30

# Fallback Configuration
AGENTCORE_FALLBACK_TO_DATABASE=true
AGENTCORE_FALLBACK_TO_LEGACY_SANDBOX=true  # Dramatiq background worker
```

### Programmatic Configuration

```python
from core.agentcore import AgentCoreConfig, Environment

# Create configuration
config = AgentCoreConfig(
    environment=Environment.PRODUCTION,
    aws_region="us-east-1",
    aws_access_key_id="your-key",
    aws_secret_access_key="your-secret",
    s3_bucket_name="your-bucket",
    runtime_enabled=True,
    memory_enabled=True,
)

# Or load from environment
from core.agentcore import get_agentcore_config
config = get_agentcore_config()
```

## Usage

### AgentCore Runtime (Phase 1 - Complete)

The Runtime integration provides serverless agent execution with SSE streaming and automatic deployment management.

#### Execution Manager

```python
from core.agentcore.runtime import ExecutionManager, ExecutionContext, ExecutionConfig

# Initialize execution manager
manager = ExecutionManager()

# Create execution context
context = ExecutionContext(
    agent_id="my-agent",
    user_id="user-123",
    session_id="session-abc",
    input_text="What is the weather today?",
    config=ExecutionConfig(
        deployment_id="dep-my-agent-v1",  # Auto-deployed if needed
        timeout_seconds=300,
        enable_trace=False,
        fallback_to_dramatiq=True,
    ),
)

# Execute agent and stream results
async for chunk in manager.execute_agent(context=context):
    if chunk["type"] == "token":
        print(f"Token: {chunk['data'].get('content', '')}")
    elif chunk["type"] == "metadata":
        print(f"Status: {chunk['data'].get('status')}")

# Get execution info
info = await manager.get_execution_info(execution_id="exec-123")
print(f"Status: {info['status']}, Duration: {info['duration_seconds']}s")
```

#### SSE Streaming Handler

```python
from core.agentcore.runtime import stream_agent_execution_sse

# Stream agent execution via Server-Sent Events
async for sse_event in stream_agent_execution_sse(
    deployment_id="dep-my-agent-v1",
    session_id="session-abc",
    input_text="Hello, agent!",
    enable_trace=True,
    timeout_seconds=300,
):
    print(sse_event)  # Formatted SSE event string
```

#### Deployment Manager

```python
from core.agentcore.deployment import DeploymentManager

# Initialize deployment manager
deployer = DeploymentManager()

# Deploy agent version
result = await deployer.deploy_agent_version(
    agent_id="my-agent",
    version_id="v1.0.0",
    agent_config={
        "name": "My Agent",
        "system_prompt": "You are a helpful assistant",
        "model": "claude-3-5-sonnet-20241022",
    },
)

print(f"Deployment ID: {result.deployment_id}")
print(f"Status: {result.status}")

# Trigger deployment on agent update
result = await deployer.trigger_deployment(
    agent_id="my-agent",
    version_id="v1.1.0",
    agent_config={"name": "My Agent v1.1"},
    trigger_type="agent_update",
)
```

#### Runtime Adapter (Direct Usage)

```python
from core.agentcore.adapters import AgentCoreRuntimeAdapter

# Initialize adapter
runtime = AgentCoreRuntimeAdapter()

# Deploy agent
deployment_id = await runtime.deploy_agent(
    agent_id="my-agent",
    agent_config={"system_prompt": "You are a helpful assistant"},
    version_id="v1"
)

# Invoke agent with streaming
async for response in runtime.invoke_agent(
    deployment_id=deployment_id,
    session_id="thread-123",
    input_text="Hello",
    stream=True
):
    print(response)

# Cancel execution
await runtime.cancel_execution(execution_id="exec-123")

# Get execution status
status = await runtime.get_execution_status(execution_id="exec-123")
```

### Tool Registry (Phase 6)

Centralized tool discovery and metadata management:

```python
from core.agentcore import ToolRegistry, ToolMetadata

# Initialize registry
registry = ToolRegistry()

# Discover all tools in a package
tools = await registry.discover_tools(tool_package="core.tools")
print(f"Discovered {len(tools)} tools")

# Register a tool with metadata
metadata = ToolMetadata(
    name="web_search",
    description="Search the web for information",
    category="mcp",
    input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
    output_schema={"type": "object"},
    is_agentcore_native=False
)
await registry.register_tool(metadata)

# Get tool by name
tool = await registry.get_tool("web_search")
print(f"Tool: {tool.name} - {tool.description}")

# List tools by category
mcp_tools = await registry.list_tools(category="mcp")
for tool in mcp_tools:
    print(f"  - {tool.name}")

# Unregister a tool
await registry.unregister_tool("web_search")
```

### ThreadManager Runtime Integration (Phase 6)

ThreadManager integration with AgentCore Runtime for serverless tool execution:

```python
from core.agentpress import ThreadManager
from core.agentcore import get_config

# Initialize ThreadManager (auto-creates Runtime deployment)
manager = ThreadManager(
    account_id="account-456",
    project_id="project-123"
)

# Create thread - automatically creates Runtime deployment
thread_id = await manager.create_thread(
    name="My Thread",
    runtime_enabled=True  # Set to false to disable Runtime
)
print(f"Thread created: {thread_id}")

# ThreadManager automatically registers tools with Runtime
# Tools are executed through Runtime when available

# Execute tool via Runtime (automatic fallback to local)
result = await manager.execute_tool(
    tool_name="web_search",
    arguments={"query": "AWS AgentCore documentation"},
    thread_id=thread_id
)
print(f"Result: {result}")

# Get thread with Runtime metadata
thread = await manager.get_thread(thread_id)
print(f"Runtime Deployment: {thread.get('runtime_deployment_id')}")
print(f"Runtime Status: {thread.get('runtime_metadata', {}).get('status')}")

# Delete thread - automatically cleans up Runtime deployment
await manager.delete_thread(thread_id)
```

### ThreadManager with Custom Runtime Configuration

```python
from core.agentpress import ThreadManager
from core.agentcore import AgentCoreConfig, ExecutionConfig

# Create ThreadManager with custom Runtime config
manager = ThreadManager(
    account_id="account-456",
    runtime_config=ExecutionConfig(
        timeout_seconds=300,
        enable_trace=True,
        fallback_to_local=True
    )
)

# Create thread with specific Runtime settings
thread_id = await manager.create_thread(
    name="Production Thread",
    runtime_enabled=True,
    runtime_timeout_seconds=600,
    runtime_memory_mb=4096
)

# Execute tool with explicit Runtime preference
result = await manager.execute_tool(
    tool_name="data_analysis",
    arguments={"dataset": "sales_2024.csv"},
    thread_id=thread_id,
    prefer_runtime=True  # Try Runtime first, fallback to local
)
```

### AgentCore Memory

Store and retrieve conversation history:

```python
from core.agentcore import AgentCoreMemoryAdapter

# Initialize adapter
memory = AgentCoreMemoryAdapter()

# Create memory resource
memory_id = await memory.create_memory_resource(
    thread_id="thread-123",
    account_id="account-456"
)

# Store message
message_id = await memory.store_message(
    memory_resource_id=memory_id,
    message={"role": "user", "content": "Hello"},
    metadata={"timestamp": "2024-01-01T00:00:00Z"}
)

# Retrieve messages
messages = await memory.retrieve_messages(
    memory_resource_id=memory_id,
    limit=100
)

# Semantic search
relevant_messages = await memory.retrieve_messages(
    memory_resource_id=memory_id,
    semantic_query="What did we discuss about pricing?",
    limit=10
)

# Delete memory resource
await memory.delete_memory_resource(memory_id)
```

### AgentCore Code Interpreter

Execute code in isolated environments:

```python
from core.agentcore import AgentCoreCodeInterpreterAdapter

# Initialize adapter
code_interpreter = AgentCoreCodeInterpreterAdapter()

# Execute Python code
result = await code_interpreter.execute_code(
    code="print('Hello, World!')",
    language="python",
    timeout=30
)
print(result["output"])

# Execute shell command
result = await code_interpreter.execute_shell_command(
    command="ls -la",
    working_dir="/workspace",
    timeout=30
)
print(result["stdout"])

# Upload file
await code_interpreter.upload_file(
    file_path="/workspace/data.txt",
    content=b"file content"
)

# Download file
content = await code_interpreter.download_file("/workspace/output.txt")

# List files
files = await code_interpreter.list_files("/workspace")
```

### AgentCore Browser

Automate web interactions:

```python
from core.agentcore import AgentCoreBrowserAdapter

# Initialize adapter
browser = AgentCoreBrowserAdapter()

# Navigate to URL
result = await browser.navigate(
    url="https://example.com",
    wait_for="#content"
)
print(result["html"])

# Extract content
content = await browser.extract_content(
    url="https://example.com",
    selectors=["h1", ".article"]
)
print(content["text"])

# Fill form
result = await browser.fill_form(
    form_data={
        "#username": "user@example.com",
        "#password": "password123"
    },
    submit=True
)

# Click element
await browser.click_element("#submit-button")

# Take screenshot
screenshot = await browser.take_screenshot(full_page=True)
```

### AgentCore Gateway

Deploy and invoke MCP servers:

```python
from core.agentcore import AgentCoreGatewayAdapter

# Initialize adapter
gateway = AgentCoreGatewayAdapter()

# Deploy MCP server
deployment_id = await gateway.deploy_mcp_server(
    mcp_config={
        "name": "github",
        "type": "http",
        "openapi_spec": "https://api.github.com/openapi.json"
    },
    account_id="account-456"
)

# Invoke MCP tool
result = await gateway.invoke_mcp_tool(
    gateway_deployment_id=deployment_id,
    tool_name="get_user",
    parameters={"username": "octocat"},
    credentials={"token": "github-token"}
)
print(result)

# Update configuration
await gateway.update_gateway_config(
    gateway_deployment_id=deployment_id,
    config={"rate_limit": 100}
)

# Delete deployment
await gateway.delete_gateway_deployment(deployment_id)
```

## Architecture

### Module Structure

```
backend/core/agentcore/
├── __init__.py              # Module exports (Runtime, Memory, ToolRegistry, etc.)
├── config.py                # Configuration management with environment variables
├── models.py                # Data models (RuntimeStatus, DeploymentResult, ToolMetadata, etc.)
├── errors.py                # Error hierarchy and retry decorators
├── adapters/
│   ├── __init__.py
│   ├── runtime.py           # ✅ Runtime adapter (deploy_agent, invoke_agent, etc.)
│   ├── memory.py            # ✅ Memory adapter (create_memory_resource, store_message, etc.)
│   ├── code_interpreter.py  # ✅ Code Interpreter adapter (execute_code, execute_shell_command)
│   ├── browser.py           # ✅ Browser adapter (navigate, extract_content, fill_form)
│   └── gateway.py           # ✅ Gateway adapter (MCP server deployment, tool invocation)
├── runtime/
│   ├── __init__.py
│   ├── execution_manager.py # ✅ Execution lifecycle management
│   └── streaming_handler.py # ✅ SSE streaming handler
├── deployment/
│   ├── __init__.py
│   ├── agent_packager.py    # ✅ Agent packaging for AgentCore deployment
│   └── deployment_manager.py # ✅ Deployment orchestration and rollback
├── registry/
│   ├── __init__.py
│   ├── tool_registry.py     # ✅ Tool Registry for centralized tool discovery
│   └── tool_metadata.py     # ✅ Tool metadata models and schemas
├── tests/
│   ├── __init__.py
│   ├── test_config.py       # Configuration tests
│   ├── test_adapters.py     # Adapter unit tests
│   ├── test_deployment.py   # Deployment automation tests
│   ├── test_runtime_execution.py  # Runtime execution flow tests
│   ├── test_integration_phase6.py   # ✅ Phase 6 integration tests (end-to-end)
│   ├── test_property_runtime.py   # Property-based tests (7 properties)
│   └── test_tool_registry.py      # ✅ Tool registry tests
└── README.md                # This file
```

### Design Principles

1. **Clean Interfaces**: Each adapter provides a simple, consistent API
2. **Environment-Based Configuration**: Support for dev/prod environments
3. **Graceful Fallbacks**: Fallback to database when AgentCore unavailable
4. **Tenant Isolation**: Built-in multi-tenancy support
5. **Error Handling**: Comprehensive error handling with retries
6. **Testability**: Full test coverage with mocks

## Testing

Run the test suite:

```bash
# Run all AgentCore tests
uv run pytest core/agentcore/tests/ -v

# Run specific test file
uv run pytest core/agentcore/tests/test_config.py -v

# Run integration tests
uv run pytest core/agentcore/tests/test_runtime_integration.py -v

# Run property-based tests
uv run pytest core/agentcore/tests/test_property_runtime.py -v

# Run with coverage
uv run pytest core/agentcore/tests/ --cov=core.agentcore --cov-report=html

# Run by marker
uv run pytest -m unit  # Fast tests, no external dependencies
uv run pytest -m integration  # Tests with database/external services
```

### Test Coverage

Phase 1 Runtime Integration includes comprehensive test coverage:

1. **Unit Tests**: Individual component testing
   - Configuration loading and validation
   - Adapter method implementations
   - Model serialization/deserialization

2. **Property Tests**: Hypothesis-based invariant testing
   - Property 1: AgentCore Runtime Routing
   - Property 2: Concurrent Execution Scaling
   - Property 3: Execution Result Persistence
   - Property 16: API Endpoint Behavior
   - Property 17: Streaming Functionality
   - Property 18: Deployment Packaging
   - Property 19: Deployment ID Persistence

3. **Integration Tests**: End-to-end execution flow
   - Full agent execution flow (deployment → execution → result)
   - Concurrent execution throughput
   - SSE streaming format validation
   - Deployment and execution pipeline
   - Graceful fallback to Dramatiq
   - Region enforcement (ap-southeast-2)

## Development

### Adding New Features

1. Update the appropriate adapter class
2. Add configuration options to `config.py`
3. Update environment variables in `.env.example`
4. Add tests to verify functionality
5. Update this README

### Local Development

For local development without AWS credentials:

```bash
# Set environment to local
AGENTCORE_ENVIRONMENT=local

# Disable features that require AWS
AGENTCORE_RUNTIME_ENABLED=false
AGENTCORE_MEMORY_ENABLED=false
AGENTCORE_CODE_INTERPRETER_ENABLED=false
AGENTCORE_BROWSER_ENABLED=false
AGENTCORE_GATEWAY_ENABLED=false

# Enable fallback to legacy systems
AGENTCORE_FALLBACK_TO_DATABASE=true
AGENTCORE_FALLBACK_TO_LEGACY_SANDBOX=true
```

## Migration Path

This module is designed to support gradual migration from the existing platform:

1. **Phase 1**: Install and configure AgentCore SDK (this task)
2. **Phase 2**: Implement Runtime adapter for agent execution
3. **Phase 3**: Migrate Code Interpreter for sandbox operations
4. **Phase 4**: Integrate Memory for conversation storage
5. **Phase 5**: Add Browser for web automation
6. **Phase 6**: Deploy Gateway for MCP integration

Each phase can be enabled/disabled independently using feature flags.

## Troubleshooting

### Configuration Errors

**Error**: `AWS credentials required for production environment`
- **Solution**: Set `AGENTCORE_AWS_ACCESS_KEY_ID` and `AGENTCORE_AWS_SECRET_ACCESS_KEY`

**Error**: `S3 bucket name required when Code Interpreter or Browser is enabled`
- **Solution**: Set `AGENTCORE_S3_BUCKET_NAME` or disable the features

### Runtime Errors

**Error**: `AgentCore Runtime is not enabled`
- **Solution**: Set `AGENTCORE_RUNTIME_ENABLED=true` or enable in config

**Error**: `Failed to deploy agent`
- **Solution**: Check AWS credentials and permissions, verify AgentCore service availability

### Testing Errors

**Error**: `ModuleNotFoundError: No module named 'backend'`
- **Solution**: Use relative imports (`from core.agentcore import ...`)

## Resources

- [AWS Bedrock AgentCore Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/agents.html)
- [Kortix Platform Documentation](../../../README.md)
- [Migration Design Document](../../../.kiro/specs/agentcore-migration/design.md)
- [Implementation Tasks](../../../.kiro/specs/agentcore-migration/tasks.md)

## License

Apache-2.0 - See LICENSE file for details
