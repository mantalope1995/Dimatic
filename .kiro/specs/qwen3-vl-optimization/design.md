# Design Document

## Overview

This design document outlines the technical architecture for optimizing Suna to use Qwen3-VL-235B-A22B-Instruct as the sole LLM provider via SiliconFlow's OpenAI-compatible API. The design focuses on three major changes:

1. **Native Function Calling**: Replace XML-based tool calling with OpenAI-style native function calling
2. **Native Vision**: Leverage Qwen3-VL's multimodal capabilities directly instead of a separate vision tool
3. **Simplified Architecture**: Remove legacy LLM integrations for a clean, single-provider setup

The SiliconFlow API provides full OpenAI compatibility, meaning existing LiteLLM infrastructure can be reused with minimal changes to the routing layer.

## Architecture

### High-Level Architecture

```
+------------------------------------------------------------------+
|                         Suna Agent                                |
+------------------------------------------------------------------+
|  +-------------+  +--------------+  +---------------------------+ |
|  |   Prompt    |  |    Tool      |  |    Response               | |
|  |  Generator  |  |   Registry   |  |    Processor              | |
|  |  (no XML)   |  | (JSON schema)|  |  (native parsing only)    | |
|  +------+------+  +------+-------+  +-----------+---------------+ |
|         |                |                      |                 |
|         +----------------+----------------------+                 |
|                          |                                        |
|                    +-----v-----+                                  |
|                    |  LiteLLM  |                                  |
|                    |  Router   |                                  |
|                    +-----+-----+                                  |
+--------------------------|----------------------------------------+
                           |
                    +------v------+
                    | SiliconFlow |
                    |     API     |
                    +------+------+
                           |
              +------------+------------+
              |            |            |
        +-----v-----+ +----v----+ +-----v-----+
        | Qwen3-VL  | | Qwen3   | |  Qwen3    |
        | 235B-A22B | |Embedding| | Reranker  |
        | (primary) | |(optional)| |(optional) |
        +-----------+ +---------+ +-----------+
```

### Request Flow

1. User message arrives (potentially with images)
2. **Model Router** determines if this is a planning or execution request
3. For complex tasks: Route to **Qwen3-VL-Thinking** for task planning
4. Thinking model creates detailed plan with reasoning_content
5. Plan is stored in conversation context
6. For execution: Route to **Qwen3-VL-Instruct** with plan context
7. Tool Registry provides tools in OpenAI JSON schema format
8. Images are embedded directly in message content array
9. LiteLLM Router sends request to SiliconFlow endpoint
10. Response Processor parses native tool_calls from response
11. Tools execute and results return as tool role messages

### Hybrid Model Strategy

The system uses two model variants with distinct roles:

- **Planning Phase**: `Qwen/Qwen3-VL-235B-A22B-Thinking`
  - Used for initial task analysis and plan creation
  - Captures reasoning_content for transparent decision-making
  - Vision-capable for analyzing images during planning

- **Execution Phase**: `Qwen/Qwen3-VL-235B-A22B-Instruct`
  - Used for tool execution and step-by-step task completion
  - Faster inference without extended reasoning
  - Follows plan created by Thinking model

### Model Router Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    User Message Arrives                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      ModelRouter                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 1. Check conversation context for active_task_plan   │    │
│  │ 2. If no plan exists → PLANNING phase                │    │
│  │ 3. If plan exists → EXECUTION phase                  │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│   PLANNING PHASE        │     │   EXECUTION PHASE       │
│   Qwen3-VL-Thinking     │     │   Qwen3-VL-Instruct     │
│                          │     │                          │
│ • Analyze user request   │     │ • Read plan from context │
│ • Create structured plan │     │ • Execute current step   │
│ • Store plan in context  │     │ • Call tools as needed   │
│ • Return reasoning       │     │ • Mark steps complete    │
└─────────────────────────┘     └─────────────────────────┘
              │                               │
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│ Store TaskPlan in       │     │ Update plan progress    │
│ conversation context    │     │ Check if more steps     │
└─────────────────────────┘     └─────────────────────────┘
```

### Model Router Decision Logic

```python
class ModelRouter:
    THINKING_MODEL = "Qwen/Qwen3-VL-235B-A22B-Thinking"
    INSTRUCT_MODEL = "Qwen/Qwen3-VL-235B-A22B-Instruct"
    
    def select_model(self, conversation_context: dict) -> str:
        """Select appropriate model based on current phase."""
        
        # Check if there's an active task plan
        active_plan = conversation_context.get("active_task_plan")
        
        if active_plan is None:
            # No plan exists - need planning phase
            return self.THINKING_MODEL
        
        if self._plan_is_complete(active_plan):
            # Plan complete, new request needs new plan
            return self.THINKING_MODEL
        
        # Plan exists and has remaining steps - execute
        return self.INSTRUCT_MODEL
    
    def _plan_is_complete(self, plan: TaskPlan) -> bool:
        """Check if all plan steps are marked complete."""
        return all(step.status == "complete" for step in plan.steps)
