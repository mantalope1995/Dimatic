# Requirements Document

## Introduction

This document specifies the requirements for migrating the Kortix platform from its current multi-provider LLM architecture to use Minimax-m2 as the sole language model provider. Minimax-m2 offers extended thinking capabilities through interleaved thinking mode, which will replace the existing model selection system. The migration includes adapting the vision capabilities to use the Minimax understand_image MCP server instead of the current Gemini-based vision tool.

## Glossary

- **Minimax-m2**: A language model provider offering extended thinking capabilities through interleaved thinking mode
- **Interleaved Thinking**: A mode where the model's reasoning process is interwoven with its responses
- **LiteLLM**: The current multi-provider LLM integration library used by Kortix
- **Model Registry**: The system component that manages available AI models and their configurations
- **Vision Tool**: The sb_vision_tool component that enables image analysis capabilities
- **MCP Server**: Model Context Protocol server that provides tool integrations
- **understand_image MCP**: The Minimax MCP server for image understanding capabilities
- **Model Manager**: The service layer that handles model selection and API calls
- **Agent Configuration**: The settings that define which model an agent uses
- **Anthropic SDK**: The SDK format used by Minimax-m2 for API compatibility

## Requirements

### Requirement 1

**User Story:** As a system administrator, I want to configure Minimax-m2 as the sole LLM provider, so that all agents use this model exclusively without user awareness.

#### Acceptance Criteria

1. WHEN the system initializes THEN the Model Registry SHALL register only Minimax-m2 as an available model
2. WHEN an agent is created or updated THEN the system SHALL automatically assign Minimax-m2 as the model
3. WHEN the API receives a model selection request THEN the system SHALL return only Minimax-m2 as an option
4. WHEN existing agents are loaded THEN the system SHALL override their model configuration to use Minimax-m2
5. WHERE the frontend requests model information THEN the system SHALL not expose model details to the user interface

### Requirement 2

**User Story:** As a developer, I want Minimax-m2 to use interleaved thinking mode by default, so that the model provides enhanced reasoning capabilities.

#### Acceptance Criteria

1. WHEN making API calls to Minimax-m2 THEN the system SHALL include the interleaved thinking configuration parameter
2. WHEN the LLM service constructs request parameters THEN the system SHALL set thinking mode to "interleaved"
3. WHEN processing responses from Minimax-m2 THEN the system SHALL handle interleaved thinking content blocks correctly
4. WHEN streaming responses THEN the system SHALL properly parse and display thinking blocks alongside response content
5. WHEN calculating token usage THEN the system SHALL account for tokens used in thinking blocks

### Requirement 3

**User Story:** As a developer, I want to integrate Minimax-m2 using the Anthropic SDK format, so that the API calls follow the documented interface.

#### Acceptance Criteria

1. WHEN configuring the Minimax-m2 model THEN the system SHALL use the Anthropic SDK-compatible endpoint format
2. WHEN constructing API requests THEN the system SHALL format messages according to Anthropic SDK specifications
3. WHEN handling function calling THEN the system SHALL use the Anthropic SDK tool format
4. WHEN processing streaming responses THEN the system SHALL parse Anthropic SDK-formatted chunks
5. WHERE authentication is required THEN the system SHALL use the Minimax API key in the Anthropic SDK header format

### Requirement 4

**User Story:** As a system administrator, I want other LLM providers to remain in the codebase but disabled, so that the system can be easily reverted or extended in the future.

#### Acceptance Criteria

1. WHEN the Model Registry initializes THEN the system SHALL register Minimax-m2 as the only enabled model
2. WHEN the Model Registry initializes THEN the system SHALL keep other provider models registered but marked as disabled
3. WHEN the frontend renders model options THEN the system SHALL display only enabled models (Minimax-m2)
4. WHEN the LLM service processes requests THEN the system SHALL route all requests to Minimax-m2
5. WHERE existing provider code exists THEN the system SHALL preserve it without modification for future use

### Requirement 5

**User Story:** As a user, I want image analysis to work through the Minimax understand_image MCP server, so that vision capabilities remain functional after migration.

#### Acceptance Criteria

1. WHEN the vision tool is invoked THEN the system SHALL call the understand_image MCP server instead of the Gemini API
2. WHEN an image is loaded THEN the system SHALL format the request according to the understand_image MCP specification
3. WHEN the MCP server returns results THEN the system SHALL parse and present the image analysis to the user
4. WHEN image compression is needed THEN the system SHALL maintain existing compression logic before sending to the MCP server
5. WHERE SVG conversion is required THEN the system SHALL convert SVG files to PNG before sending to the understand_image MCP server

