"""
Centralized Tool Registry - Single Source of Truth for Tool Names and Classes

This registry maps tool names (used in configs) to their Python class names.
Both runtime registration (run.py) and UI metadata (tool_discovery.py) use this registry
to ensure tool names are always consistent.

To add a new tool:
1. Add the mapping to the appropriate category list below
2. The tool will automatically be available in both runtime and UI
"""

from typing import Dict, List, Tuple, Type, Optional
from core.agentpress.tool import Tool

# Core tools - Always available
CORE_TOOLS = [
    ('expand_msg_tool', 'core.tools.expand_msg_tool', 'ExpandMessageTool'),
    ('message_tool', 'core.tools.message_tool', 'MessageTool'),
    ('task_list_tool', 'core.tools.task_list_tool', 'TaskListTool'),
]

# Sandbox tools - File system, shell, and workspace operations (Daytona.io)
SANDBOX_TOOLS = [
    ('sb_shell_tool', 'core.tools.sb_shell_tool', 'SandboxShellTool'),
    ('sb_files_tool', 'core.tools.sb_files_tool', 'SandboxFilesTool'),
    ('sb_expose_tool', 'core.tools.sb_expose_tool', 'SandboxExposeTool'),
    ('sb_vision_tool', 'core.tools.sb_vision_tool', 'SandboxVisionTool'),
    ('sb_image_edit_tool', 'core.tools.sb_image_edit_tool', 'SandboxImageEditTool'),
    ('sb_kb_tool', 'core.tools.sb_kb_tool', 'SandboxKbTool'),
    # ('sb_design_tool', 'core.tools.sb_designer_tool', 'SandboxDesignerTool'),
    ('sb_presentation_tool', 'core.tools.sb_presentation_tool', 'SandboxPresentationTool'),
    ('sb_upload_file_tool', 'core.tools.sb_upload_file_tool', 'SandboxUploadFileTool'),
    # ('sb_docs_tool', 'core.tools.sb_docs_tool', 'SandboxDocsTool'),
]

# AgentCore tools - AWS AgentCore based sandbox operations
AGENTCORE_TOOLS = [
    ('sb_shell_tool', 'core.tools.sb_shell_tool_agentcore', 'AgentCoreShellTool'),
    ('sb_files_tool', 'core.tools.sb_files_tool_agentcore', 'AgentCoreFilesTool'),
    ('sb_vision_tool', 'core.tools.sb_vision_tool_agentcore', 'AgentCoreVisionTool'),
    ('sb_browser_tool', 'core.tools.sb_browser_tool_agentcore', 'AgentCoreBrowserTool'),
    ('sb_browser_tool_stagehand', 'core.tools.sb_browser_tool_stagehand_agentcore', 'AgentCoreStagehandTool'),
]

# Search and research tools
SEARCH_TOOLS = [
    ('web_search_tool', 'core.tools.web_search_tool', 'SandboxWebSearchTool'),
    ('image_search_tool', 'core.tools.image_search_tool', 'SandboxImageSearchTool'),
    ('people_search_tool', 'core.tools.people_search_tool', 'PeopleSearchTool'),
    ('company_search_tool', 'core.tools.company_search_tool', 'CompanySearchTool'),
    ('paper_search_tool', 'core.tools.paper_search_tool', 'PaperSearchTool'),
]

# Utility tools
UTILITY_TOOLS = [
    ('data_providers_tool', 'core.tools.data_providers_tool', 'DataProvidersTool'),
    ('browser_tool', 'core.tools.browser_tool', 'BrowserTool'),
    ('vapi_voice_tool', 'core.tools.vapi_voice_tool', 'VapiVoiceTool'),
]

# Agent builder tools
AGENT_BUILDER_TOOLS = [
    ('agent_config_tool', 'core.tools.agent_builder_tools.agent_config_tool', 'AgentConfigTool'),
    ('agent_creation_tool', 'core.tools.agent_creation_tool', 'AgentCreationTool'),
    ('mcp_search_tool', 'core.tools.agent_builder_tools.mcp_search_tool', 'MCPSearchTool'),
    ('credential_profile_tool', 'core.tools.agent_builder_tools.credential_profile_tool', 'CredentialProfileTool'),
    ('trigger_tool', 'core.tools.agent_builder_tools.trigger_tool', 'TriggerTool'),
]

# Combined registry of all tools
ALL_TOOLS = CORE_TOOLS + SANDBOX_TOOLS + SEARCH_TOOLS + UTILITY_TOOLS + AGENT_BUILDER_TOOLS