```

### Task Plan Data Model

```python
@dataclass
class TaskStep:
    id: str                          # Unique step identifier
    description: str                 # What this step accomplishes
    status: str = "pending"          # pending | in_progress | complete | failed
    tools_to_use: List[str] = None   # Suggested tools for this step
    dependencies: List[str] = None   # Step IDs that must complete first
    result: Optional[str] = None     # Output from step execution

@dataclass
class TaskPlan:
    id: str                          # Unique plan identifier
    original_request: str            # User's original message
    reasoning: str                   # Thinking model's reasoning_content
    steps: List[TaskStep]            # Ordered list of steps
    current_step_index: int = 0      # Which step is being executed
    created_at: datetime             # When plan was created
    status: str = "active"           # active | complete | abandoned
```

### Conversation Context Storage

The task plan is stored in the conversation's metadata, persisted to the database:

```python
# In ThreadManager or conversation context
conversation_context = {
    "active_task_plan": {
        "id": "plan_abc123",
        "original_request": "Research competitors and create a report",
        "reasoning": "This task requires multiple steps: 1) identify competitors...",
        "steps": [
            {"id": "step_1", "description": "Search for competitor companies", "status": "complete"},
            {"id": "step_2", "description": "Gather data on each competitor", "status": "in_progress"},
            {"id": "step_3", "description": "Compile findings into report", "status": "pending"}
        ],
        "current_step_index": 1,
        "status": "active"
    }
}
```

### Planning Phase Flow

1. User sends a new message (no active plan)
2. ModelRouter selects Thinking model
3. System prompt instructs Thinking model to:
   - Analyze the request complexity
   - Break down into discrete steps
   - Output structured plan in JSON format
4. Response processor extracts plan from `reasoning_content`
5. Plan is stored in conversation context
6. First step begins execution with Instruct model

### Execution Phase Flow

1. User message arrives (or auto-continue after tool execution)
2. ModelRouter detects active plan → selects Instruct model
3. System prompt includes:
   - The full task plan
   - Current step to execute
   - Results from previous steps
4. Instruct model executes current step (may call tools)
5. Step result is recorded in plan
6. If more steps remain → continue with Instruct
7. If all steps complete → plan marked complete

### Plan Injection into System Prompt

When executing with Instruct model, the plan context is injected:

```
=== ACTIVE TASK PLAN ===
Original Request: {original_request}

Plan Steps:
1. [COMPLETE] {step_1_description}
   Result: {step_1_result}
2. [IN PROGRESS] {step_2_description}  ← YOU ARE HERE
3. [PENDING] {step_3_description}