### Requirement 6

**User Story:** As a developer, I want the vision tool to integrate seamlessly with Minimax-m2, so that image analysis works within the agent conversation flow.

#### Acceptance Criteria

1. WHEN an agent loads an image THEN the system SHALL add the image to the conversation context in a format compatible with Minimax-m2
2. WHEN Minimax-m2 processes a conversation with images THEN the system SHALL include image references in the message format
3. WHEN the understand_image MCP returns analysis THEN the system SHALL format the results for inclusion in the agent's response
4. WHEN multiple images are in context THEN the system SHALL maintain the 3-image limit and handle image management correctly
5. WHERE image URLs are provided THEN the system SHALL download, process, and send images to the understand_image MCP server

### Requirement 7

**User Story:** As a system administrator, I want to configure the Minimax API endpoint and credentials, so that the system can authenticate and communicate with Minimax services.

#### Acceptance Criteria

1. WHEN the system starts THEN the configuration SHALL load the Minimax API key from environment variables
2. WHEN the system starts THEN the configuration SHALL load the Minimax API base URL from environment variables
3. WHERE the Minimax API key is missing THEN the system SHALL log an error and prevent LLM operations
4. WHEN the LLM service makes requests THEN the system SHALL include the Minimax API key in request headers
5. WHEN the configuration is updated THEN the system SHALL apply new Minimax credentials without requiring a restart

### Requirement 8

**User Story:** As a developer, I want the model pricing and token counting to reflect Minimax-m2 costs, so that billing and usage tracking remain accurate.

#### Acceptance Criteria

1. WHEN the Model Registry defines Minimax-m2 THEN the system SHALL set input cost to $0.60 per million tokens
2. WHEN the Model Registry defines Minimax-m2 THEN the system SHALL set output cost to $2.20 per million tokens
3. WHEN processing responses THEN the system SHALL extract token usage from Minimax-m2 API responses
4. WHEN storing usage data THEN the system SHALL record token counts and costs for billing purposes
5. WHERE thinking tokens are used THEN the system SHALL include thinking token costs in the total calculation

### Requirement 9

**User Story:** As a user, I want existing conversations to continue working after migration, so that I don't lose access to my conversation history.

#### Acceptance Criteria

1. WHEN loading existing threads THEN the system SHALL display historical messages regardless of the original model used
2. WHEN continuing an existing conversation THEN the system SHALL use Minimax-m2 for new messages
3. WHEN the UI displays conversations THEN the system SHALL not show any model information to the user
4. WHERE historical messages reference other models THEN the system SHALL preserve the original model name in message metadata
5. WHEN migrating agent configurations THEN the system SHALL update the default model to Minimax-m2 while preserving other settings

### Requirement 10

**User Story:** As a developer, I want comprehensive error handling for Minimax-m2 API failures, so that users receive clear feedback when issues occur.

#### Acceptance Criteria

1. WHEN the Minimax API returns an error THEN the system SHALL parse the error response and extract meaningful error messages
2. WHEN rate limits are exceeded THEN the system SHALL retry requests with exponential backoff
3. WHEN authentication fails THEN the system SHALL log the error and return a clear message to the user
4. WHEN network errors occur THEN the system SHALL attempt retries before failing
5. WHERE context length is exceeded THEN the system SHALL truncate the conversation history and retry the request

### Requirement 11

**User Story:** As a developer, I want the frontend to remove all model-related UI components, so that users are not aware of or concerned with which LLM is being used.

#### Acceptance Criteria

1. WHEN the agent creation UI loads THEN the system SHALL not display any model selection or configuration UI
2. WHEN the agent settings UI loads THEN the system SHALL not show any model information or configuration options
3. WHEN displaying agent information THEN the system SHALL not show any model name or identifier
4. WHERE model tier selection existed (basic/power) THEN the system SHALL remove these UI elements completely
5. WHEN the mobile app displays agent settings THEN the system SHALL not include any model-related components

### Requirement 12

**User Story:** As a developer, I want to maintain function calling capabilities with Minimax-m2, so that agents can continue using tools.

#### Acceptance Criteria

1. WHEN an agent has tools configured THEN the system SHALL format tool definitions according to Anthropic SDK specifications
2. WHEN Minimax-m2 requests a tool call THEN the system SHALL parse the tool call request correctly
3. WHEN executing a tool THEN the system SHALL format the tool result for inclusion in the next API request
4. WHEN multiple tools are available THEN the system SHALL include all tool definitions in the API request
5. WHERE parallel tool calls are made THEN the system SHALL execute all tool calls and return results in the correct format
