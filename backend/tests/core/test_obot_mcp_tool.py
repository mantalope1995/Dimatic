import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.tools.obot_mcp_tool import ObotMCPToolWrapper, create_obot_tools
from core.obot.models import MCPTool, ToolCallResponse
from core.obot.client import ObotServiceUnavailable

@pytest.mark.asyncio
async def test_obuf_mcp_tool_initialization():
    # Setup
    mcp_tool = MCPTool(
        name="test_tool",
        description="A test tool",
        input_schema={"type": "object", "properties": {"arg1": {"type": "string"}}},
        enabled=True
    )
    mock_client = AsyncMock()
    server_id = "server_123"
    
    # Execute
    wrapper = ObotMCPToolWrapper(
        mcp_tool=mcp_tool,
        obot_client=mock_client,
        server_id=server_id
    )
    
    # Verify
    schemas = wrapper.get_schemas()
    assert "test_tool" in schemas
    assert schemas["test_tool"][0].schema["function"]["name"] == "test_tool"
    assert schemas["test_tool"][0].schema["function"]["description"] == "A test tool"

@pytest.mark.asyncio
async def test_execute_success():
    # Setup
    mcp_tool = MCPTool(name="test_tool", description="desc", input_schema={}, enabled=True)
    mock_client = AsyncMock()
    mock_client.call_tool.return_value = ToolCallResponse(
        success=True,
        result="Success output",
        is_error=False
    )
    
    wrapper = ObotMCPToolWrapper(
        mcp_tool=mcp_tool,
        obot_client=mock_client,
        server_id="server_1"
    )
    
    # Execute
    result = await wrapper.execute("test_tool", arg1="value1")
    
    # Verify
    assert result.success is True
    assert "Success output" in result.output
    mock_client.call_tool.assert_called_once_with(
        server_id="server_1",
        tool_name="test_tool",
        arguments={"arg1": "value1"},
        token=None
    )

@pytest.mark.asyncio
async def test_execute_failure():
    # Setup
    mcp_tool = MCPTool(name="test_tool", description="desc", input_schema={}, enabled=True)
    mock_client = AsyncMock()
    mock_client.call_tool.return_value = ToolCallResponse(
        success=False,
        error="Execution failed",
        is_error=True
    )
    
    wrapper = ObotMCPToolWrapper(
        mcp_tool=mcp_tool,
        obot_client=mock_client,
        server_id="server_1"
    )
    
    # Execute
    result = await wrapper.execute("test_tool")
    
    # Verify
    assert result.success is False
    assert "Execution failed" in result.output

@pytest.mark.asyncio
async def test_create_obot_tools_factory():
    # Setup
    mock_client = AsyncMock()
    tools_list = [
        MCPTool(name="tool1", description="d1", input_schema={}, enabled=True),
        MCPTool(name="tool2", description="d2", input_schema={}, enabled=False), # Disabled
        MCPTool(name="tool3", description="d3", input_schema={}, enabled=True)
    ]
    mock_client.list_tools.return_value = tools_list
    
    # Execute
    tools = await create_obot_tools(mock_client, "server_1")
    
    # Verify
    assert len(tools) == 2
    assert tools[0].mcp_tool.name == "tool1"
    assert tools[1].mcp_tool.name == "tool3"

@pytest.mark.asyncio
async def test_execute_service_unavailable():
    # Setup
    mcp_tool = MCPTool(name="test_tool", description="desc", input_schema={}, enabled=True)
    mock_client = AsyncMock()
    mock_client.call_tool.side_effect = ObotServiceUnavailable("Service overload")
    
    wrapper = ObotMCPToolWrapper(
        mcp_tool=mcp_tool,
        obot_client=mock_client,
        server_id="server_1"
    )
    
    # Execute
    result = await wrapper.execute("test_tool")
    
    # Verify
    assert result.success is False
    assert "Service temporarily unavailable" in result.output
    assert "Service overload" in result.output
