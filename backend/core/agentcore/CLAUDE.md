# CLAUDE.md - AgentCore Migration Guide

This file provides guidance for Claude Code when working with the AWS Bedrock AgentCore migration in the Kortix platform.

## Quick Start

### What is AgentCore?

AWS Bedrock AgentCore is a serverless platform for AI agents that provides managed primitives:

- **Runtime**: Serverless agent deployment with fast cold starts and automatic scaling
- **Memory**: Event and semantic memory with cross-agent sharing capabilities
- **Code Interpreter**: Secure code execution in isolated sandboxes (Python/JavaScript)
- **Browser**: Cloud-based Chrome automation with Playwright/CDP support
- **Gateway**: MCP (Model Context Protocol) server integration

### Why Migrate?

The Kortix platform currently uses:
- **Daytona** for sandboxed code execution (third-party service)
- **Stagehand** for browser automation

Phase 1 replaces Daytona+Stagehand with AgentCore Code Interpreter+Browser to:
- Reduce vendor lock-in
- Improve cold start performance
- Better integrate with AWS ecosystem
- Enable cross-agent memory sharing
- Simplify credential management

## Migration Status

### Current Progress

| Migration | Tasks Complete | Progress |
|-----------|----------------|----------|
| **Phase 1** (Runtime Integration) | 15 / 15 | **100%** ✅ |
| **Phase 2** (Code Interpreter & Browser) | 15 / 15 | **100%** ✅ |
| **Phase 4** (Memory Integration) | 15 / 15 | **100%** ✅ |
| **Phase 5** (MCP Integration) | 8 / 8 | **100%** ✅ |
| **Phase 6** (ThreadManager & Tool Registry) | 4 / 4 | **100%** ✅ |
| **Full Migration** (Complete Platform) | 57 / 77 | ~74% |

### Completed Phases

#### Phase 1: Runtime Integration (100% Complete)
- AgentCore SDK integration (boto3 dependency, config.py)
- Runtime Adapter implementation (deploy_agent, invoke_agent, cancel_execution)
- Execution Manager with SSE streaming
- Deployment automation with rollback support
- Integration tests and property tests (7 properties)

#### Phase 2: Code Interpreter & Browser (100% Complete)
- Code Interpreter Adapter (execute_code, execute_shell_command, file operations)
- Browser Adapter (navigate, extract_content, fill_form, screenshot)
- Property tests (Properties 1-6, 9-17)
- Integration tests and fallback verification

#### Phase 4: Memory Integration (100% Complete)
- Memory Adapter Implementation (create_memory_resource, store_message, retrieve_messages)
- ThreadManager Memory Integration (create Memory on thread creation)
- Memory cleanup on thread deletion
- Property tests (Properties 7, 8, 20, 24)

#### Phase 5: MCP Integration (100% Complete)
- Gateway Adapter Implementation (deploy_mcp_server, invoke_mcp_tool, list_tools)
- OAuth flow management (generate_auth_url, exchange_code_for_tokens, refresh_tokens)
- MCP catalog and deployment tracking (DynamoDB tables, CRUD operations)
- Tool discovery and registration (list_mcp_tools, register_tool_with_gateway)
- Credential management (Secrets Manager integration, OAuth token storage)
- MCP server deployment automation (deploy_server, update_config, delete_deployment)
- Property tests (Properties 21-24: OAuth flow, credential storage, server deployment)
- Integration tests (end-to-end MCP tool execution via Gateway)

#### Phase 6: ThreadManager & Tool Registry (100% Complete)
- Tool Registry Service (centralized tool discovery and metadata management)
- ThreadManager Runtime Integration (create Runtime deployment on thread creation)
- Tool Execution Coordination (unified execute() path via Runtime with fallback)
- Integration tests and verification (end-to-end flows, tool registry discovery)

### Remaining Work

**Advanced Features and Optimization** (~20 remaining tasks):

- **Phase 3**: Enhanced error handling and retry strategies
- **Phase 7**: Performance optimization and caching
- **Phase 8**: Multi-region deployment support
- **Phase 9**: Advanced monitoring and observability
- **Phase 10**: Security hardening and compliance
- **Phase 11**: Documentation and training materials
- **Phase 12**: Production readiness checklist

