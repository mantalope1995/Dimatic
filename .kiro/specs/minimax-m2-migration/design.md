# Design Document

## Overview

This design document outlines the architecture and implementation approach for migrating the Kortix platform to use Minimax-m2 as the primary language model provider. **The migration leverages the existing LiteLLM integration and makes minimal changes to the working system.** The existing multi-provider infrastructure remains intact, with Minimax-m2 configured as the only enabled model.

### Design Principles

1. **Minimal Changes**: Leverage existing LiteLLM integration; only add Minimax-m2 configuration
2. **Preserve Working Code**: Keep all existing LLM service code unchanged
3. **Configuration Over Code**: Use model registry configuration to enable Minimax-m2
4. **Backward Compatibility**: Maintain support for existing conversations and agents

The key technical changes required:
1. Add Minimax-m2 to the model registry (using existing Model class)
2. Configure LiteLLM to route to Minimax API (LiteLLM already supports Anthropic SDK format)
3. Add thinking block parsing to response processor (minimal addition to existing code)
4. Update vision tool to call understand_image MCP (replace Gemini API call only)
5. Remove model selection UI (frontend only)

## Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend / Mobile App                    │
│  - Remove all model-related UI components                    │
│  - No model display or selection                            │
└────────────────────┬────────────────────────────────────────┘
                     │
                     │ HTTP/WebSocket
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    Backend API (FastAPI)                     │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           Model Manager & Registry                    │  │
│  │  - Register Minimax-m2 (enabled)                     │  │
│  │  - Keep other models (disabled)                      │  │
│  │  - Route all requests to Minimax-m2                  │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              LLM Service Layer                        │  │
│  │  - Format requests (Anthropic SDK)                   │  │
│  │  - Enable interleaved thinking                       │  │
│  │  - Handle streaming responses                        │  │
│  │  - Parse thinking blocks                             │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │            Vision Tool (sb_vision_tool)               │  │
│  │  - Compress images                                    │  │
│  │  - Call understand_image MCP                         │  │
│  │  - Format results for conversation                   │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     │ HTTPS
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                  Minimax API Platform                        │
│  - Anthropic SDK-compatible endpoint                         │
│  - Interleaved thinking support                             │
│  - Function calling (Anthropic format)                      │
└─────────────────────────────────────────────────────────────┘
                     
┌─────────────────────────────────────────────────────────────┐
│              understand_image MCP Server                     │
│  - Image analysis via Minimax                                │
│  - Returns structured analysis                               │
└─────────────────────────────────────────────────────────────┘
```

### Component Interaction Flow

1. **User Request Flow**:
   - User sends message through frontend/mobile app
   - Backend routes to Model Manager
   - Model Manager resolves to Minimax-m2 (only enabled model)
   - LLM Service formats request with Anthropic SDK format
   - Request sent to Minimax API with interleaved thinking enabled

2. **Response Processing Flow**:
   - Minimax returns streaming response with thinking blocks
   - Response Processor parses both thinking and content blocks
   - Thinking blocks displayed/logged separately
   - Content blocks streamed to user
   - Token usage tracked including thinking tokens

3. **Vision Tool Flow**:
   - User requests image analysis
   - Vision tool compresses image (existing logic)
   - Image sent to understand_image MCP server
   - MCP server calls Minimax for analysis
   - Results formatted and added to conversation context

## Components and Interfaces

### 1. Model Registry (`backend/core/ai_models/registry.py`)

**Purpose**: Manage available models and their configurations

**Key Changes**:
- Add Minimax-m2 model definition with `enabled=True`
- Set all other models to `enabled=False`
- Configure Minimax-m2 with Anthropic SDK-compatible settings

**Interface**:
```python
class ModelRegistry:
    def _initialize_models(self):
        # Register Minimax-m2 as enabled
        self.register(Model(
            id="minimax/minimax-m2",
            name="Minimax-m2",
            provider=ModelProvider.MINIMAX,
            aliases=["minimax-m2", "Minimax-m2"],
            context_window=200_000,  # Verify actual limit
            capabilities=[
                ModelCapability.CHAT,
                ModelCapability.FUNCTION_CALLING,
                ModelCapability.THINKING,
            ],
            pricing=ModelPricing(
                input_cost_per_million_tokens=0.60,
                output_cost_per_million_tokens=2.20,
            ),
            tier_availability=["free", "paid"],
            priority=100,
            recommended=True,
            enabled=True,
            config=ModelConfig(
                api_base="https://api.minimax.chat/v1",
                extra_headers={
                    "anthropic-version": "2023-06-01",  # Verify version
                }
            )
        ))
        
        # Keep existing models but set enabled=False
        # ... existing model registrations with enabled=False
