# AWS AgentCore Integration

This module provides integration with AWS Bedrock AgentCore for the Kortix AI agent platform. It includes configuration management and adapter classes for all AgentCore primitives.

## Overview

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
AGENTCORE_AWS_REGION=us-east-1
AGENTCORE_AWS_ACCESS_KEY_ID=your-access-key
AGENTCORE_AWS_SECRET_ACCESS_KEY=your-secret-key

# Feature Flags (default: true)
AGENTCORE_RUNTIME_ENABLED=true
AGENTCORE_MEMORY_ENABLED=true
AGENTCORE_CODE_INTERPRETER_ENABLED=true
AGENTCORE_BROWSER_ENABLED=true
AGENTCORE_GATEWAY_ENABLED=true

# S3 Configuration (required for Code Interpreter and Browser)
AGENTCORE_S3_BUCKET_NAME=your-bucket-name
AGENTCORE_S3_BUCKET_REGION=us-east-1

# Timeouts (in seconds)
AGENTCORE_RUNTIME_TIMEOUT_SECONDS=300
AGENTCORE_CODE_INTERPRETER_TIMEOUT_SECONDS=30
AGENTCORE_BROWSER_TIMEOUT_SECONDS=60
AGENTCORE_GATEWAY_TIMEOUT_SECONDS=30

# Fallback Configuration
AGENTCORE_FALLBACK_TO_DATABASE=true
AGENTCORE_FALLBACK_TO_LEGACY_SANDBOX=false
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

### AgentCore Runtime

Deploy and invoke agents using AgentCore Runtime:

```python
from core.agentcore import AgentCoreRuntimeAdapter

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
    thread_id="thread-123",
    input_data={"message": "Hello"},
    stream=True
):
    print(response)

# Cancel execution
await runtime.cancel_execution(execution_id="exec-123")

# Get execution status
status = await runtime.get_execution_status(execution_id="exec-123")
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
├── __init__.py              # Module exports
├── config.py                # Configuration management
├── adapters/
│   ├── __init__.py
│   ├── runtime.py           # Runtime adapter
│   ├── memory.py            # Memory adapter
│   ├── code_interpreter.py  # Code Interpreter adapter
│   ├── browser.py           # Browser adapter
│   └── gateway.py           # Gateway adapter
├── tests/
│   ├── __init__.py
│   ├── test_config.py       # Configuration tests
│   └── test_adapters.py     # Adapter tests
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
# Run all tests
uv run pytest core/agentcore/tests/ -v

# Run specific test file
uv run pytest core/agentcore/tests/test_config.py -v

# Run with coverage
uv run pytest core/agentcore/tests/ --cov=core.agentcore --cov-report=html
```

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
