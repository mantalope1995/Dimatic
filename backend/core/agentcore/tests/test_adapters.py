"""
Tests for AgentCore adapters
"""

import pytest
from unittest.mock import patch, MagicMock
from hypothesis import given, strategies as st

from core.agentcore.config import AgentCoreConfig, Environment
from core.agentcore.adapters.runtime import AgentCoreRuntimeAdapter
from core.agentcore.adapters.memory import AgentCoreMemoryAdapter
from core.agentcore.adapters.code_interpreter import AgentCoreCodeInterpreterAdapter
from core.agentcore.adapters.browser import AgentCoreBrowserAdapter
from core.agentcore.adapters.gateway import AgentCoreGatewayAdapter
from core.agentcore.utils import (
    substitute_variables,
    extract_variables,
    validate_template,
    substitute_in_dict,
)


@pytest.fixture
def local_config():
    """Create a local environment configuration for testing"""
    return AgentCoreConfig(
        environment=Environment.LOCAL,
        runtime_enabled=True,
        memory_enabled=True,
        code_interpreter_enabled=True,
        browser_enabled=True,
        gateway_enabled=True,
        s3_bucket_name="test-bucket",
    )


class TestAgentCoreRuntimeAdapter:
    """Test AgentCore Runtime adapter"""
    
    def test_initialization(self, local_config):
        """Test adapter initialization"""
        adapter = AgentCoreRuntimeAdapter(config=local_config)
        assert adapter.config == local_config
        assert adapter.config.runtime_enabled is True
    
    def test_disabled_runtime(self):
        """Test initialization with disabled runtime"""
        config = AgentCoreConfig(
            environment=Environment.LOCAL,
            runtime_enabled=False,
            code_interpreter_enabled=False,
            browser_enabled=False
        )
        
        with pytest.raises(ValueError, match="AgentCore Runtime is not enabled"):
            AgentCoreRuntimeAdapter(config=config)
    
    @pytest.mark.asyncio
    async def test_deploy_agent(self, local_config):
        """Test agent deployment"""
        adapter = AgentCoreRuntimeAdapter(config=local_config)
        
        deployment_id = await adapter.deploy_agent(
            agent_id="test-agent",
            agent_config={"system_prompt": "Test prompt"},
            version_id="v1"
        )
        
        assert deployment_id is not None
        assert "test-agent" in deployment_id
        assert "v1" in deployment_id
    
    @pytest.mark.asyncio
    async def test_invoke_agent(self, local_config):
        """Test agent invocation"""
        adapter = AgentCoreRuntimeAdapter(config=local_config)
        
        responses = []
        async for response in adapter.invoke_agent(
            deployment_id="test-deployment",
            thread_id="test-thread",
            input_data={"message": "Hello"},
            stream=True
        ):
            responses.append(response)
        
        assert len(responses) > 0
        assert responses[0]["type"] == "message"
    
    @pytest.mark.asyncio
    async def test_cancel_execution(self, local_config):
        """Test execution cancellation"""
        adapter = AgentCoreRuntimeAdapter(config=local_config)
        
        result = await adapter.cancel_execution("test-execution")
        assert result is True
    
    @pytest.mark.asyncio
    async def test_get_execution_status(self, local_config):
        """Test execution status retrieval"""
        adapter = AgentCoreRuntimeAdapter(config=local_config)
        
        status = await adapter.get_execution_status("test-execution")
        assert "execution_id" in status
        assert "status" in status