## Phase 6: ThreadManager & Tool Registry (Complete)

Phase 6 integrates AgentCore Runtime and Tool Registry with ThreadManager for centralized tool discovery, execution, and lifecycle management.

### Key Components

1. **Tool Registry Service** (`registry/tool_registry.py`)
   - Centralized tool discovery and metadata management
   - Tool registration with AgentCore Runtime
   - Category-based filtering (browser, code_interpreter, mcp, file_ops)

2. **ThreadManager Runtime Integration**
   - Automatic Runtime deployment creation on thread creation
   - Tool registration with Runtime deployment
   - Runtime deployment ID stored in threads table
   - Graceful cleanup on thread deletion

3. **Tool Execution Coordination**
   - Unified `execute()` path via Runtime
   - Automatic fallback to local execution when Runtime unavailable
   - Result aggregation and streaming
   - Error handling and retry logic

### Usage Examples

```python
from core.agentcore import ToolRegistry, ToolMetadata
from core.agentpress import ThreadManager

# Initialize tool registry
registry = ToolRegistry()

# Discover tools
tools = await registry.discover_tools(tool_package="core.tools")

# ThreadManager with Runtime auto-deployment
manager = ThreadManager(account_id="account-456")
thread_id = await manager.create_thread(runtime_enabled=True)

# Execute tool via Runtime (with automatic fallback)
result = await manager.execute_tool(
    tool_name="web_search",
    arguments={"query": "AWS AgentCore"},
    thread_id=thread_id
)
```

### Database Schema

Phase 6 adds `runtime_deployment_id` and `runtime_metadata` columns to the threads table:

```sql
ALTER TABLE threads
ADD COLUMN runtime_deployment_id TEXT,
ADD COLUMN runtime_metadata JSONB DEFAULT '{}'::jsonb;

CREATE INDEX idx_threads_runtime_deployment_id ON threads(runtime_deployment_id);
```

### Testing

- **Unit Tests**: `test_tool_registry.py` - Tool registration, discovery, metadata management
- **Integration Tests**: `test_integration_phase6.py` - End-to-end Runtime tool execution
- **Property Tests**: Tool discovery, metadata consistency, execution fallback

## Architecture Overview

### Component Relationships

```
┌─────────────────────────────────────────────────────────────────┐
│                         Agent Tools                             │
│  (BrowserTool, FileWriteTool, PythonTool, etc.)                 │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SandboxToolsBase                             │
│  _ensure_sandbox() → backend selection logic                    │
└────────────────────────────┬────────────────────────────────────┘
                             │
                    ┌────────┴────────┐
                    ▼                 ▼
┌──────────────────────────┐  ┌──────────────────────────┐
│   AgentCore Adapter      │  │   Legacy Daytona        │
│  (CodeInterpreter,        │  │   (Fallback)            │
│   Browser)               │  │                          │
└───────────┬──────────────┘  └──────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────┐
│              AWS Bedrock AgentCore (ap-southeast-2)              │
│  Code Interpreter Sessions  │  Browser Sessions                  │
└─────────────────────────────────────────────────────────────────┘
```

### Adapter Pattern

Each AgentCore primitive has an adapter class in `adapters/`:

```python
class AgentCoreCodeInterpreterAdapter:
    """Wraps bedrock_agentcore.tools.code_interpreter_client.CodeInterpreter"""

    async def execute_code(self, code: str, language: str, ...) -> dict:
        # TODO: Call AgentCore Code Interpreter API

    async def execute_shell_command(self, command: str, ...) -> dict:
        # TODO: Call AgentCore shell API
```

## Key Requirements

### Region Requirement (Phase 1)

**CRITICAL**: All AgentCore services for Phase 1 MUST run in `ap-southeast-2` (Australia).

This requirement comes from:
- Latency targets for Australian users
- Data residency requirements
- Cost optimization for the region

```python
# CORRECT: Region is ap-southeast-2
config = AgentCoreConfig(
    environment=Environment.PRODUCTION,
    aws_region="ap-southeast-2"  # Required for Phase 1
)

# INCORRECT: Default us-east-1 is not acceptable for Phase 1
config = AgentCoreConfig(
    environment=Environment.PRODUCTION,
    aws_region="us-east-1"  # Wrong region!
)
```