```

### 2. LLM Service (`backend/core/services/llm.py`)

**Purpose**: Handle API calls to Minimax with proper formatting

**Key Changes**: **MINIMAL - LiteLLM already handles Anthropic SDK format**
- No changes to `make_llm_api_call` function
- LiteLLM will automatically use Anthropic SDK format based on model config
- Thinking mode configured in model registry (passed through LiteLLM)

**Why No Changes Needed**:
- LiteLLM already supports Anthropic SDK-compatible providers
- Model configuration in registry provides all necessary parameters
- Existing `model_manager.get_litellm_params()` already handles custom headers and API bases
- LiteLLM will automatically format requests based on provider configuration

**Example of how existing code works**:
```python
# Existing code - NO CHANGES NEEDED
async def make_llm_api_call(
    messages: List[Dict[str, Any]],
    model_name: str,
    # ... existing parameters
) -> Union[Dict[str, Any], AsyncGenerator]:
    """Make API call - works for all providers including Minimax."""
    
    # This already gets Minimax config from registry
    params = model_manager.get_litellm_params(model_name)
    
    # LiteLLM automatically handles Anthropic SDK format
    response = await provider_router.acompletion(**params)
    return response
```

### 3. Response Processor (`backend/core/agentpress/response_processor.py`)

**Purpose**: Parse and handle streaming responses with thinking blocks

**Key Changes**: **MINIMAL - Add thinking block handling to existing code**
- The response processor already handles `reasoning_content` from Anthropic (see line 377-385)
- Minimax thinking blocks use the same field name
- Only need to ensure thinking tokens are tracked in usage calculation

**Existing Code Already Handles Thinking**:
```python
# From response_processor.py lines 377-385 - ALREADY EXISTS
if delta and hasattr(delta, 'reasoning_content') and delta.reasoning_content:
    if not has_printed_thinking_prefix:
        has_printed_thinking_prefix = True
    reasoning_content = delta.reasoning_content
    if isinstance(reasoning_content, list):
        reasoning_content = ''.join(str(item) for item in reasoning_content)
    accumulated_content += reasoning_content
```

**Only Addition Needed**:
```python
# In token usage tracking - add thinking token support
if hasattr(chunk, 'usage') and chunk.usage:
    thinking_tokens = getattr(chunk.usage, 'thinking_tokens', 0)
    # Add to existing token tracking
```

### 4. Vision Tool (`backend/core/tools/sb_vision_tool.py`)

**Purpose**: Provide image analysis through understand_image MCP

**Key Changes**:
- Replace Gemini API calls with MCP server calls
- Maintain existing image compression logic
- Format MCP responses for conversation context

**Interface**:
```python
class SandboxVisionTool(SandboxToolsBase):
    async def load_image(self, file_path: str) -> ToolResult:
        """Load and analyze image using understand_image MCP."""
        
        # Existing compression logic (unchanged)
        compressed_bytes, mime_type = await self.compress_image(...)
        
        # Upload to storage (unchanged)
        public_url = await self._upload_to_storage(compressed_bytes)
        
        # Call understand_image MCP instead of Gemini
        analysis = await self._call_understand_image_mcp(public_url)
        
        # Format result for conversation
        return self.success_response({
            "image_url": public_url,
            "analysis": analysis,
            "message": f"Image loaded and analyzed: {file_path}"
        })
    
    async def _call_understand_image_mcp(self, image_url: str) -> str:
        """Call understand_image MCP server for analysis."""
        # MCP server call implementation
        # Format: POST to MCP server with image URL
        # Returns: Structured analysis text
        pass