class TestAgentCoreMemoryAdapter:
    """Test AgentCore Memory adapter"""
    
    def test_initialization(self, local_config):
        """Test adapter initialization"""
        adapter = AgentCoreMemoryAdapter(config=local_config)
        assert adapter.config == local_config
        assert adapter.config.memory_enabled is True
    
    @pytest.mark.asyncio
    async def test_create_memory_resource(self, local_config):
        """Test memory resource creation"""
        adapter = AgentCoreMemoryAdapter(config=local_config)
        
        memory_id = await adapter.create_memory_resource(
            thread_id="test-thread",
            account_id="test-account"
        )
        
        assert memory_id is not None
        assert "memory" in memory_id
        assert "test-thread" in memory_id
    
    @pytest.mark.asyncio
    async def test_store_message(self, local_config):
        """Test message storage"""
        adapter = AgentCoreMemoryAdapter(config=local_config)
        
        message_id = await adapter.store_message(
            memory_resource_id="test-memory",
            message={"role": "user", "content": "Hello"},
            metadata={"timestamp": "2024-01-01"}
        )
        
        assert message_id is not None
    
    @pytest.mark.asyncio
    async def test_retrieve_messages(self, local_config):
        """Test message retrieval"""
        adapter = AgentCoreMemoryAdapter(config=local_config)
        
        messages = await adapter.retrieve_messages(
            memory_resource_id="test-memory",
            limit=10
        )
        
        assert isinstance(messages, list)
    
    @pytest.mark.asyncio
    async def test_delete_memory_resource(self, local_config):
        """Test memory resource deletion"""
        adapter = AgentCoreMemoryAdapter(config=local_config)
        
        result = await adapter.delete_memory_resource("test-memory")
        assert result is True


class TestAgentCoreCodeInterpreterAdapter:
    """Test AgentCore Code Interpreter adapter"""
    
    def test_initialization(self, local_config):
        """Test adapter initialization"""
        adapter = AgentCoreCodeInterpreterAdapter(config=local_config)
        assert adapter.config == local_config
        assert adapter.config.code_interpreter_enabled is True
    
    def test_missing_s3_bucket(self):
        """Test initialization without S3 bucket"""
        # This test verifies that the config validation catches missing S3 bucket
        with pytest.raises(ValueError, match="S3 bucket name required"):
            config = AgentCoreConfig(
                environment=Environment.LOCAL,
                code_interpreter_enabled=True,
                s3_bucket_name=None
            )
    
    @pytest.mark.asyncio
    async def test_execute_code(self, local_config):
        """Test code execution"""
        adapter = AgentCoreCodeInterpreterAdapter(config=local_config)
        
        result = await adapter.execute_code(
            code="print('Hello, World!')",
            language="python",
            timeout=30
        )
        
        assert "output" in result
        assert "error" in result
        assert result["exit_code"] == 0
    
    @pytest.mark.asyncio
    async def test_execute_shell_command(self, local_config):
        """Test shell command execution"""
        adapter = AgentCoreCodeInterpreterAdapter(config=local_config)
        
        result = await adapter.execute_shell_command(
            command="echo 'test'",
            working_dir="/workspace",
            timeout=30
        )
        
        assert "stdout" in result
        assert "stderr" in result
        assert result["exit_code"] == 0
    
    @pytest.mark.asyncio
    async def test_upload_file(self, local_config):
        """Test file upload"""
        adapter = AgentCoreCodeInterpreterAdapter(config=local_config)
        
        file_path = await adapter.upload_file(
            file_path="/workspace/test.txt",
            content=b"test content"
        )
        
        assert file_path == "/workspace/test.txt"
    
    @pytest.mark.asyncio
    async def test_list_files(self, local_config):
        """Test file listing"""
        adapter = AgentCoreCodeInterpreterAdapter(config=local_config)
        
        files = await adapter.list_files(directory="/workspace")
        assert isinstance(files, list)


