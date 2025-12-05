# Implementation Plan

## Overview

This implementation plan focuses on **minimal changes** to integrate Minimax-m2 while preserving the existing working LLM integration. The tasks are organized to build incrementally, with testing integrated throughout.

## Task List

- [x] 1. Configure Minimax-m2 in Model Registry
  - Add Minimax-m2 model definition to `backend/core/ai_models/registry.py`
  - Set pricing: $0.60 input, $2.20 output per million tokens
  - Configure with Anthropic SDK-compatible settings (api_base, headers)
  - Enable thinking capability
  - Set `enabled=True` for Minimax-m2
  - Set `enabled=False` for all other models
  - _Requirements: 1.1, 1.2, 4.1, 4.2, 8.1, 8.2_

- [x] 1.1 Write property test for model registry initialization
  - **Property 1: Model Registry Initialization**
  - **Validates: Requirements 1.1, 4.1, 4.2**

- [x] 2. Add Minimax API configuration
  - Add `MINIMAX_API_KEY` to `backend/core/utils/config.py`
  - Add `MINIMAX_API_BASE` to `backend/core/utils/config.py`
  - Add validation for missing API key
  - Update `.env.example` with new variables
  - _Requirements: 7.1, 7.2, 7.3_

- [x] 2.1 Write unit tests for configuration loading
  - Test API key loading from environment
  - Test API base URL loading
  - Test error handling for missing key
  - _Requirements: 7.1, 7.2, 7.3_

- [x] 3. Update response processor for thinking tokens
  - Add thinking token extraction in `backend/core/agentpress/response_processor.py`
  - Update token usage calculation to include thinking tokens
  - Preserve existing `reasoning_content` handling (already works)
  - _Requirements: 2.5, 8.3, 8.4, 8.5_

- [x] 3.1 Write property test for thinking token tracking
  - **Property 6: Token Usage Calculation**
  - **Validates: Requirements 2.5, 8.5**

- [x] 3.2 Write property test for thinking block parsing
  - **Property 5: Thinking Block Parsing**
  - **Validates: Requirements 2.3, 2.4**

- [x] 4. Checkpoint - Verify LLM integration works
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Migrate vision tool to understand_image MCP
  - Update `backend/core/tools/sb_vision_tool.py`
  - Replace Gemini API call with understand_image MCP server call
  - Implement `_call_understand_image_mcp()` method
  - Keep all existing compression logic unchanged
  - Keep all existing upload logic unchanged
  - Handle SVG conversion before MCP call
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 5.1 Write property test for MCP request formatting
  - **Property 10: Vision Tool MCP Integration**
  - **Validates: Requirements 5.1, 5.2**

- [x] 5.2 Write property test for MCP response handling
  - **Property 11: MCP Response Handling**
  - **Validates: Requirements 5.3, 6.3**

- [x] 5.3 Write property test for image compression preservation
  - **Property 12: Image Compression Preservation**
  - **Validates: Requirements 5.4**

- [x] 5.4 Write unit tests for vision tool
  - Test MCP server is called instead of Gemini
  - Test image compression still works
  - Test SVG conversion before MCP call
  - Test error handling for MCP failures
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 6. Update agent model assignment logic
  - Update agent creation to assign Minimax-m2 automatically
  - Update agent loading to override model to Minimax-m2
  - Preserve other agent settings during migration
  - _Requirements: 1.2, 1.4, 9.5_

- [x] 6.1 Write property test for agent model assignment
  - **Property 2: Agent Model Assignment**
  - **Validates: Requirements 1.2, 1.4**

- [x] 6.2 Write property test for agent configuration migration
  - **Property 20: Agent Configuration Migration**
  - **Validates: Requirements 9.5**

- [x] 7. Remove model selection UI from frontend
  - Remove model selection dropdowns from agent creation page
  - Remove model display from agent settings page
  - Remove model configuration options
  - Remove model tier selection (basic/power)
  - Update `frontend/src/components/agents/` components
  - _Requirements: 11.1, 11.2, 11.3, 11.4_

- [x] 7.1 Write unit tests for frontend components
  - Test model selection UI is not rendered
  - Test model information is not displayed
  - _Requirements: 11.1, 11.2, 11.3, 11.4_

- [x] 8. Remove model selection UI from mobile app
  - Remove model selection from agent settings screens
  - Remove model display from agent information
  - Update `apps/mobile/components/agents/` components
  - _Requirements: 11.5_

- [x] 8.1 Write unit tests for mobile components
  - Test model selection UI is not rendered
  - Test model information is not displayed
  - _Requirements: 11.5_

- [x] 9. Checkpoint - Verify all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Integration testing
  - Test end-to-end conversation flow with Minimax-m2
  - Test thinking blocks are parsed and displayed
  - Test vision tool with understand_image MCP
  - Test tool calling with Anthropic SDK format
  - Test existing conversations still load
  - Test agent migration preserves settings
  - _Requirements: All_

- [x] 10.1 Write integration tests
  - Test complete conversation flow
  - Test vision tool integration
  - Test tool calling flow
  - Test conversation migration
  - _Requirements: All_

- [x] 11. Final checkpoint - Production readiness
  - Ensure all tests pass, ask the user if questions arise.