```

### 5. Configuration (`backend/core/utils/config.py`)

**Purpose**: Store Minimax API credentials and settings

**New Configuration Variables**:
```python
class Config:
    # Minimax API Configuration
    MINIMAX_API_KEY: str = os.getenv("MINIMAX_API_KEY", "")
    MINIMAX_API_BASE: str = os.getenv("MINIMAX_API_BASE", "https://api.minimax.chat/v1")
    MINIMAX_THINKING_MODE: str = os.getenv("MINIMAX_THINKING_MODE", "interleaved")
    
    # understand_image MCP Configuration
    UNDERSTAND_IMAGE_MCP_URL: str = os.getenv("UNDERSTAND_IMAGE_MCP_URL", "")
```

## Data Models

### Minimax Model Definition

```python
@dataclass
class MinimaxModelConfig:
    """Configuration specific to Minimax-m2."""
    model_id: str = "minimax-m2"
    api_base: str = "https://api.minimax.chat/v1"
    thinking_mode: str = "interleaved"
    context_window: int = 200_000
    max_output_tokens: int = 8192
    supports_vision: bool = False  # Vision through MCP only
    supports_function_calling: bool = True
```

### Thinking Block Structure

```python
@dataclass
class ThinkingBlock:
    """Represents a thinking block in the response."""
    content: str
    token_count: int
    timestamp: datetime
    sequence: int  # Order in response
```

### MCP Image Analysis Request

```python
@dataclass
class ImageAnalysisRequest:
    """Request format for understand_image MCP."""
    image_url: str
    analysis_type: str = "general"  # or "detailed", "ocr", etc.
    max_tokens: int = 1000
```

### MCP Image Analysis Response

```python
@dataclass
class ImageAnalysisResponse:
    """Response format from understand_image MCP."""
    analysis: str
    confidence: float
    detected_objects: List[str]
    text_content: Optional[str]  # For OCR
    metadata: Dict[str, Any]
```


## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Model Registry Initialization
*For any* system initialization, the Model Registry should register Minimax-m2 as the only enabled model, while keeping other models registered but disabled.
**Validates: Requirements 1.1, 4.1, 4.2**

### Property 2: Agent Model Assignment
*For any* agent creation or update operation, the system should automatically assign Minimax-m2 as the model, regardless of any model parameter provided in the request.
**Validates: Requirements 1.2, 1.4**

### Property 3: Request Routing
*For any* LLM service request, the system should route the request to Minimax-m2, regardless of which model ID is specified in the agent configuration.
**Validates: Requirements 1.4, 4.4**

### Property 4: Interleaved Thinking Configuration
*For any* API call to Minimax-m2, the request parameters should include the thinking mode set to "interleaved".
**Validates: Requirements 2.1, 2.2**

### Property 5: Thinking Block Parsing
*For any* streaming response from Minimax-m2 containing thinking blocks, the system should correctly parse and separate thinking content from regular content.
**Validates: Requirements 2.3, 2.4**

### Property 6: Token Usage Calculation
*For any* response from Minimax-m2, the total token count should include both regular tokens and thinking tokens in the cost calculation.
**Validates: Requirements 2.5, 8.5**

### Property 7: Anthropic SDK Message Formatting
*For any* message sent to Minimax-m2, the message format should conform to Anthropic SDK specifications.
**Validates: Requirements 3.2**

### Property 8: Tool Call Formatting
*For any* function call request, the tool definitions and tool call responses should use the Anthropic SDK format.
**Validates: Requirements 3.3, 12.1, 12.3, 12.4**

### Property 9: Streaming Chunk Parsing
*For any* streaming response chunk from Minimax-m2, the system should correctly parse chunks formatted according to Anthropic SDK specifications.
**Validates: Requirements 3.4**

### Property 10: Vision Tool MCP Integration
*For any* image analysis request, the vision tool should call the understand_image MCP server and format the request according to MCP specifications.
**Validates: Requirements 5.1, 5.2**

### Property 11: MCP Response Handling
*For any* response from the understand_image MCP server, the system should parse and format the analysis results for inclusion in the conversation.
**Validates: Requirements 5.3, 6.3**

### Property 12: Image Compression Preservation
*For any* image loaded through the vision tool, the system should apply compression before sending to the MCP server, maintaining the existing compression logic.
**Validates: Requirements 5.4**

### Property 13: Image Context Formatting
*For any* image added to a conversation, the system should format the image reference in a way compatible with Minimax-m2's message format.
**Validates: Requirements 6.1, 6.2**

### Property 14: Image Limit Enforcement
*For any* conversation context, the system should enforce the 3-image limit and prevent adding more images when the limit is reached.
**Validates: Requirements 6.4**

### Property 15: Image URL Processing
*For any* image URL provided to the vision tool, the system should download, process, and send the image to the understand_image MCP server.
**Validates: Requirements 6.5**

### Property 16: API Key Header Inclusion
*For any* request to Minimax-m2, the system should include the Minimax API key in the request headers using the Anthropic SDK format.
**Validates: Requirements 7.4**

### Property 17: Token Usage Extraction
*For any* response from Minimax-m2, the system should extract and record token usage information including input, output, and thinking tokens.
**Validates: Requirements 8.3, 8.4**

### Property 18: Historical Message Compatibility
*For any* existing conversation thread, the system should load and display all historical messages regardless of which model was originally used.
**Validates: Requirements 9.1, 9.4**

### Property 19: New Message Model Assignment
*For any* new message in an existing conversation, the system should use Minimax-m2 as the model while preserving historical model information in metadata.
**Validates: Requirements 9.2**

### Property 20: Agent Configuration Migration
*For any* agent configuration being migrated, the system should update the model to Minimax-m2 while preserving all other configuration settings.
**Validates: Requirements 9.5**

### Property 21: Error Message Parsing
*For any* error response from the Minimax API, the system should parse the error and extract a meaningful error message for the user.
**Validates: Requirements 10.1**

### Property 22: Tool Call Parsing
*For any* tool call request from Minimax-m2, the system should correctly parse the tool call and extract the function name and arguments.
**Validates: Requirements 12.2**

### Property 23: Parallel Tool Execution
*For any* set of parallel tool calls from Minimax-m2, the system should execute all tool calls and return results in the correct format.
**Validates: Requirements 12.5**

## Error Handling

### 1. API Communication Errors

**Error Types**:
- Network timeouts
- Connection failures
- DNS resolution errors

**Handling Strategy**:
```python
class MinimaxAPIError(Exception):
    """Base exception for Minimax API errors."""
    pass