### Feature Flags

AgentCore components can be enabled/disabled independently:

```bash
# Enable only Code Interpreter (disable Browser for now)
AGENTCORE_CODE_INTERPRETER_ENABLED=true
AGENTCORE_BROWSER_ENABLED=false
AGENTCORE_MEMORY_ENABLED=false
AGENTCORE_RUNTIME_ENABLED=false
AGENTCORE_GATEWAY_ENABLED=false
```

### Fallback Behavior

When AgentCore is unavailable, the system gracefully falls back:

```python
class SandboxToolsBase(Tool):
    async def _ensure_sandbox(self):
        if self._use_agentcore():
            try:
                return await self._ensure_agentcore_session()
            except Exception as e:
                logger.warning(f"AgentCore unavailable: {e}")
                if self.config.fallback_to_legacy_sandbox:
                    return await self._ensure_daytona_sandbox()
        return await self._ensure_daytona_sandbox()
```

## File Reference

### Specification Files

| File | Purpose |
|------|---------|
| `.kiro/specs/agentcore-phase1-migration/design.md` | Phase 1 architecture and design decisions |
| `.kiro/specs/agentcore-phase1-migration/requirements.md` | 23 requirements for Phase 1 |
| `.kiro/specs/agentcore-phase1-migration/tasks.md` | 15 implementation tasks with checkpoints |
| `.kiro/specs/agentcore-migration/design.md` | Full migration design (77 tasks) |
| `.kiro/specs/agentcore-migration/requirements.md` | 20 major requirements for full migration |
| `.kiro/specs/agentcore-migration/tasks.md` | All 77 tasks across 12 phases |

### Implementation Files

| File | Status | Notes |
|------|--------|-------|
| `config.py` | ✅ Complete | Configuration with environment variable parsing |
| `adapters/code_interpreter.py` | 🔶 Stubs | Methods have TODO comments, need implementation |
| `adapters/browser.py` | 🔶 Stubs | Methods have TODO comments, need implementation |
| `adapters/memory.py` | 🔶 Stubs | Not in Phase 1 scope |
| `adapters/runtime.py` | 🔶 Stubs | Not in Phase 1 scope |
| `adapters/gateway.py` | 🔶 Stubs | Not in Phase 1 scope |
| `tests/test_config.py` | ✅ Basic | Tests for configuration loading |
| `tests/test_adapters.py` | 🔶 Basic | Adapter tests are mocks, need real tests |
| `README.md` | 🔶 Basic | Needs CLAUDE.md cross-reference |

## Development Workflow

### Working on a Task

1. **Read the task definition** in `.kiro/specs/agentcore-phase1-migration/tasks.md`
2. **Identify files to modify** using the File Reference section above
3. **Check for AWS documentation** needs (see AWS Context below)
4. **Implement the feature** following existing patterns
5. **Add tests** (unit tests + property tests)
6. **Update task status** in tasks.md (mark with `[x]` when done)

### Example: Implementing Code Interpreter Adapter

```bash
# 1. Read the task
# Task 5.1: Create AgentCoreCodeInterpreterAdapter class

# 2. File to modify: adapters/code_interpreter.py
# The adapter class already exists, need to implement the TODO methods

# 3. AWS SDK pattern
from bedrock_agentcore.tools.code_interpreter_client import CodeInterpreter

# 4. Implementation
client = CodeInterpreter(region_name="ap-southeast-2")
session = client.create_session(timeout_in_seconds=30)
result = session.execute_code(code="print('hello')")

# 5. Add tests to tests/test_adapters.py

# 6. Mark task as complete in tasks.md
```

### Testing Before Committing

```bash
# Run all AgentCore tests
cd backend
uv run pytest core/agentcore/tests/ -v

# Run specific test file
uv run pytest core/agentcore/tests/test_config.py -v

# Run with coverage
uv run pytest core/agentcore/tests/ --cov=core.agentcore --cov-report=html
```

## Testing Strategy

### Test Types

1. **Unit Tests**: Specific examples and edge cases
   - Fast, no external dependencies
   - Mock AWS SDK calls

2. **Property Tests**: Universal correctness properties
   - Uses Hypothesis framework
   - Tests invariants across many generated inputs

