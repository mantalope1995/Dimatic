"""
AWS AgentCore Integration Module

This module provides adapters and configuration for AWS Bedrock AgentCore primitives:
- Runtime: Serverless agent execution
- Memory: Persistent knowledge storage with semantic search
- Code Interpreter: Secure code execution in isolated sandboxes
- Browser: Cloud-based browser automation
- Gateway: MCP server integration and API connectivity
"""

from .config import AgentCoreConfig, get_agentcore_config
from .adapters.runtime import AgentCoreRuntimeAdapter
from .adapters.memory import AgentCoreMemoryAdapter
from .adapters.code_interpreter import AgentCoreCodeInterpreterAdapter
from .adapters.browser import AgentCoreBrowserAdapter
from .adapters.gateway import AgentCoreGatewayAdapter

__all__ = [
    "AgentCoreConfig",
    "get_agentcore_config",
    "AgentCoreRuntimeAdapter",
    "AgentCoreMemoryAdapter",
    "AgentCoreCodeInterpreterAdapter",
    "AgentCoreBrowserAdapter",
    "AgentCoreGatewayAdapter",
]