Focus on completing step 2. Use the available tools as needed.
=== END TASK PLAN ===
```

### Edge Cases

| Scenario | Handling |
|----------|----------|
| User sends new message mid-plan | Abandon current plan, create new plan for new request |
| Step fails repeatedly | Mark step failed, Thinking model creates recovery plan |
| Simple request (no planning needed) | Instruct model handles directly (single-step plan) |
| User explicitly asks to continue | Resume from current step with Instruct model |

## Components and Interfaces

### 1. Model Registry (backend/core/ai_models/registry.py)

Simplified to register only Qwen3-VL-235B-A22B-Instruct.

Interface:
- get_model() -> Model: Returns the single registered model
- get_litellm_params(**overrides) -> Dict: Returns LiteLLM-compatible parameters
- resolve_model_id(alias: str) -> str: Always returns Qwen3-VL model ID

### 2. LLM Service (backend/core/services/llm.py)

Updated to route all requests to SiliconFlow.

Interface:
- make_llm_api_call(messages, tools, stream, ...) -> Response: Main entry point
- setup_provider_router(): Initializes LiteLLM router with SiliconFlow config

### 3. Response Processor (backend/core/agentpress/response_processor.py)

Simplified to handle only native function calling with config:
- xml_tool_calling: False (disabled)
- native_tool_calling: True (always enabled)

Interface:
- process_streaming_response(llm_response, ...) -> AsyncGenerator
- _parse_native_tool_calls(response) -> List[ToolCall]
- _execute_tool(tool_call) -> ToolResult

### 4. Tool Registry (backend/core/agentpress/tool_registry.py)

Updated to output only OpenAI function schema format.

### 5. Native Tool Parser (backend/core/agentpress/native_tool_parser.py)

Handles parsing of OpenAI-style tool calls from responses.

### 6. Vision Message Handler (New Component)

Handles embedding images directly in messages for Qwen3-VL's native vision.

### 7. Embedding Service (Optional)

Qwen3-Embedding integration for semantic search.

### 8. Reranker Service (Optional)

Qwen3-Reranker integration for improved retrieval.


## Data Models

### ToolCall
```python
@dataclass
class ToolCall:
    id: str                      # Unique identifier from LLM
    function_name: str           # Name of function to call
    arguments: Dict[str, Any]    # Parsed JSON arguments
    source: str = "native"       # Always "native" for this implementation
```

### ToolResult
```python
@dataclass
class ToolResult:
    tool_call_id: str           # Matches the ToolCall.id
    success: bool               # Whether execution succeeded
    content: Any                # Result content (will be JSON serialized)
    error: Optional[str] = None # Error message if failed
```

### ModelConfig
```python
@dataclass
class ModelConfig:
    model_id: str = "Qwen/Qwen3-VL-235B-A22B-Instruct"
    api_base: str = "https://api.siliconflow.cn/v1"
    api_key: Optional[str] = None
    context_window: int = 262144
    max_output_tokens: int = 262144
    default_min_pixels: int = 512 * 32 * 32
    default_max_pixels: int = 2048 * 32 * 32
    tool_choice: str = "auto"
```

### StreamingChunk
```python
@dataclass
class StreamingChunk:
    content: Optional[str] = None
    tool_call_delta: Optional[Dict] = None
    finish_reason: Optional[str] = None
    usage: Optional[Dict] = None
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Tool schema conversion preserves semantics
*For any* tool definition with name, description, and parameters, converting to OpenAI function schema format and back should preserve all semantic information.
**Validates: Requirements 2.1**

### Property 2: Native tool call parsing extracts all fields
*For any* valid OpenAI-format tool call response containing id, function name, and arguments, parsing should extract all three fields correctly.
**Validates: Requirements 2.3, 2.4**

### Property 3: Tool result formatting maintains ID consistency
*For any* tool execution result paired with a tool_call_id, the formatted tool message should contain the exact same tool_call_id.
**Validates: Requirements 2.5**

### Property 4: Streaming tool call assembly produces complete calls
*For any* sequence of streaming chunks containing partial tool call data, assembling them should produce a complete tool call equivalent to non-streaming.
**Validates: Requirements 2.6, 11.2**

### Property 5: Image encoding produces valid data URLs
*For any* valid image (bytes or file path), encoding should produce a valid base64 data URL that can be decoded back to the original image data.
**Validates: Requirements 4.2**

### Property 6: Multi-image messages include all images
*For any* set of N images (within model limits), the formatted message content array should contain exactly N image entries plus one text entry.
**Validates: Requirements 4.4**

### Property 7: JSON argument parsing preserves structure
*For any* valid JSON string containing nested objects and arrays, parsing should produce a Python dict/list structure that serializes back to equivalent JSON.
**Validates: Requirements 12.1, 12.2**

### Property 8: Model selection always returns Qwen3-VL
*For any* model selection request regardless of tier or alias, the system should return the Qwen3-VL-235B-A22B-Instruct model configuration.
**Validates: Requirements 9.2**

### Property 9: API routing targets SiliconFlow endpoint
*For any* LLM request, the request URL should be the SiliconFlow API base URL.
**Validates: Requirements 1.2, 9.4**

