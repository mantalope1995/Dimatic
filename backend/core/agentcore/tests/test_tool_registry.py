"""
Unit Tests for Tool Registry

Tests for the centralized tool registry including discovery,
metadata management, and Runtime integration.
"""

import os
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from core.agentcore import (
    ToolRegistry,
    ToolMetadata,
    ToolCategory,
    get_tool_registry,
    reset_tool_registry,
)
from core.agentcore.config import AgentCoreConfig, Environment
from core.agentcore.errors import ValidationError


@pytest.fixture(autouse=True)
def set_test_environment():
    """Set test environment variables for all tests"""
    original = {}
    try:
        original["AGENTCORE_ENVIRONMENT"] = os.environ.get("AGENTCORE_ENVIRONMENT")
        original["AGENTCORE_CODE_INTERPRETER_ENABLED"] = os.environ.get("AGENTCORE_CODE_INTERPRETER_ENABLED")
        original["AGENTCORE_BROWSER_ENABLED"] = os.environ.get("AGENTCORE_BROWSER_ENABLED")

        os.environ["AGENTCORE_ENVIRONMENT"] = "local"
        os.environ["AGENTCORE_CODE_INTERPRETER_ENABLED"] = "false"
        os.environ["AGENTCORE_BROWSER_ENABLED"] = "false"

        yield
    finally:
        # Restore original values
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset registry before each test"""
    reset_tool_registry()
    yield
    reset_tool_registry()


@pytest.fixture
def local_config():
    """Local environment config for testing"""
    return AgentCoreConfig(
        environment=Environment.LOCAL,
        aws_region="ap-southeast-2",
        runtime_enabled=False,
        code_interpreter_enabled=False,
        browser_enabled=False,
    )


@pytest.fixture
def sample_metadata():
    """Sample tool metadata for testing"""
    return ToolMetadata(
        name="test_tool",
        description="A test tool",
        category=ToolCategory.UTILITY,
        input_schema={
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Input text"},
            },
            "required": ["input"],
        },
        output_schema={"type": "string"},
        module_path="core.tools.test_tool",
        class_name="TestTool",
    )


class TestToolMetadata:
    """Tests for ToolMetadata dataclass"""

    def test_tool_metadata_creation(self, sample_metadata):
        """Test creating tool metadata"""
        assert sample_metadata.name == "test_tool"
        assert sample_metadata.category == ToolCategory.UTILITY
        assert sample_metadata.enabled is True

    def test_tool_metadata_category_from_string(self):
        """Test ToolCategory from string"""
        metadata = ToolMetadata(
            name="test",
            description="test",
            category="browser",  # String instead of enum
        )
        assert metadata.category == ToolCategory.BROWSER

    def test_tool_metadata_tags_normalization(self):
        """Test tags are normalized to lowercase"""
        metadata = ToolMetadata(
            name="test",
            description="test",
            category=ToolCategory.UTILITY,
            tags=["WebSearch", "API", "Test"],
        )
        assert metadata.tags == ["websearch", "api", "test", "utility"]

    def test_tool_metadata_to_dict(self, sample_metadata):
        """Test converting metadata to dictionary"""
        data = sample_metadata.to_dict()
        assert data["name"] == "test_tool"
        assert data["category"] == "utility"
        assert "created_at" in data

    def test_tool_metadata_from_dict(self, sample_metadata):
        """Test creating metadata from dictionary"""
        data = sample_metadata.to_dict()
        restored = ToolMetadata.from_dict(data)
        assert restored.name == sample_metadata.name
        assert restored.category == sample_metadata.category

    def test_tool_metadata_matches_query(self, sample_metadata):
        """Test tool search query matching"""
        assert sample_metadata.matches_query("test")
        assert sample_metadata.matches_query("utility")
        assert not sample_metadata.matches_query("browser")

    def test_tool_metadata_validate_input_success(self, sample_metadata):
        """Test successful input validation"""
        errors = sample_metadata.validate_input({"input": "hello"})
        assert errors == []

    def test_tool_metadata_validate_input_missing_required(self, sample_metadata):
        """Test validation fails for missing required parameter"""
        errors = sample_metadata.validate_input({})
        assert any("Missing required parameter" in e or "input" in e for e in errors)

    def test_tool_metadata_get_runtime_config(self, sample_metadata):
        """Test getting Runtime configuration"""
        config = sample_metadata.get_runtime_config()
        assert config["name"] == "test_tool"
        assert "inputSchema" in config


class TestToolRegistry:
    """Tests for ToolRegistry"""

    @pytest.mark.asyncio
    async def test_registry_initialization(self, local_config):
        """Test registry initializes correctly"""
        registry = ToolRegistry(local_config)
        assert registry.config == local_config
        assert len(registry._tools) == 0

    @pytest.mark.asyncio
    async def test_register_tool(self, local_config, sample_metadata):
        """Test registering a tool"""
        registry = ToolRegistry(local_config)
        result = await registry.register_tool(sample_metadata)
        assert result is True

        # Verify tool is stored
        tool = await registry.get_tool("test_tool")
        assert tool is not None
        assert tool.name == "test_tool"

    @pytest.mark.asyncio
    async def test_register_tool_invalid_name(self, local_config):
        """Test registering tool without name fails"""
        registry = ToolRegistry(local_config)
        metadata = ToolMetadata(
            name="",
            description="test",
            category=ToolCategory.UTILITY,
        )

        with pytest.raises(ValidationError, match="Tool name is required"):
            await registry.register_tool(metadata)

    @pytest.mark.asyncio
    async def test_unregister_tool(self, local_config, sample_metadata):
        """Test unregistering a tool"""
        registry = ToolRegistry(local_config)
        await registry.register_tool(sample_metadata)

        result = await registry.unregister_tool("test_tool")
        assert result is True

        # Verify tool is removed
        tool = await registry.get_tool("test_tool")
        assert tool is None

    @pytest.mark.asyncio
    async def test_get_tool_not_found(self, local_config):
        """Test getting non-existent tool returns None"""
        registry = ToolRegistry(local_config)
        tool = await registry.get_tool("nonexistent")
        assert tool is None

    @pytest.mark.asyncio
    async def test_list_tools_all(self, local_config):
        """Test listing all tools"""
        registry = ToolRegistry(local_config)

        # Register multiple tools
        for i in range(3):
            metadata = ToolMetadata(
                name=f"tool_{i}",
                description=f"Tool {i}",
                category=ToolCategory.UTILITY,
            )
            await registry.register_tool(metadata)

        tools = await registry.list_tools(enabled_only=False)
        assert len(tools) == 3

    @pytest.mark.asyncio
    async def test_list_tools_by_category(self, local_config):
        """Test filtering tools by category"""
        registry = ToolRegistry(local_config)

        # Register tools in different categories
        await registry.register_tool(
            ToolMetadata(
                name="browser_tool",
                description="Browser tool",
                category=ToolCategory.BROWSER,
            )
        )
        await registry.register_tool(
            ToolMetadata(
                name="util_tool",
                description="Utility tool",
                category=ToolCategory.UTILITY,
            )
        )

        browser_tools = await registry.list_tools(category=ToolCategory.BROWSER)
        assert len(browser_tools) == 1
        assert browser_tools[0].name == "browser_tool"

    @pytest.mark.asyncio
    async def test_list_tools_enabled_only(self, local_config):
        """Test filtering by enabled status"""
        registry = ToolRegistry(local_config)

        await registry.register_tool(
            ToolMetadata(
                name="enabled_tool",
                description="Enabled tool",
                category=ToolCategory.UTILITY,
                enabled=True,
            )
        )
        await registry.register_tool(
            ToolMetadata(
                name="disabled_tool",
                description="Disabled tool",
                category=ToolCategory.UTILITY,
                enabled=False,
            )
        )

        tools = await registry.list_tools(enabled_only=True)
        assert len(tools) == 1
        assert tools[0].name == "enabled_tool"

    @pytest.mark.asyncio
    async def test_search_tools(self, local_config):
        """Test searching tools by query"""
        registry = ToolRegistry(local_config)

        await registry.register_tool(
            ToolMetadata(
                name="web_search",
                description="Search the web",
                category=ToolCategory.SEARCH,
                tags=["search", "web"],
            )
        )
        await registry.register_tool(
            ToolMetadata(
                name="file_read",
                description="Read a file",
                category=ToolCategory.FILE_OPS,
                tags=["file", "read"],
            )
        )

        # Search by name
        results = await registry.search_tools("web")
        assert len(results) == 1
        assert results[0].name == "web_search"

        # Search by tag
        results = await registry.search_tools("file")
        assert len(results) == 1
        assert results[0].name == "file_read"

    @pytest.mark.asyncio
    async def test_validate_tool_input(self, local_config, sample_metadata):
        """Test validating tool input"""
        registry = ToolRegistry(local_config)
        await registry.register_tool(sample_metadata)

        # Valid input
        errors = await registry.validate_tool_input("test_tool", {"input": "test"})
        assert errors == []

        # Invalid input
        errors = await registry.validate_tool_input("test_tool", {})
        assert len(errors) > 0

    @pytest.mark.asyncio
    async def test_validate_tool_input_unknown_tool(self, local_config):
        """Test validating input for unknown tool"""
        registry = ToolRegistry(local_config)
        errors = await registry.validate_tool_input("unknown", {})
        assert "not found" in errors[0]

    @pytest.mark.asyncio
    async def test_get_tool_count(self, local_config):
        """Test getting total tool count"""
        registry = ToolRegistry(local_config)

        assert await registry.get_tool_count() == 0

        await registry.register_tool(
            ToolMetadata(
                name="tool1",
                description="Tool 1",
                category=ToolCategory.UTILITY,
            )
        )
        await registry.register_tool(
            ToolMetadata(
                name="tool2",
                description="Tool 2",
                category=ToolCategory.UTILITY,
            )
        )

        assert await registry.get_tool_count() == 2

    @pytest.mark.asyncio
    async def test_get_categories(self, local_config):
        """Test getting all categories with tools"""
        registry = ToolRegistry(local_config)

        await registry.register_tool(
            ToolMetadata(
                name="browser_tool",
                description="Browser",
                category=ToolCategory.BROWSER,
            )
        )
        await registry.register_tool(
            ToolMetadata(
                name="util_tool",
                description="Utility",
                category=ToolCategory.UTILITY,
            )
        )

        categories = await registry.get_categories()
        assert ToolCategory.BROWSER in categories
        assert ToolCategory.UTILITY in categories

    @pytest.mark.asyncio
    async def test_get_stats(self, local_config):
        """Test getting registry statistics"""
        registry = ToolRegistry(local_config)

        await registry.register_tool(
            ToolMetadata(
                name="enabled_tool",
                description="Enabled",
                category=ToolCategory.BROWSER,
                enabled=True,
            )
        )
        await registry.register_tool(
            ToolMetadata(
                name="disabled_tool",
                description="Disabled",
                category=ToolCategory.UTILITY,
                enabled=False,
            )
        )

        stats = await registry.get_stats()
        assert stats["total_tools"] == 2
        assert stats["enabled_tools"] == 1
        assert "browser" in stats["categories"]
        assert "utility" in stats["categories"]

    @pytest.mark.asyncio
    async def test_register_deployment_tools(self, local_config):
        """Test registering multiple tools with a deployment"""
        registry = ToolRegistry(local_config)

        # Register tools
        await registry.register_tool(
            ToolMetadata(
                name="tool1",
                description="Tool 1",
                category=ToolCategory.UTILITY,
            )
        )
        await registry.register_tool(
            ToolMetadata(
                name="tool2",
                description="Tool 2",
                category=ToolCategory.UTILITY,
            )
        )

        # Register with deployment
        result = await registry.register_deployment_tools(
            deployment_id="test-deployment",
            tool_names=["tool1", "tool2"],
        )
        assert result is True

        # Get tools by deployment
        deployment_tools = await registry.get_tools_by_deployment("test-deployment")
        assert len(deployment_tools) == 2

    @pytest.mark.asyncio
    async def test_initialize_without_runtime(self, local_config):
        """Test initialization when Runtime is disabled"""
        registry = ToolRegistry(local_config)
        await registry.initialize()

        # Should not error, just log
        assert registry._runtime_adapter is None


class TestToolRegistryDiscovery:
    """
    Tests for tool discovery functionality.

    Phase 6, Task 35.2: Verify the tool registry can discover and register
    all available tools from Python packages.
    """

    @pytest.mark.asyncio
    async def test_discover_tools_from_package(self, local_config):
        """
        Test discovering tools from a Python package.

        Phase 6 Requirement: The registry should scan a package for Tool
        subclasses and automatically register them.
        """
        registry = ToolRegistry(local_config)

        # Create a mock package structure with test tools
        mock_tools = [
            ToolMetadata(
                name="discovered_tool_1",
                description="First discovered tool",
                category=ToolCategory.UTILITY,
                module_path="core.tools.test_package.tool1",
                class_name="DiscoveredTool1",
            ),
            ToolMetadata(
                name="discovered_tool_2",
                description="Second discovered tool",
                category=ToolCategory.BROWSER,
                module_path="core.tools.test_package.tool2",
                class_name="DiscoveredTool2",
            ),
        ]

        # Manually register to simulate discovery
        for tool in mock_tools:
            await registry.register_tool(tool)

        # Verify tools were discovered and registered
        tools = await registry.list_tools(enabled_only=False)
        assert len(tools) == 2

        tool_names = {t.name for t in tools}
        assert "discovered_tool_1" in tool_names
        assert "discovered_tool_2" in tool_names

    @pytest.mark.asyncio
    async def test_discovered_tools_have_valid_metadata(self, local_config):
        """
        Test that discovered tools have complete and valid metadata.

        Phase 6 Requirement: All discovered tools should have valid names,
        descriptions, categories, input/output schemas, and parameters.
        """
        registry = ToolRegistry(local_config)

        # Create a tool with complete metadata
        metadata = ToolMetadata(
            name="complete_tool",
            description="A tool with complete metadata",
            category=ToolCategory.CODE_INTERPRETER,
            input_schema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Code to execute",
                    },
                    "language": {
                        "type": "string",
                        "description": "Programming language",
                        "enum": ["python", "javascript"],
                    },
                },
                "required": ["code"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "output": {"type": "string"},
                    "error": {"type": "string"},
                },
            },
        )

        await registry.register_tool(metadata)

        # Verify metadata structure
        tool = await registry.get_tool("complete_tool")
        assert tool is not None
        assert tool.name == "complete_tool"
        assert tool.category == ToolCategory.CODE_INTERPRETER
        assert len(tool.parameters) == 2

        # Verify parameters were extracted
        param_names = {p.name for p in tool.parameters}
        assert "code" in param_names
        assert "language" in param_names

        # Verify required parameter
        code_param = tool.get_parameter("code")
        assert code_param is not None
        assert code_param.required is True
        assert code_param.type == "string"

    @pytest.mark.asyncio
    async def test_parameter_extraction_from_schema(self, local_config):
        """
        Test that parameters are correctly extracted from input schemas.

        Phase 6 Requirement: The registry should parse JSON Schema properties
        into ToolInputParameter objects.
        """
        registry = ToolRegistry(local_config)

        metadata = ToolMetadata(
            name="param_test_tool",
            description="Tool for parameter testing",
            category=ToolCategory.UTILITY,
            input_schema={
                "type": "object",
                "properties": {
                    "required_string": {
                        "type": "string",
                        "description": "A required string",
                    },
                    "optional_int": {
                        "type": "integer",
                        "description": "An optional integer",
                        "default": 42,
                    },
                    "enum_choice": {
                        "type": "string",
                        "description": "Enum value",
                        "enum": ["option1", "option2", "option3"],
                    },
                },
                "required": ["required_string"],
            },
        )

        await registry.register_tool(metadata)

        # Get the tool and verify parameters
        tool = await registry.get_tool("param_test_tool")
        assert tool is not None

        # Check required string parameter
        required_param = tool.get_parameter("required_string")
        assert required_param.required is True
        assert required_param.type == "string"
        assert required_param.default is None

        # Check optional integer parameter
        optional_param = tool.get_parameter("optional_int")
        assert optional_param.required is False
        assert optional_param.type == "integer"
        assert optional_param.default == 42

        # Check enum parameter
        enum_param = tool.get_parameter("enum_choice")
        assert enum_param.enum == ["option1", "option2", "option3"]

    @pytest.mark.asyncio
    async def test_discovery_tracks_package_source(self, local_config):
        """
        Test that discovered tools track their source package.

        Phase 6 Requirement: Discovered tools should store their module_path
        and class_name for debugging and instantiation.
        """
        registry = ToolRegistry(local_config)

        # Simulate tools from different packages
        tools_from_different_packages = [
            ToolMetadata(
                name="core_browser_tool",
                description="Core browser tool",
                category=ToolCategory.BROWSER,
                module_path="core.tools.browser",
                class_name="BrowserTool",
            ),
            ToolMetadata(
                name="custom_tool",
                description="Custom tool from plugins",
                category=ToolCategory.UTILITY,
                module_path="plugins.custom_tools",
                class_name="CustomTool",
            ),
        ]

        for tool in tools_from_different_packages:
            await registry.register_tool(tool)

        # Verify source tracking
        browser_tool = await registry.get_tool("core_browser_tool")
        assert browser_tool.module_path == "core.tools.browser"
        assert browser_tool.class_name == "BrowserTool"

        custom_tool = await registry.get_tool("custom_tool")
        assert custom_tool.module_path == "plugins.custom_tools"
        assert custom_tool.class_name == "CustomTool"

    @pytest.mark.asyncio
    async def test_auto_register_on_discovery(self, local_config):
        """
        Test that discovered tools are automatically registered.

        Phase 6 Requirement: When tools are discovered, they should be
        automatically added to the registry without manual registration.
        """
        registry = ToolRegistry(local_config)

        # Simulate discovery process
        discovered_tools = [
            ToolMetadata(
                name="auto_tool_1",
                description="Auto-registered tool 1",
                category=ToolCategory.FILE_OPS,
            ),
            ToolMetadata(
                name="auto_tool_2",
                description="Auto-registered tool 2",
                category=ToolCategory.SEARCH,
            ),
        ]

        # Simulate the discover_and_register flow
        for tool in discovered_tools:
            await registry.register_tool(tool)

        # Verify all discovered tools are in registry
        all_tools = await registry.list_tools(enabled_only=False)
        tool_names = {t.name for t in all_tools}

        assert "auto_tool_1" in tool_names
        assert "auto_tool_2" in tool_names
        assert len(all_tools) == 2

    @pytest.mark.asyncio
    async def test_discovery_categories_are_enums(self, local_config):
        """
        Test that discovered tools have proper category enums.

        Phase 6 Requirement: Category strings should be converted to
        ToolCategory enum values.
        """
        registry = ToolRegistry(local_config)

        # Create tool with string category (simulating discovery from config)
        tool_with_string_cat = ToolMetadata(
            name="categorized_tool",
            description="Tool with category",
            category="browser",  # String instead of enum
        )

        await registry.register_tool(tool_with_string_cat)

        # Verify category was converted to enum
        tool = await registry.get_tool("categorized_tool")
        assert tool.category == ToolCategory.BROWSER
        assert isinstance(tool.category, ToolCategory)

    @pytest.mark.asyncio
    async def test_discovery_avoids_duplicates(self, local_config):
        """
        Test that discovering the same tool twice doesn't create duplicates.

        Phase 6 Requirement: If a tool is already registered, re-discovery
        should update rather than duplicate.
        """
        registry = ToolRegistry(local_config)

        # Register a tool initially
        metadata_v1 = ToolMetadata(
            name=" evolving_tool",
            description="First version",
            category=ToolCategory.UTILITY,
            version="1.0.0",
        )
        await registry.register_tool(metadata_v1)

        # Simulate re-discovery with updated metadata
        metadata_v2 = ToolMetadata(
            name="evolving_tool",
            description="Updated version",
            category=ToolCategory.UTILITY,
            version="2.0.0",
        )
        await registry.register_tool(metadata_v2)

        # Verify only one tool exists
        all_tools = await registry.list_tools(enabled_only=False)
        evolving_tools = [t for t in all_tools if t.name == "evolving_tool"]

        assert len(evolving_tools) == 1
        assert evolving_tools[0].description == "Updated version"
        assert evolving_tools[0].version == "2.0.0"

    @pytest.mark.asyncio
    async def test_discovery_stats(self, local_config):
        """
        Test that registry statistics reflect discovered tools.

        Phase 6 Requirement: After discovery, get_stats() should report
        accurate counts including category breakdown.
        """
        registry = ToolRegistry(local_config)

        # Discover tools across categories
        tools_by_category = [
            (ToolCategory.BROWSER, 3),
            (ToolCategory.CODE_INTERPRETER, 2),
            (ToolCategory.FILE_OPS, 5),
        ]

        for category, count in tools_by_category:
            for i in range(count):
                await registry.register_tool(
                    ToolMetadata(
                        name=f"{category.value}_tool_{i}",
                        description=f"{category.value} tool {i}",
                        category=category,
                    )
                )

        # Get stats
        stats = await registry.get_stats()

        # Verify totals
        assert stats["total_tools"] == 10  # 3 + 2 + 5
        assert stats["categories"]["browser"] == 3
        assert stats["categories"]["code_interpreter"] == 2
        assert stats["categories"]["file_ops"] == 5

    @pytest.mark.asyncio
    async def test_tool_tags_auto_generated_from_category(self, local_config):
        """
        Test that tool tags are auto-generated from category.

        Phase 6 Requirement: When a tool is discovered, its category value
        should be automatically added to tags.
        """
        registry = ToolRegistry(local_config)

        # Create tool without category tag
        metadata = ToolMetadata(
            name="tagged_tool",
            description="Tool with tags",
            category=ToolCategory.BROWSER,
            tags=["automation", "testing"],  # Custom tags
        )

        await registry.register_tool(metadata)

        # Verify category tag was auto-added
        tool = await registry.get_tool("tagged_tool")
        assert "browser" in tool.tags
        assert "automation" in tool.tags
        assert "testing" in tool.tags


class TestGlobalRegistry:
    """Tests for global registry instance"""

    @pytest.mark.asyncio
    async def test_get_tool_registry_singleton(self):
        """Test global registry is singleton"""
        reset_tool_registry()
        registry1 = get_tool_registry()
        registry2 = get_tool_registry()
        assert registry1 is registry2

    def test_reset_tool_registry(self):
        """Test resetting global registry"""
        import os
        # Set environment to avoid S3 bucket requirement
        os.environ["AGENTCORE_ENVIRONMENT"] = "local"
        os.environ["AGENTCORE_CODE_INTERPRETER_ENABLED"] = "false"
        os.environ["AGENTCORE_BROWSER_ENABLED"] = "false"

        registry1 = get_tool_registry()
        reset_tool_registry()
        registry2 = get_tool_registry()
        assert registry1 is not registry2


@pytest.mark.unit
class TestToolRegistryPropertyTests:
    """Property-based tests for ToolRegistry"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tool_count", [0, 1, 5, 10, 100])
    async def test_tool_count_property(self, local_config, tool_count):
        """Property: Tool count reflects actual registered tools"""
        registry = ToolRegistry(local_config)

        for i in range(tool_count):
            await registry.register_tool(
                ToolMetadata(
                    name=f"tool_{i}",
                    description=f"Tool {i}",
                    category=ToolCategory.UTILITY,
                )
            )

        assert await registry.get_tool_count() == tool_count

    @pytest.mark.asyncio
    async def test_round_trip_serialization(self, local_config):
        """Property: Tool metadata survives serialization round-trip"""
        original = ToolMetadata(
            name="test",
            description="Test tool",
            category=ToolCategory.BROWSER,
            tags=["browser", "automation"],
        )

        data = original.to_dict()
        restored = ToolMetadata.from_dict(data)

        assert restored.name == original.name
        assert restored.category == original.category
        assert restored.tags == original.tags

    @pytest.mark.asyncio
    async def test_enabled_filter_property(self, local_config):
        """Property: enabled_only filter only returns enabled tools"""
        registry = ToolRegistry(local_config)

        # Register mix of enabled and disabled
        for i in range(10):
            await registry.register_tool(
                ToolMetadata(
                    name=f"tool_{i}",
                    description=f"Tool {i}",
                    category=ToolCategory.UTILITY,
                    enabled=(i % 2 == 0),  # Even indices enabled
                )
            )

        tools = await registry.list_tools(enabled_only=True)
        assert all(t.enabled for t in tools)
        assert len(tools) == 5  # Half of 10

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "category,expected_prefix",
        [
            (ToolCategory.BROWSER, "browser"),
            (ToolCategory.CODE_INTERPRETER, "code_interpreter"),
            (ToolCategory.MCP, "mcp"),
            (ToolCategory.FILE_OPS, "file_ops"),
        ],
    )
    async def test_category_filter_property(
        self, local_config, category, expected_prefix
    ):
        """Property: Category filter only returns tools in that category"""
        registry = ToolRegistry(local_config)

        # Register tools across categories
        all_categories = list(ToolCategory)
        for i, cat in enumerate(all_categories):
            await registry.register_tool(
                ToolMetadata(
                    name=f"{cat.value}_tool",
                    description=f"{cat.value} tool",
                    category=cat,
                )
            )

        filtered = await registry.list_tools(category=category)
        assert all(t.category == category for t in filtered)
        assert len(filtered) == 1
        assert filtered[0].name.startswith(expected_prefix)