3. **Integration Tests**: Requires AWS credentials
   - Real AWS API calls to ap-southeast-2
   - Marked with `@pytest.mark.integration`

### Property-Based Tests (Phase 1)

Phase 1 requires 18 property-based tests defined in the spec:

| Property | Description |
|----------|-------------|
| Region enforcement | All AgentCore calls use ap-southeast-2 |
| Session round-trip | Session state survives serialization |
| Backend selection | Backend choice is deterministic and consistent |
| Retry transient failures | Retry logic for 500/503 errors |
| Sensitive data redaction | Credentials redacted from logs |
| WebSocket URL generation | URLs are valid and reachable |
| Result structure completeness | All required fields present in results |
| ... | (12 more properties in spec) |

Example property test:

```python
from hypothesis import given, strategies as st

@given(st.text(min_size=1))
def test_region_enforcement_for_code_execution(code: str):
    """Property: All code execution uses ap-southeast-2 region"""
    adapter = AgentCoreCodeInterpreterAdapter(
        config=AgentCoreConfig(aws_region="ap-southeast-2")
    )
    # Verify region is used in underlying AWS call
    # ...
```

## AWS Context

### AgentCore SDK Documentation

The AgentCore SDK is part of AWS Bedrock but uses a separate client:

```python
# Code Interpreter
from bedrock_agentcore.tools.code_interpreter_client import CodeInterpreter

# Browser (WebSocket API)
from bedrock_agentcore.tools.browser_client import BrowserClient
import websockets

# Memory
from bedrock_agentcore.tools.memory_client import MemoryClient

# Runtime
from bedrock_agentcore.runtime_client import RuntimeClient

# Gateway
from bedrock_agentcore.gateway_client import GatewayClient
```

### SDK Usage Patterns

#### Code Interpreter Session

```python
from bedrock_agentcore.tools.code_interpreter_client import CodeInterpreter

# Initialize with region
client = CodeInterpreter(
    region_name="ap-southeast-2",  # CRITICAL for Phase 1
    aws_access_key_id=config.aws_access_key_id,
    aws_secret_access_key=config.aws_secret_access_key
)

# Create session
session = client.create_session(
    timeout_in_seconds=30,
    memory_limit_in_mb=1024
)

# Execute code
response = session.execute_code(
    code="print('Hello, Australia!')",
    language="python"
)

# Get output
print(response["output"])

# Clean up
session.delete()
```

#### Browser Session (WebSocket)

```python
import websockets
import asyncio

async def browser_session():
    # Connect to browser WebSocket in ap-southeast-2
    ws_url = f"wss://agentcore-browser-ap-southeast-2.amazonaws.com/v1/sessions"

    async with websockets.connect(ws_url) as ws:
        # Create session
        await ws.send_json({
            "action": "create",
            "config": {
                "timeout_in_seconds": 60,
                "headless": True
            }
        })

        # Navigate
        await ws.send_json({
            "action": "navigate",
            "url": "https://example.com"
        })

        # Get result
        result = await ws.recv_json()
        print(result["html"])

        # Close session
        await ws.send_json({"action": "close"})
```

### Error Handling Patterns

```python
import botocore.exceptions
from tenacity import retry, stop_after_attempt, wait_exponential

class AgentCoreError(Exception):
    """Base exception for AgentCore errors"""
    pass

class TransientError(AgentCoreError):
    """Retryable transient errors"""
    pass

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10)
)
async def call_agentcore_with_retry(func, *args, **kwargs):
    """Call AgentCore API with retry for transient errors"""
    try:
        return await func(*args, **kwargs)
    except botocore.exceptions.ClientError as e:
        error_code = e.response.get('Error', {}).get('Code')
        if error_code in ['500', '503', 'TooManyRequestsException']:
            raise TransientError(f"Transient error: {e}")
        raise AgentCoreError(f"AgentCore error: {e}")
```

### Relevant AWS Documentation

