"""
Obot MCP Tool Wrapper

This module provides a wrapper for Obot MCP tools to be used within the AgentPress framework.
It maps MCP tool definitions to AgentPress Tool classes and handles execution delegation.
"""

from typing import Dict, Any, List, Optional, Type
import json
import logging
from dataclasses import dataclass

from core.agentpress.tool import Tool, ToolResult, ToolSchema, SchemaType
from core.obot.client import ObotClient, ObotClientError, ObotServiceUnavailable
from core.obot.models import MCPTool

logger = logging.getLogger(__name__)


class ObotMCPToolWrapper(Tool):
    """
    Wrapper for an Obot MCP tool.
    
    This class dynamically registers itself as an AgentPress Tool based on the
    MCP tool definition from Obot. It forwards execution calls to the Obot API.
    """
    
    def __init__(
        self, 
        mcp_tool: MCPTool, 
        obot_client: ObotClient, 
        server_id: str,
        user_token: Optional[str] = None
    ):
        """
        Initialize the MCP tool wrapper.
        
        Args:
            mcp_tool: The MCP tool definition from Obot
            obot_client: Initialized ObotClient instance
            server_id: ID of the MCP server this tool belongs to
            user_token: Optional user-scoped token for execution
        """
        self.mcp_tool = mcp_tool
        self.obot_client = obot_client
        self.server_id = server_id
        self.user_token = user_token
        
        # Initialize base Tool
        super().__init__()
        
        # Overwrite standard registration with dynamic schema
        self._register_dynamic_schema()
        
    def _register_dynamic_schema(self):
        """Register the tool schema dynamically from MCP definition."""
        # Map MCP input schema (JSON Schema) to AgentPress ToolSchema
        # AgentPress expects the schema to be for the method name
        
        # The method name for execution will be the tool name (sanitized if needed)
        method_name = self.mcp_tool.name
        
        schema = ToolSchema(
            schema_type=SchemaType.OPENAPI,
            schema={
                "type": "function",
                "function": {
                    "name": method_name,
                    "description": self.mcp_tool.description,
                    "parameters": self.mcp_tool.input_schema
                }
            }
        )
        
        # Register in the _schemas dictionary
        self._schemas[method_name] = [schema]
        
    async def execute(self, method_name: str, **kwargs) -> ToolResult:
        """
        Execute the tool.
        
        This method is called by the agent framework when it decides to use this tool.
        Run.py or the response processor needs to call this specific method.
        
        Args:
            method_name: Name of the method to execute (should match tool name)
            **kwargs: Arguments for the tool execution
            
        Returns:
            ToolResult containing the execution output or error
        """
        if method_name != self.mcp_tool.name:
            return self.fail_response(f"Unknown method: {method_name}. Expected: {self.mcp_tool.name}")
            
        try:
            logger.info(f"Executing Obot MCP tool: {self.server_id}/{method_name}")
            
            # Call Obot API
            response = await self.obot_client.call_tool(
                server_id=self.server_id,
                tool_name=method_name,
                arguments=kwargs,
                token=self.user_token
            )
            
            if response.success:
                # Format output
                return self.success_response(response.result)
            else:
                # Handle failure
                error_msg = response.error or "Unknown error during tool execution"
                
                # Check for OAuth requirement (standardized convention needed)
                # If the error string indicates auth required, we could parse it
                # For now, we rely on the client or server status for that, 
                # but execution-time 401s might come through as errors.
                
                return self.fail_response(f"Tool execution failed: {error_msg}")
        
        except ObotServiceUnavailable as e:
            logger.warning(f"Obot service unavailable during tool execution {method_name}: {e}")
            return self.fail_response(f"Service temporarily unavailable: {str(e)}. Please try again later.")
            
        except ObotClientError as e:
            logger.error(f"Obot client error execute MCP tool {method_name}: {e}")
            return self.fail_response(f"Error communicating with tool service: {str(e)}")
            
        except Exception as e:
            logger.error(f"Error executing MCP tool {method_name}: {e}")
            return self.fail_response(f"Internal error executing tool: {str(e)}")

    # Support for the standard 'execute_tool' pattern if used by some runners
    # Note: AgentPress usually calls methods directly by name on the instance if it finds them,
    # OR the runner uses a unified execute method. 
    # Since we don't have a real method named `method_name` on this class,
    # we need to rely on the runner knowing how to handle dynamic tools OR 
    # we simulate the method using __getattr__ which is risky, 
    # OR we bind a method dynamically.
    
    # Binding strategy:
    # We can add a method to the instance that matches the tool name.
    
    def __getattr__(self, name):
        """
        Dynamic method dispatcher.
        
        If the agent tries to call the tool method directly (e.g. tool.calculator_add(...)),
        this intercepts it.
        """
        if name == self.mcp_tool.name:
            # Return a callable that maps to execute
            async def wrapper(**kwargs):
                return await self.execute(name, **kwargs)
            return wrapper
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")


async def create_obot_tools(
    obot_client: ObotClient, 
    server_id: str, 
    user_id: Optional[str] = None,
    user_token: Optional[str] = None
) -> List[Tool]:
    """
    Factory function to create Tool instances for all enabled tools in an MCP server.
    
    Args:
        obot_client: Initialized ObotClient
        server_id: MCP Server ID
        user_id: Suna user ID (optional, for logging/context)
        user_token: Obot token for the user (optional, execution token)
        
    Returns:
        List of Tool instances
    """
    try:
        # Fetch available tools
        # We use the bootstrap token (in client) or user token to list tools
        # Usually listing tools is a public/shared operation, but might need auth
        mcp_tools = await obot_client.list_tools(server_id, token=user_token)
        
        tools = []
        for mcp_tool in mcp_tools:
            if mcp_tool.enabled:
                wrapper = ObotMCPToolWrapper(
                    mcp_tool=mcp_tool,
                    obot_client=obot_client,
                    server_id=server_id,
                    user_token=user_token
                )
                tools.append(wrapper)
                
        logger.info(f"Created {len(tools)} wrapper tools for Obot server {server_id}")
        return tools
        
    except Exception as e:
        logger.error(f"Failed to create Obot tools for server {server_id}: {e}")
        return []