### Property 10: Error responses produce descriptive messages
*For any* SiliconFlow API error response, parsing should extract a human-readable error message.
**Validates: Requirements 10.1**

### Property 11: Streaming yields chunks in order
*For any* streaming response, content chunks should be yielded in the same order they are received.
**Validates: Requirements 11.1**

### Property 12: Embedding vectors have correct dimensions
*For any* text input to the embedding service, the returned vector should have the dimension specified by the model.
**Validates: Requirements 6.2**

### Property 13: Reranker returns scores for all documents
*For any* query and list of N documents, reranking should return exactly N scores.
**Validates: Requirements 7.4**

### Property 14: Hybrid model routing selects correct variant
*For any* request, planning requests should route to Thinking variant and execution requests should route to Instruct variant.
**Validates: Requirements 9.2, 9.5**

## Error Handling

### API Errors

| Error Type | HTTP Code | Handling Strategy |
|------------|-----------|-------------------|
| Invalid API Key | 401 | Log error, prevent startup |
| Rate Limited | 429 | Exponential backoff, max 5 retries |
| Context Too Long | 400 | Truncate oldest messages, retry |
| Server Error | 5xx | Retry with backoff, max 3 retries |
| Timeout | - | Retry once with extended timeout |
| Malformed Response | - | Log error, graceful failure |

### Tool Execution Errors

1. Catch exception during tool execution
2. Format error as tool result with success=False
3. Return error message to LLM for retry or alternative
4. Log error for debugging

### Streaming Errors

- Stream breaks mid-response: Save partial content, notify user
- Tool call incomplete: Discard partial, continue with text
- Connection lost: Attempt reconnection once, then fail gracefully

## Reference Implementation: Qwen-Agent

The `qwen-agent/Qwen-Agent/` directory contains Alibaba's official agent framework for Qwen models. The following components should be adapted for Suna's implementation:

### High Priority - Adapt Directly

#### 1. Native Function Calling Format
**Source:** `qwen_agent/llm/fncall_prompts/nous_fncall_prompt.py`

The Nous prompt format is the standard for Qwen3-VL function calling:

```python
FN_CALL_TEMPLATE = """# Tools

You may call one or more functions to assist with the user query.

You are provided with function signatures within <tools></tools> XML tags:
<tools>
{tool_descs}
</tools>

For each function call, return a json object with function name and arguments within <tool_call></tool_call> XML tags:
<tool_call>
{"name": <function-name>, "arguments": <args-json-object>}
</tool_call>"""
```

Key patterns to adapt:
- `preprocess_fncall_messages()` - Converts messages to function calling format
- `postprocess_fncall_messages()` - Parses `<tool_call>` responses back to structured data
- `thought_in_content` parameter - For parsing `<think>...</think>` blocks from reasoning models
- `extract_fn()` - Robust extraction of function name/args from partial responses

**Use in Tasks:** 4.1, 4.2, 4.4

#### 2. Vision Message Handling
**Source:** `qwen_agent/llm/qwenvl_oai.py`

```python
@staticmethod
def convert_messages_to_dicts(messages: List[Message]) -> List[dict]:
    # Converts multimodal messages to OpenAI vision format
    for item in content:
        t, v = item.get_type_and_value()
        if t == 'image':
            new_content.append({'type': 'image_url', 'image_url': {'url': v}})
```

Key patterns to adapt:
- `convert_messages_to_dicts()` - Formats messages with images for API
- `conv_multimodel_value()` - Handles file://, http://, and base64 encoding
- `encode_image_as_base64()` - With `max_short_side_length` parameter

**Use in Tasks:** 7.1, 7.4

#### 3. Thinking Model Integration
**Source:** `examples/assistant_qwq.py`

```python
llm_cfg = {
    'model': 'qwq-32b',
    'generate_cfg': {
        'fncall_prompt_type': 'nous',
        'thought_in_content': True,  # For models without reasoning_content field
    },
}
```

Key patterns to adapt:
- `reasoning_content` field handling in responses
- `thought_in_content` parsing for `<think>` blocks
- Integration with function calling for reasoning models

**Use in Tasks:** 11.1, 11.8

### Medium Priority - Reference Patterns

