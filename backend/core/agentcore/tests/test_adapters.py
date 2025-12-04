"""
Tests for AgentCore adapters
"""

import pytest
from unittest.mock import patch, MagicMock

from core.agentcore.config import AgentCoreConfig, Environment
from core.agentcore.adapters.runtime import AgentCoreRuntimeAdapter
from core.agentcore.adapters.memory import AgentCoreMemoryAdapter
from core.agentcore.adapters.code_interpreter import AgentCoreCodeInterpreterAdapter
from core.agentcore.adapters.browser import AgentCoreBrowserAdapter
from core.agentcore.adapters.gateway import AgentCoreGatewayAdapter


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