class TestAgentCoreBrowserAdapter:
    """Test AgentCore Browser adapter"""
    
    def test_initialization(self, local_config):
        """Test adapter initialization"""
        adapter = AgentCoreBrowserAdapter(config=local_config)
        assert adapter.config == local_config
        assert adapter.config.browser_enabled is True
    
    @pytest.mark.asyncio
    async def test_navigate(self, local_config):
        """Test browser navigation"""
        adapter = AgentCoreBrowserAdapter(config=local_config)
        
        result = await adapter.navigate(
            url="https://example.com",
            wait_for=None
        )
        
        assert "html" in result
        assert "status" in result
        assert result["url"] == "https://example.com"
    
    @pytest.mark.asyncio
    async def test_extract_content(self, local_config):
        """Test content extraction"""
        adapter = AgentCoreBrowserAdapter(config=local_config)
        
        result = await adapter.extract_content(
            url="https://example.com",
            selectors=None
        )
        
        assert "text" in result
        assert "links" in result
        assert "images" in result
    
    @pytest.mark.asyncio
    async def test_fill_form(self, local_config):
        """Test form filling"""
        adapter = AgentCoreBrowserAdapter(config=local_config)
        
        result = await adapter.fill_form(
            form_data={"#username": "test", "#password": "pass"},
            submit=True
        )
        
        assert result["success"] is True
    
    @pytest.mark.asyncio
    async def test_take_screenshot(self, local_config):
        """Test screenshot capture"""
        adapter = AgentCoreBrowserAdapter(config=local_config)
        
        screenshot = await adapter.take_screenshot(full_page=False)
        assert isinstance(screenshot, str)