#### 4. Router Agent Pattern
**Source:** `qwen_agent/agents/router.py`

```python
ROUTER_PROMPT = '''你有下列帮手：
{agent_descs}

当你可以直接回答用户时，请忽略帮手，直接回复；但当你的能力无法达成用户的请求时，请选择其中一个来帮你回答'''
```

Key patterns to reference:
- Stop word-based routing detection (`'stop': ['Reply:', 'Reply:\n']`)
- Agent handoff with context preservation
- `supplement_name_special_token()` for tracking agent responses

**Use in Tasks:** 11.2, 11.3

#### 5. MCP Manager Improvements
**Source:** `qwen_agent/tools/mcp_manager.py`

Key patterns to reference:
- Singleton pattern with async event loop in separate thread
- Auto-reconnection on session timeout (`send_ping()` health check)
- Clean process cleanup with `atexit` and signal handlers
- Resource listing and reading support

**Use in Tasks:** Compare with existing Suna MCP implementation

#### 6. FnCallAgent Loop
**Source:** `qwen_agent/agents/fncall_agent.py`

```python
while True and num_llm_calls_available > 0:
    num_llm_calls_available -= 1
    output_stream = self._call_llm(messages=messages, functions=[...])
    # ... detect tool, execute, append result
    if not used_any_tool:
        break
```

Key patterns to reference:
- `MAX_LLM_CALL_PER_RUN` limit for safety
- Tool detection with `_detect_tool()`
- Memory integration for file handling

**Use in Tasks:** Reference for agent run loop improvements

### Low Priority - Optional Enhancements

#### 7. Retrieval Tool (RAG)
**Source:** `qwen_agent/tools/retrieval.py`

Key patterns for Qwen3-Embedding/Reranker integration:
- Hybrid search (BM25 + semantic)
- `max_ref_token` for context limits
- Document parsing pipeline

**Use in Tasks:** 15, 16

#### 8. Code Interpreter Patterns
**Source:** `qwen_agent/tools/code_interpreter.py`

Key patterns to reference:
- Jupyter kernel lifecycle management
- Timeout handling with countdown timer
- Cross-platform event loop handling (`AnyThreadEventLoopPolicy`)

**Use in Tasks:** Compare with e2b code interpreter

#### 9. Tool Base Class
**Source:** `qwen_agent/tools/base.py`

Key patterns to reference:
- `@register_tool` decorator pattern
- `is_tool_schema()` validation function
- `BaseToolWithFileAccess` for file-handling tools

**Use in Tasks:** Reference for tool registry improvements

### File Reference Summary

| Component | Source File | Suna Target | Priority |
|-----------|-------------|-------------|----------|
| Function calling prompt | `llm/fncall_prompts/nous_fncall_prompt.py` | `agentpress/native_tool_parser.py` | High |
| Vision message handling | `llm/qwenvl_oai.py` | `agentpress/vision_handler.py` (new) | High |
| Thinking model config | `examples/assistant_qwq.py` | `ai_models/registry.py` | High |
| Router pattern | `agents/router.py` | `agentpress/model_router.py` (new) | Medium |
| MCP improvements | `tools/mcp_manager.py` | `mcp_module/` | Medium |
| Agent loop | `agents/fncall_agent.py` | `run.py` | Medium |
| RAG/Retrieval | `tools/retrieval.py` | `services/qwen_embedding.py` | Low |
| Code interpreter | `tools/code_interpreter.py` | Compare with e2b | Low |

## Testing Strategy

### Dual Testing Approach

- **Unit tests**: Verify specific examples, edge cases, integration points
- **Property-based tests**: Verify universal properties across all valid inputs

### Property-Based Testing Framework

**Framework**: hypothesis (Python)
**Minimum iterations**: 100 per property test

### Test Categories

1. **Tool Schema Tests**: Schema conversion round-trip
2. **Tool Call Parsing Tests**: Native parsing completeness, malformed handling
3. **Streaming Tests**: Chunk assembly, partial buffering
4. **Vision Tests**: Image encoding round-trip, URL passthrough
5. **Integration Tests**: End-to-end flows, error recovery

### Test Annotations

Each property-based test must include:
```python
# **Feature: qwen3-vl-optimization, Property {N}: {property_text}**
# **Validates: Requirements X.Y**
```