async def make_minimax_request_with_retry(
    params: Dict[str, Any],
    max_retries: int = 3,
    backoff_factor: float = 2.0
) -> Any:
    """Make request with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            response = await make_llm_api_call(**params)
            return response
        except (NetworkError, TimeoutError) as e:
            if attempt == max_retries - 1:
                raise MinimaxAPIError(f"Failed after {max_retries} attempts: {e}")
            wait_time = backoff_factor ** attempt
            await asyncio.sleep(wait_time)
```

### 2. Authentication Errors

**Error Types**:
- Missing API key
- Invalid API key
- Expired API key

**Handling Strategy**:
```python
def validate_minimax_credentials() -> Tuple[bool, str]:
    """Validate Minimax API credentials on startup."""
    if not config.MINIMAX_API_KEY:
        logger.error("MINIMAX_API_KEY not configured")
        return False, "Minimax API key is required but not configured"
    
    # Test API key with a simple request
    try:
        test_response = requests.get(
            f"{config.MINIMAX_API_BASE}/health",
            headers={"x-api-key": config.MINIMAX_API_KEY}
        )
        if test_response.status_code == 401:
            return False, "Minimax API key is invalid"
        return True, "Credentials validated"
    except Exception as e:
        logger.warning(f"Could not validate credentials: {e}")
        return True, "Credentials not validated (will check on first request)"
```

### 3. Rate Limiting

**Error Types**:
- 429 Too Many Requests
- Rate limit exceeded

**Handling Strategy**:
```python
async def handle_rate_limit(
    error_response: Dict[str, Any],
    attempt: int
) -> float:
    """Calculate wait time for rate limit errors."""
    # Check for Retry-After header
    retry_after = error_response.get('headers', {}).get('retry-after')
    if retry_after:
        return float(retry_after)
    
    # Exponential backoff: 1s, 2s, 4s, 8s, ...
    return min(2 ** attempt, 60)  # Cap at 60 seconds
```

### 4. Context Length Errors

**Error Types**:
- Context window exceeded
- Token limit exceeded

**Handling Strategy**:
```python
async def handle_context_length_error(
    messages: List[Dict[str, Any]],
    max_context: int = 200_000
) -> List[Dict[str, Any]]:
    """Truncate conversation history when context limit is exceeded."""
    # Keep system message and last N messages
    system_messages = [m for m in messages if m['role'] == 'system']
    user_messages = [m for m in messages if m['role'] != 'system']
    
    # Estimate tokens (rough: 4 chars = 1 token)
    def estimate_tokens(msg: Dict) -> int:
        content = str(msg.get('content', ''))
        return len(content) // 4
    
    # Keep removing oldest messages until under limit
    while sum(estimate_tokens(m) for m in user_messages) > max_context * 0.9:
        if len(user_messages) <= 2:  # Keep at least last 2 messages
            break
        user_messages.pop(0)
    
    return system_messages + user_messages
```

### 5. MCP Server Errors

**Error Types**:
- MCP server unavailable
- Image analysis timeout
- Invalid image format

**Handling Strategy**:
```python
async def call_understand_image_mcp_with_fallback(
    image_url: str,
    timeout: int = 30
) -> str:
    """Call MCP server with timeout and fallback."""
    try:
        async with asyncio.timeout(timeout):
            response = await mcp_client.call(
                "understand_image",
                {"image_url": image_url}
            )
            return response['analysis']
    except asyncio.TimeoutError:
        logger.error(f"MCP server timeout after {timeout}s")
        return "Image analysis timed out. Please try again."
    except MCPServerError as e:
        logger.error(f"MCP server error: {e}")
        return f"Image analysis failed: {e}"
```

### 6. Thinking Block Parsing Errors

**Error Types**:
- Malformed thinking blocks
- Incomplete thinking content
- Mixed content types

**Handling Strategy**:
```python
def parse_thinking_block_safe(
    chunk: Any
) -> Tuple[Optional[str], Optional[str]]:
    """Safely parse thinking and content from chunk."""
    thinking = None
    content = None
    
    try:
        if hasattr(chunk, 'thinking_content'):
            thinking = str(chunk.thinking_content)
    except Exception as e:
        logger.warning(f"Failed to parse thinking content: {e}")
    
    try:
        if hasattr(chunk, 'content'):
            content = str(chunk.content)
    except Exception as e:
        logger.warning(f"Failed to parse content: {e}")
    
    return thinking, content
```

## Testing Strategy

### Unit Testing

**Test Coverage Areas**:

1. **Model Registry Tests**
   - Test Minimax-m2 registration with correct configuration
   - Test other models are registered but disabled
   - Test model resolution returns Minimax-m2 for all requests
   - Test pricing configuration matches requirements

2. **LLM Service Tests**
   - Test request parameter construction includes thinking mode
   - Test Anthropic SDK header formatting
   - Test API key inclusion in headers
   - Test error handling for various API errors

3. **Response Processor Tests**
   - Test thinking block detection and parsing
   - Test content block parsing
   - Test token usage extraction including thinking tokens
   - Test streaming chunk handling

4. **Vision Tool Tests**
   - Test MCP server call instead of Gemini API
   - Test image compression logic preservation
   - Test MCP request formatting
   - Test MCP response parsing
   - Test SVG to PNG conversion before MCP call

5. **Configuration Tests**
   - Test Minimax API key loading from environment
   - Test API base URL configuration
   - Test missing API key error handling
   - Test configuration hot-reload

### Property-Based Testing

The model will use **Hypothesis** (Python) for property-based testing to verify universal properties across many inputs.

**Configuration**: Each property-based test will run a minimum of 100 iterations to ensure thorough coverage.

**Test Generators**:

```python
from hypothesis import given, strategies as st

# Generator for agent configurations
@st.composite
def agent_config(draw):
    return {
        "agent_id": draw(st.uuids()),
        "name": draw(st.text(min_size=1, max_size=100)),
        "model": draw(st.sampled_from([
            "gpt-4", "claude-3", "gemini-pro", "minimax-m2"
        ])),
        "tools": draw(st.lists(st.text(), max_size=10))
    }

# Generator for conversation messages
@st.composite
def conversation_messages(draw):
    num_messages = draw(st.integers(min_value=1, max_value=20))
    messages = []
    for _ in range(num_messages):
        messages.append({
            "role": draw(st.sampled_from(["user", "assistant", "system"])),
            "content": draw(st.text(min_size=1, max_size=1000))
        })
    return messages

# Generator for streaming chunks with thinking
@st.composite
def streaming_chunk_with_thinking(draw):
    has_thinking = draw(st.booleans())
    has_content = draw(st.booleans())
    
    chunk = {}
    if has_thinking:
        chunk['thinking_content'] = draw(st.text(min_size=1, max_size=500))
    if has_content:
        chunk['content'] = draw(st.text(min_size=1, max_size=500))
    
    return chunk
```

### Integration Testing

**Test Scenarios**:

1. **End-to-End Conversation Flow**
   - Create agent → Send message → Receive response with thinking
   - Verify Minimax-m2 is used
   - Verify thinking blocks are parsed
   - Verify token usage is tracked

2. **Vision Tool Integration**
   - Load image → Call vision tool → Receive analysis
   - Verify MCP server is called
   - Verify image is compressed
   - Verify analysis is added to context

3. **Tool Calling Flow**
   - Configure agent with tools → Send message requiring tool use
   - Verify tool calls use Anthropic SDK format
   - Verify tool execution works
   - Verify results are formatted correctly

4. **Migration Flow**
   - Create agents with various models → Run migration
   - Verify all agents use Minimax-m2
   - Verify other settings preserved
   - Verify conversations still load

### Manual Testing Checklist

- [ ] Verify frontend has no model selection or display UI
- [ ] Verify mobile app has no model information displayed
- [ ] Test conversation with thinking blocks displays correctly
- [ ] Test image analysis through vision tool works
- [ ] Test tool calling with multiple tools works
- [ ] Test error messages are user-friendly
- [ ] Test existing conversations load correctly
- [ ] Verify billing calculations are accurate

## Implementation Notes

### Migration Path (Minimal Changes)

1. **Phase 1: Model Registry Configuration** (1 file change)
   - Add Minimax-m2 model definition to `backend/core/ai_models/registry.py`
   - Set `enabled=True` for Minimax-m2
   - Set `enabled=False` for all other models
   - **No changes to model manager or LLM service needed**

2. **Phase 2: Environment Configuration** (1 file change)
   - Add `MINIMAX_API_KEY` to environment variables
   - Add `MINIMAX_API_BASE` to environment variables
   - Update `.env.example` with new variables

3. **Phase 3: Vision Tool Update** (1 file change)
   - Replace Gemini API call in `backend/core/tools/sb_vision_tool.py`
   - Call understand_image MCP server instead
   - Keep all existing compression and upload logic

4. **Phase 4: Response Processor Enhancement** (1 small addition)
   - Add thinking token tracking to existing usage calculation
   - **No changes to streaming logic needed** (already handles reasoning_content)

5. **Phase 5: Frontend Cleanup** (remove UI components)
   - Remove model selection dropdowns
   - Remove model display fields
   - Update mobile app to remove model UI

6. **Phase 6: Testing & Validation**
   - Test with existing test suite (should mostly pass)
   - Add tests for Minimax-specific features
   - Validate billing calculations

**Total Code Changes**: ~5 files modified, existing functionality preserved

### Rollback Plan

If issues arise, the system can be rolled back by:

1. Re-enabling previous models in the registry
2. Reverting LLM service changes
3. Restoring Gemini API in vision tool
4. Re-adding frontend model selection UI

All previous provider code remains in place, making rollback straightforward.

### Performance Considerations

1. **Thinking Tokens**: Thinking mode increases token usage. Monitor costs closely.
2. **MCP Server Latency**: Image analysis through MCP may be slower than direct API calls. Implement timeouts.
3. **Streaming Performance**: Ensure thinking block parsing doesn't slow down streaming.
4. **Context Window**: Minimax-m2 has a 200K context window. Implement aggressive truncation if needed.

### Security Considerations

1. **API Key Storage**: Store Minimax API key securely in environment variables
2. **MCP Server Authentication**: Ensure MCP server requires authentication
3. **Image URLs**: Validate image URLs before downloading to prevent SSRF attacks
4. **Error Messages**: Don't expose API keys or internal details in error messages