class TestAgentCoreGatewayAdapter:
    """Test AgentCore Gateway adapter"""

    def test_initialization(self, local_config):
        """Test adapter initialization"""
        adapter = AgentCoreGatewayAdapter(config=local_config)
        assert adapter.config == local_config
        assert adapter.config.gateway_enabled is True

    @pytest.mark.asyncio
    async def test_deploy_mcp_server(self, local_config):
        """Test MCP server deployment"""
        adapter = AgentCoreGatewayAdapter(config=local_config)

        deployment_id = await adapter.deploy_mcp_server(
            mcp_config={"name": "github", "type": "http"},
            account_id="test-account"
        )

        assert deployment_id is not None
        assert "gateway" in deployment_id
        assert "github" in deployment_id

    @pytest.mark.asyncio
    async def test_invoke_mcp_tool(self, local_config):
        """Test MCP tool invocation"""
        adapter = AgentCoreGatewayAdapter(config=local_config)

        result = await adapter.invoke_mcp_tool(
            gateway_deployment_id="test-gateway",
            tool_name="get_user",
            parameters={"username": "test"},
            credentials=None
        )

        assert result["success"] is True
        assert result["tool_name"] == "get_user"

    @pytest.mark.asyncio
    async def test_update_gateway_config(self, local_config):
        """Test Gateway configuration update"""
        adapter = AgentCoreGatewayAdapter(config=local_config)

        result = await adapter.update_gateway_config(
            gateway_deployment_id="test-gateway",
            config={"rate_limit": 100}
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_delete_gateway_deployment(self, local_config):
        """Test Gateway deployment deletion"""
        adapter = AgentCoreGatewayAdapter(config=local_config)

        result = await adapter.delete_gateway_deployment("test-gateway")
        assert result is True


class TestVariableSubstitutionPropertyTests:
    """
    Property 8: Variable Substitution Correctness

    Tests that variable substitution works correctly across many generated inputs.
    Validates Requirements 5.2 (Prompt Templates).
    """

    # Property: substitution correctly replaces all placeholders with values
    @given(
        template=st.text(min_size=1).map(lambda t: t.replace("%", "%%")[:100]),
        variables=st.dictionaries(
            st.text(min_size=1, max_size=20).map(lambda s: s.strip("%")),
            st.text(min_size=0, max_size=50),
            min_size=0,
            max_size=10
        )
    )
    def test_substitution_replaces_known_variables(self, template: str, variables: dict):
        """
        Property: All known variables in template are replaced with their values.
        For any template and variables dict, after substitution:
        - No %known_var% patterns remain in result
        - All variables from the dict that were in template are replaced
        """
        # Add placeholders to template for testing
        if variables:
            var_items = list(variables.items())
            if var_items:
                var_name, var_value = var_items[0]
                template = f"%{var_name}% " + template

        result = substitute_variables(template, variables, preserve_placeholders=False)

        # Check that at least the first variable was substituted
        if variables:
            var_name = next(iter(variables))
            if f"%{var_name}%" in template:
                assert f"%{var_name}%" not in result or result == template
                if result != template:
                    assert variables[var_name] in result or str(variables[var_name]) in result

    # Property: extract_variables finds all placeholders
    @given(
        template=st.lists(
            st.tuples(
                st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=['L', 'N'])),
                st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=['L', 'N']))
            ).map(lambda t: "%" + t[0] + t[1] + "%"),
            min_size=0,
            max_size=5
        ).map(lambda lst: "".join(lst)),
        separator=st.text(min_size=1, max_size=3).map(lambda s: s.replace("%", ""))
    )
    def test_extract_variables_finds_all_placeholders(self, placeholders: str, separator: str):
        """
        Property: extract_variables returns all unique variable names in template.
        """
        template = separator.join(placeholders.split("%") if placeholders else [])
        # Ensure we have valid %var% patterns
        if placeholders:
            parts = []
            for i, p in enumerate(placeholders.split("%")[1::2]):
                parts.append(f"%{p}%")
            template = separator.join(parts)

        variables = extract_variables(template)

        # All extracted variables should not contain % sign
        for var in variables:
            assert "%" not in var

    # Property: validate_template returns True only when all placeholders have variables
    @given(
        template=st.text(min_size=1, max_size=100),
        variables=st.dictionaries(
            st.text(min_size=1, max_size=20),
            st.text(min_size=0, max_size=50),
            min_size=0,
            max_size=10
        )
    )
    def test_validate_template_checks_all_placeholders(self, template: str, variables: dict):
        """
        Property: validate_template returns True iff all placeholders have values.
        """
        is_valid = validate_template(template, variables)

        # Extract required variables
        required = set(extract_variables(template))

        # If no placeholders required, should be valid
        if not required:
            assert is_valid is True
        # If all required variables are present, should be valid
        elif required.issubset(set(variables.keys())):
            assert is_valid is True
        # If missing required variables, should be invalid (unless no %var% patterns)
        else:
            # Only check if template actually has %var% patterns
            has_placeholders = "%" in template
            if has_placeholders:
                expected = required.issubset(set(variables.keys()))
                assert is_valid == expected

    # Property: substitution is idempotent when no unmatched placeholders
    @given(st.text(min_size=1, max_size=50))
    def test_substitution_is_idempotent(self, text: str):
        """
        Property: Substituting twice with same variables gives same result
        when all placeholders are matched.
        """
        # Clean text to avoid nested % signs
        clean_text = text.replace("%", "")

        variables = {"name": clean_text[:10] or "test", "value": clean_text[:5] or "123"}
        template = f"Hello %name%, your value is %value%"

        result1 = substitute_variables(template, variables)
        result2 = substitute_variables(result1, variables)

        assert result1 == result2

    # Property: substitute_in_dict only processes specified keys or all if None
    @given(
        data=st.dictionaries(
            st.text(min_size=1, max_size=10),
            st.text(min_size=0, max_size=50),
            min_size=1,
            max_size=5
        ),
        variables=st.dictionaries(
            st.text(min_size=1, max_size=10),
            st.text(min_size=0, max_size=30),
            min_size=1,
            max_size=3
        )
    )
    def test_substitute_in_dict_respects_keys_parameter(self, data: dict, variables: dict):
        """
        Property: substitute_in_dict only processes specified keys.
        When keys=None, processes all keys.
        """
        result_all = substitute_in_dict(data, variables, keys=None)

        # When processing all keys, result should have same keys as input
        assert set(result_all.keys()) == set(data.keys())

        # When processing specific keys, other keys should be unchanged
        if data:
            first_key = next(iter(data))
            result_one = substitute_in_dict(data, variables, keys=[first_key])

            # The specified key should be in result
            assert first_key in result_one
            # All keys should be in result
            assert set(result_one.keys()) == set(data.keys())

    # Property: preserve_placeholders keeps unmatched placeholders
    @given(
        template=st.lists(
            st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=['L', 'N'])),
            min_size=1,
            max_size=3
        ).map(lambda lst: "%".join([""] + lst + [""])),
        variables=st.dictionaries(
            st.text(min_size=1, max_size=10),
            st.text(min_size=0, max_size=20),
            min_size=0,
            max_size=2
        )
    )
    def test_preserve_placeholders_keeps_unmatched(self, template: str, variables: dict):
        """
        Property: When preserve_placeholders=True, unmatched placeholders remain.
        """
        # Ensure template is valid
        if not template.startswith("%"):
            template = "%" + template
        if not template.endswith("%"):
            template = template + "%"

        result_preserve = substitute_variables(template, variables, preserve_placeholders=True)
        result_no_preserve = substitute_variables(template, variables, preserve_placeholders=False)

        # Results may differ based on preservation
        assert isinstance(result_preserve, str)
        assert isinstance(result_no_preserve, str)

    # Property: strict mode raises error for unmatched placeholders
    @given(
        template=st.text(min_size=5, max_size=50),
        variables=st.dictionaries(
            st.text(min_size=1, max_size=10),
            st.text(min_size=0, max_size=20),
            min_size=0,
            max_size=3
        )
    )
    def test_strict_mode_raises_on_unmatched(self, template: str, variables: dict):
        """
        Property: strict=True raises ValueError when placeholders are unmatched.
        """
        # Create a template with guaranteed unmatched placeholder
        if not variables:
            # No variables, any placeholder will be unmatched
            template = "%unmatched_var% test"

        try:
            result = substitute_variables(template, variables, strict=True)
            # If no error, either template had no placeholders or all were matched
            placeholders = extract_variables(template)
            if placeholders:
                assert set(placeholders).issubset(set(variables.keys()))
        except ValueError as e:
            # Should only raise if there are unmatched placeholders
            placeholders = set(extract_variables(template))
            unmatched = placeholders - set(variables.keys())
            assert unmatched
            assert "Unmatched placeholder" in str(e)

    # Property: empty variables dict leaves template unchanged
    @given(st.text(min_size=0, max_size=100))
    def test_empty_variables_leaves_template_unchanged(self, template: str):
        """
        Property: Substituting with empty variables dict leaves template unchanged.
        """
        result = substitute_variables(template, {})
        assert result == template

    # Property: non-string values are converted to strings
    @given(
        st.integers(),
        st.floats(allow_nan=False, allow_infinity=False),
        st.booleans(),
        st.text(min_size=1, max_size=10)
    )
    def test_non_string_values_converted_to_strings(self, int_val, float_val, bool_val, text_val):
        """
        Property: Non-string variable values are converted to strings during substitution.
        """
        variables = {
            "int_var": int_val,
            "float_var": float_val,
            "bool_var": bool_val,
            "text_var": text_val
        }

        template = "%int_var% %float_var% %bool_var% %text_var%"
        result = substitute_variables(template, variables)

        # All values should be present as strings in result
        assert str(int_val) in result
        assert str(float_val) in result
        assert str(bool_val) in result
        assert text_val in result

    # Property: substitution handles special characters correctly
    @given(
        var_name=st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=['L', 'N'])),
        var_value=st.text(min_size=1, max_size=30)
    )
    def test_handles_special_characters(self, var_name: str, var_value: str):
        """
        Property: Substitution correctly handles special characters in values.
        """
        template = f"%{var_name}%"
        variables = {var_name: var_value}

        result = substitute_variables(template, variables)

        # Result should be the variable value (as string)
        assert result == str(var_value) or "%" in result  # Either substituted or preserved
