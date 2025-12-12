# Requirements Document

## Introduction

This specification defines the requirements for optimizing Suna (Kortix's AI agent platform) to use Qwen3-VL-235B-A22B-Instruct as the primary LLM. This is a greenfield integration that replaces the existing LLM infrastructure with a Qwen3-VL-optimized architecture. The model will be accessed via SiliconFlow's API, which provides an OpenAI-compatible interface. Key optimizations include transitioning from XML-based tool calling to native OpenAI-style function calling, leveraging the model's native multimodal (vision) capabilities, and optionally integrating Qwen3 embedding and reranker models for enhanced RAG functionality.

## Glossary

- **Qwen3-VL-235B-A22B-Instruct**: A multimodal vision-language model from Alibaba's Qwen series with 235B parameters (22B active via MoE), supporting text, image, and video understanding with native function calling
- **SiliconFlow**: A cloud API provider offering OpenAI-compatible endpoints for various LLMs including Qwen models
- **Native Function Calling**: OpenAI-style tool/function calling where the model outputs structured JSON tool calls rather than XML-formatted text
- **XML Tool Calling**: The current Suna approach where tools are invoked via XML tags like `<function_calls><invoke name="tool">...</invoke></function_calls>`
- **MoE (Mixture of Experts)**: Architecture where only a subset of parameters are active per inference, enabling larger models with efficient compute
- **Qwen3-Embedding**: Qwen's text embedding model series (0.6B-8B) for semantic search and retrieval
- **Qwen3-Reranker**: Qwen's reranking model series (0.6B-8B) for improving retrieval relevance
- **RAG (Retrieval-Augmented Generation)**: Pattern combining retrieval systems with LLM generation
- **LiteLLM**: Python library providing unified interface to multiple LLM providers
- **Vision Tool**: Current Suna tool that sends images to a separate vision model for analysis

## Requirements

### Requirement 1

**User Story:** As a platform operator, I want to configure Qwen3-VL-235B-A22B-Instruct as the primary LLM via SiliconFlow API, so that all agent interactions use this model.

#### Acceptance Criteria

1. WHEN the backend initializes THEN the System SHALL load SiliconFlow API credentials from environment configuration
2. WHEN an LLM request is made THEN the System SHALL route the request to SiliconFlow's OpenAI-compatible endpoint with model identifier `Qwen/Qwen3-VL-235B-A22B-Instruct`
3. WHEN the SiliconFlow API returns a response THEN the System SHALL parse the response using OpenAI-compatible response format
4. WHEN API credentials are missing or invalid THEN the System SHALL log a descriptive error and prevent agent startup
5. WHEN configuring the model THEN the System SHALL set appropriate context window limits (262144 tokens) and max output token limits (262144 tokens)

### Requirement 2

**User Story:** As a developer, I want Suna to use native OpenAI-style function calling instead of XML tool calling, so that tool invocations are more reliable and leverage the model's trained capabilities.

#### Acceptance Criteria

1. WHEN tools are registered THEN the System SHALL convert tool definitions to OpenAI function calling JSON schema format
2. WHEN making an LLM request with tools THEN the System SHALL include tools in the `tools` parameter using OpenAI function format
3. WHEN the model returns tool calls THEN the System SHALL parse them from the `tool_calls` field in the response message
4. WHEN a tool call is parsed THEN the System SHALL extract function name, arguments, and tool_call_id from the native format
5. WHEN tool results are returned THEN the System SHALL format them as tool role messages with matching tool_call_id
6. WHEN streaming responses contain tool calls THEN the System SHALL buffer and assemble tool call chunks correctly

### Requirement 3

**User Story:** As a developer, I want to remove the XML tool calling system, so that the codebase is simplified and optimized for native function calling.

#### Acceptance Criteria

1. WHEN the System processes LLM responses THEN the System SHALL use only native tool call parsing (not XML parsing)
2. WHEN configuring the response processor THEN the System SHALL set `xml_tool_calling=False` and `native_tool_calling=True`
3. WHEN the System generates prompts THEN the System SHALL exclude XML tool calling instructions from system prompts
4. WHEN tool definitions are provided THEN the System SHALL format them only in OpenAI function schema format

### Requirement 4

**User Story:** As a user, I want Suna to directly process images using Qwen3-VL's native vision capabilities, so that image understanding is faster and more integrated.

#### Acceptance Criteria

1. WHEN a user provides an image in a message THEN the System SHALL include the image directly in the message content array using OpenAI vision format
2. WHEN processing images THEN the System SHALL encode images as base64 data URLs or pass image URLs directly
3. WHEN the model analyzes an image THEN the System SHALL receive the analysis in the standard text response without requiring a separate vision tool call
4. WHEN multiple images are provided THEN the System SHALL include all images in the content array (respecting model limits)
5. WHEN image resolution parameters are needed THEN the System SHALL support min_pixels and max_pixels configuration

### Requirement 5

**User Story:** As a developer, I want to remove the separate vision tool entirely, so that image analysis uses only the model's native multimodal capabilities.

#### Acceptance Criteria

1. WHEN configuring agent tools THEN the System SHALL not include any vision-specific tool in the available tools list
2. WHEN image analysis is needed THEN the System SHALL rely on native multimodal message content (not tool calls)
3. WHEN the vision tool code is removed THEN the System SHALL have no references to the legacy vision tool modules

### Requirement 6

**User Story:** As a platform operator, I want to optionally integrate Qwen3-Embedding models for semantic search, so that RAG functionality is enhanced.

#### Acceptance Criteria

1. WHEN embedding configuration is provided THEN the System SHALL initialize the Qwen3-Embedding model client
2. WHEN text needs embedding THEN the System SHALL call the embedding model and return vector representations
3. WHEN embedding model is not configured THEN the System SHALL fall back to existing embedding behavior or disable semantic search
4. WHEN embedding requests are made THEN the System SHALL support instruction-aware embedding with task prefixes

### Requirement 7

**User Story:** As a platform operator, I want to optionally integrate Qwen3-Reranker models for improved retrieval, so that search results are more relevant.

#### Acceptance Criteria

1. WHEN reranker configuration is provided THEN the System SHALL initialize the Qwen3-Reranker model client
2. WHEN search results need reranking THEN the System SHALL call the reranker model with query-document pairs
3. WHEN reranker model is not configured THEN the System SHALL skip reranking and return results in original order
4. WHEN reranking is performed THEN the System SHALL return relevance scores for each document

### Requirement 8

**User Story:** As a developer, I want the system prompt optimized for Qwen3-VL's capabilities, so that the model performs optimally.

#### Acceptance Criteria

1. WHEN generating the system prompt THEN the System SHALL exclude XML tool calling syntax examples and instructions
2. WHEN generating the system prompt THEN the System SHALL include guidance for native function calling format
3. WHEN generating the system prompt THEN the System SHALL reference the model's native vision capabilities for image tasks
4. WHEN generating the system prompt THEN the System SHALL maintain existing task management and workflow instructions

### Requirement 9

**User Story:** As a platform operator, I want to use a hybrid model approach with Qwen3-VL-Thinking for planning and Qwen3-VL-Instruct for execution, so that complex tasks benefit from reasoning while execution remains fast.

#### Acceptance Criteria

1. WHEN a new complex task is received THEN the System SHALL invoke Qwen/Qwen3-VL-235B-A22B-Thinking to create a detailed task plan
2. WHEN executing individual task steps THEN the System SHALL use Qwen/Qwen3-VL-235B-A22B-Instruct for tool execution
3. WHEN the task plan is created THEN the System SHALL store it in the conversation context for the execution model to follow
4. WHEN the Thinking model generates reasoning THEN the System SHALL capture the reasoning_content field from the response
5. WHEN model selection is needed THEN the System SHALL route planning requests to the Thinking variant and execution requests to the Instruct variant

#### Future Enhancement: Adversarial Review Loop

_Not in MVP scope - document for future implementation:_

- Thinking model automatically adds "Final Review" step to every task plan
- When execution reaches Final Review, Thinking model compares output against original requirements
- If issues found: creates correction plan with new Final Review at end
- Cap at 2-3 review iterations to prevent runaway costs
- This creates a self-correcting adversarial loop for complex multi-step tasks

### Requirement 10

**User Story:** As a developer, I want clean removal of legacy LLM integrations, so that the codebase is simplified for the Qwen3-VL-only architecture.

#### Acceptance Criteria

1. WHEN the model registry initializes THEN the System SHALL register only Qwen3-VL models (Thinking and Instruct variants) as available
2. WHEN model selection is requested THEN the System SHALL return the appropriate Qwen3-VL variant based on task type
3. WHEN legacy model configurations exist THEN the System SHALL ignore them and use Qwen3-VL configuration
4. WHEN API routing is configured THEN the System SHALL route all requests to SiliconFlow endpoint

### Requirement 11

**User Story:** As a developer, I want robust error handling for the SiliconFlow API integration, so that failures are handled gracefully.

#### Acceptance Criteria

1. WHEN the SiliconFlow API returns an error THEN the System SHALL parse the error response and provide a descriptive message
2. WHEN rate limiting occurs THEN the System SHALL implement appropriate backoff and retry logic
3. WHEN the API is unavailable THEN the System SHALL log the failure and notify the user through the agent interface
4. WHEN token limits are exceeded THEN the System SHALL truncate context appropriately and retry

### Requirement 12

**User Story:** As a developer, I want streaming responses to work correctly with native function calling, so that users see real-time output.

#### Acceptance Criteria

1. WHEN streaming is enabled THEN the System SHALL process content chunks and yield them incrementally
2. WHEN tool call chunks arrive during streaming THEN the System SHALL buffer them until complete
3. WHEN a tool call is complete during streaming THEN the System SHALL execute it according to the configured strategy
4. WHEN streaming completes THEN the System SHALL save the complete assistant message with all tool calls

### Requirement 13

**User Story:** As a developer, I want tool argument parsing to handle Qwen3-VL's JSON output format, so that tool calls execute correctly.

#### Acceptance Criteria

1. WHEN tool arguments are received THEN the System SHALL parse them as JSON objects
2. WHEN tool arguments contain nested structures THEN the System SHALL preserve the structure during parsing
3. WHEN tool arguments are malformed THEN the System SHALL log the error and skip the tool call gracefully
4. WHEN serializing tool arguments for storage THEN the System SHALL maintain JSON format consistency