def get_tool_class(module_path: str, class_name: str) -> Type[Tool]:
    """
    Dynamically import and return a tool class.
    
    Args:
        module_path: Python module path (e.g., 'core.tools.sb_files_tool')
        class_name: Class name within the module (e.g., 'SandboxFilesTool')
    
    Returns:
        Tool class
    """
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def get_all_tools() -> Dict[str, Type[Tool]]:
    """
    Get a dictionary mapping tool names to their classes.
    
    Returns:
        Dict mapping tool names (str) to tool classes (Type[Tool])
        Example: {'sb_files_tool': SandboxFilesTool, 'browser_tool': BrowserTool, ...}
    """
    tools_map = {}
    for tool_name, module_path, class_name in ALL_TOOLS:
        try:
            tools_map[tool_name] = get_tool_class(module_path, class_name)
        except (ImportError, AttributeError) as e:
            # Tool may not be available in all environments
            # (e.g., missing dependencies, optional features)
            from core.utils.logger import logger
            logger.debug(f"Skipping tool {tool_name}: {e}")
    
    return tools_map


def get_tool_info(tool_name: str) -> Optional[Tuple[str, str, str]]:
    """
    Get module path and class name for a tool by its name.
    
    Args:
        tool_name: Tool name (e.g., 'sb_files_tool')
    
    Returns:
        Tuple of (tool_name, module_path, class_name) or None if not found
    """
    for name, module_path, class_name in ALL_TOOLS:
        if name == tool_name:
            return (name, module_path, class_name)
    return None


def get_tools_by_category() -> Dict[str, List[Tuple[str, str, str]]]:
    """
    Get tools organized by category.
    
    Returns:
        Dict mapping category names to lists of (tool_name, module_path, class_name) tuples
    """
    return {
        'core': CORE_TOOLS,
        'sandbox': SANDBOX_TOOLS,
        'agentcore': AGENTCORE_TOOLS,
        'search': SEARCH_TOOLS,
        'utility': UTILITY_TOOLS,
        'agent_builder': AGENT_BUILDER_TOOLS,
    }


def get_all_tools_with_agentcore() -> Dict[str, Type[Tool]]:
    """
    Get tools dynamically choosing between Daytona and AgentCore based on configuration.
    
    Returns:
        Dict mapping tool names (str) to tool classes (Type[Tool])
    """
    from core.utils.config import config
    from core.utils.logger import logger
    
    # Start with core tools
    tools_map = {}
    for tool_name, module_path, class_name in CORE_TOOLS:
        try:
            tools_map[tool_name] = get_tool_class(module_path, class_name)
        except (ImportError, AttributeError) as e:
            logger.debug(f"Skipping tool {tool_name}: {e}")
    
    # Add search, utility, and agent builder tools
    for tools_list in [SEARCH_TOOLS, UTILITY_TOOLS, AGENT_BUILDER_TOOLS]:
        for tool_name, module_path, class_name in tools_list:
            try:
                tools_map[tool_name] = get_tool_class(module_path, class_name)
            except (ImportError, AttributeError) as e:
                logger.debug(f"Skipping tool {tool_name}: {e}")
    
    # Choose sandbox backend based on configuration
    # Use AgentCore if configured, otherwise fallback to Daytona
    use_agentcore = config.USE_AGENTCORE
    
    if use_agentcore:
        logger.info("🚀 Using AWS AgentCore for sandbox tools")
        # Use AgentCore tools
        for tool_name, module_path, class_name in AGENTCORE_TOOLS:
            try:
                tools_map[tool_name] = get_tool_class(module_path, class_name)
                logger.debug(f"✅ Loaded AgentCore tool: {tool_name}")
            except (ImportError, AttributeError) as e:
                logger.warning(f"⚠️ Failed to load AgentCore tool {tool_name}: {e}")
                # Fall back to Daytona tools if AgentCore tools fail to load
                try:
                    daytona_tool = next((t for t in SANDBOX_TOOLS if t[0] == tool_name), None)
                    if daytona_tool:
                        tools_map[tool_name] = get_tool_class(daytona_tool[1], daytona_tool[2])
                        logger.info(f"🔄 Fell back to Daytona tool for: {tool_name}")
                except (ImportError, AttributeError):
                    logger.error(f"❌ Failed to load both AgentCore and Daytona tools for: {tool_name}")
    else:
        logger.info("🏖️ Using Daytona.io for sandbox tools")
        # Use Daytona tools
        for tool_name, module_path, class_name in SANDBOX_TOOLS:
            try:
                tools_map[tool_name] = get_tool_class(module_path, class_name)
                logger.debug(f"✅ Loaded Daytona tool: {tool_name}")
            except (ImportError, AttributeError) as e:
                logger.warning(f"⚠️ Failed to load Daytona tool {tool_name}: {e}")
    
    return tools_map