- [AWS Bedrock AgentCore Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/agents.html)
- [Code Interpreter API Reference](https://docs.aws.amazon.com/bedrock/latest/userguide/code-interpreter.html)
- [Browser Automation API](https://docs.aws.amazon.com/bedrock/latest/userguide/browser.html)
- [Memory Storage API](https://docs.aws.amazon.com/bedrock/latest/userguide/memory.html)

## Common Issues and Solutions

### Issue: "AWS credentials required for production environment"

**Cause**: `environment=Environment.PRODUCTION` but no AWS credentials set

**Solution**:
```bash
export AGENTCORE_AWS_ACCESS_KEY_ID=your-key
export AGENTCORE_AWS_SECRET_ACCESS_KEY=your-secret
```

### Issue: "S3 bucket name required when Code Interpreter is enabled"

**Cause**: Code Interpreter enabled but no S3 bucket configured

**Solution**:
```bash
export AGENTCORE_S3_BUCKET_NAME=your-bucket-name
# or disable Code Interpreter
export AGENTCORE_CODE_INTERPRETER_ENABLED=false
```

### Issue: Import errors for bedrock_agentcore

**Cause**: SDK not installed

**Solution**:
```bash
cd backend
uv sync  # Should install boto3>=1.40.74
```

### Issue: Region mismatch errors

**Cause**: Using wrong region for Phase 1

**Solution**: Ensure all AgentCore calls use `ap-southeast-2`:
```python
config = AgentCoreConfig(aws_region="ap-southeast-2")  # Must be ap-southeast-2
```

## Environment Configuration

### Required Environment Variables

```bash
# Environment
AGENTCORE_ENVIRONMENT=production  # or development, local

# AWS Credentials (for non-local)
AGENTCORE_AWS_REGION=ap-southeast-2  # CRITICAL for Phase 1
AGENTCORE_AWS_ACCESS_KEY_ID=your-key
AGENTCORE_AWS_SECRET_ACCESS_KEY=your-secret

# Feature Flags
AGENTCORE_CODE_INTERPRETER_ENABLED=true
AGENTCORE_BROWSER_ENABLED=true
AGENTCORE_MEMORY_ENABLED=false
AGENTCORE_RUNTIME_ENABLED=false
AGENTCORE_GATEWAY_ENABLED=false

# S3 (required for Code Interpreter and Browser)
AGENTCORE_S3_BUCKET_NAME=kortix-agentcore-files
AGENTCORE_S3_BUCKET_REGION=ap-southeast-2

# Timeouts
AGENTCORE_CODE_INTERPRETER_TIMEOUT_SECONDS=30
AGENTCORE_BROWSER_TIMEOUT_SECONDS=60

# Fallback
AGENTCORE_FALLBACK_TO_DATABASE=true
AGENTCORE_FALLBACK_TO_LEGACY_SANDBOX=false
```

### Local Development (No AWS Credentials)

```bash
AGENTCORE_ENVIRONMENT=local
AGENTCORE_CODE_INTERPRETER_ENABLED=false
AGENTCORE_BROWSER_ENABLED=false
AGENTCORE_FALLBACK_TO_LEGACY_SANDBOX=true
```

## Debugging Tips

### Enable Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
# or specifically for agentcore
logging.getLogger('core.agentcore').setLevel(logging.DEBUG)
```

### Check AWS Configuration

```python
from core.agentcore import get_config
config = get_config()
print(f"Environment: {config.environment}")
print(f"Region: {config.aws_region}")
print(f"Code Interpreter Enabled: {config.code_interpreter_enabled}")
print(f"S3 Bucket: {config.s3_bucket_name}")
```

### Verify Region Enforcement

```python
# In property test
def test_region_enforcement():
    config = get_config()
    assert config.aws_region == "ap-southeast-2", "Phase 1 requires ap-southeast-2"
```

## Progress Tracking

After completing tasks, update the status in:

1. **Phase 1 Tasks**: `.kiro/specs/agentcore-phase1-migration/tasks.md`
2. **Full Migration Tasks**: `.kiro/specs/agentcore-migration/tasks.md`

Mark tasks complete:
```markdown
- [x] 5.1 Create AgentCoreCodeInterpreterAdapter class
- [x] 5.2 Implement execute_code method
```

## Related Documentation

- [Backend CLAUDE.md](../CLAUDE.md) - General backend development guide
- [AgentCore README.md](README.md) - Installation and usage overview
- [Migration Design Doc](../../../../.kiro/specs/agentcore-phase1-migration/design.md)
- [Platform README](../../../../README.md) - Overall Kortix platform docs
