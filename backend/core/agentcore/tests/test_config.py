"""
Tests for AgentCore configuration management
"""

import os
import pytest
from unittest.mock import patch

from core.agentcore.config import (
    AgentCoreConfig,
    Environment,
    get_agentcore_config,
    reset_config,
)


class TestAgentCoreConfig:
    """Test AgentCore configuration"""
    
    def test_default_config(self):
        """Test default configuration values"""
        config = AgentCoreConfig(s3_bucket_name="test-bucket")
        
        assert config.environment == Environment.LOCAL
        assert config.aws_region == "us-east-1"
        assert config.runtime_enabled is True
        assert config.memory_enabled is True
        assert config.code_interpreter_enabled is True
        assert config.browser_enabled is True
        assert config.gateway_enabled is True
        assert config.fallback_to_database is True
    
    def test_environment_validation(self):
        """Test environment validation"""
        # Local environment should not require AWS credentials
        config = AgentCoreConfig(environment=Environment.LOCAL, s3_bucket_name="test-bucket")
        assert config.environment == Environment.LOCAL
        
        # Production environment should require AWS credentials
        with pytest.raises(ValueError, match="AWS credentials required"):
            AgentCoreConfig(
                environment=Environment.PRODUCTION,
                aws_access_key_id=None,
                aws_secret_access_key=None,
                s3_bucket_name="test-bucket"
            )
    
    def test_s3_bucket_validation(self):
        """Test S3 bucket validation"""
        # Code Interpreter requires S3 bucket
        with pytest.raises(ValueError, match="S3 bucket name required"):
            AgentCoreConfig(
                code_interpreter_enabled=True,
                s3_bucket_name=None
            )
        
        # Browser requires S3 bucket
        with pytest.raises(ValueError, match="S3 bucket name required"):
            AgentCoreConfig(
                browser_enabled=True,
                s3_bucket_name=None
            )
    
    def test_timeout_validation(self):
        """Test timeout validation"""
        with pytest.raises(ValueError, match="Runtime timeout must be positive"):
            AgentCoreConfig(runtime_timeout_seconds=0, s3_bucket_name="test-bucket")
        
        with pytest.raises(ValueError, match="Code Interpreter timeout must be positive"):
            AgentCoreConfig(
                code_interpreter_timeout_seconds=-1,
                code_interpreter_enabled=False,  # Disable to avoid S3 validation
                browser_enabled=False  # Disable to avoid S3 validation
            )
    
    def test_resource_prefix(self):
        """Test resource prefix generation"""
        config = AgentCoreConfig(
            environment=Environment.DEVELOPMENT,
            aws_access_key_id="test-key",
            aws_secret_access_key="test-secret",
            s3_bucket_name="test-bucket"
        )
        assert config.get_resource_prefix() == "agentcore-development"
        
        config = AgentCoreConfig(
            environment=Environment.PRODUCTION,
            aws_access_key_id="test-key",
            aws_secret_access_key="test-secret",
            s3_bucket_name="test-bucket"
        )
        assert config.get_resource_prefix() == "agentcore-production"
    
    def test_environment_checks(self):
        """Test environment check methods"""
        config = AgentCoreConfig(environment=Environment.LOCAL, s3_bucket_name="test-bucket")
        assert config.is_local() is True
        assert config.is_development() is False
        assert config.is_production() is False
        
        config = AgentCoreConfig(
            environment=Environment.PRODUCTION,
            aws_access_key_id="test-key",
            aws_secret_access_key="test-secret",
            s3_bucket_name="test-bucket"
        )
        assert config.is_local() is False
        assert config.is_development() is False
        assert config.is_production() is True


class TestGetAgentCoreConfig:
    """Test configuration loading from environment"""
    
    def setup_method(self):
        """Reset config before each test"""
        reset_config()
    
    def teardown_method(self):
        """Reset config after each test"""
        reset_config()
    
    @patch.dict(os.environ, {
        "AGENTCORE_ENVIRONMENT": "local",
        "AGENTCORE_RUNTIME_ENABLED": "true",
        "AGENTCORE_S3_BUCKET_NAME": "test-bucket",
    }, clear=False)
    def test_load_from_environment(self):
        """Test loading configuration from environment variables"""
        config = get_agentcore_config()
        
        assert config.environment == Environment.LOCAL
        assert config.runtime_enabled is True
    
    @patch.dict(os.environ, {
        "AGENTCORE_ENVIRONMENT": "development",
        "AGENTCORE_AWS_REGION": "us-west-2",
        "AGENTCORE_RUNTIME_TIMEOUT_SECONDS": "600",
        "AGENTCORE_AWS_ACCESS_KEY_ID": "test-key",
        "AGENTCORE_AWS_SECRET_ACCESS_KEY": "test-secret",
        "AGENTCORE_S3_BUCKET_NAME": "test-bucket",
    }, clear=False)
    def test_custom_values(self):
        """Test custom configuration values"""
        config = get_agentcore_config()
        
        assert config.environment == Environment.DEVELOPMENT
        assert config.aws_region == "us-west-2"
        assert config.runtime_timeout_seconds == 600
    
    @patch.dict(os.environ, {
        "AGENTCORE_ENVIRONMENT": "invalid",
    }, clear=False)
    def test_invalid_environment(self):
        """Test invalid environment value"""
        with pytest.raises(ValueError, match="Invalid AGENTCORE_ENVIRONMENT"):
            get_agentcore_config()
    
    @patch.dict(os.environ, {
        "AGENTCORE_RUNTIME_ENABLED": "false",
        "AGENTCORE_MEMORY_ENABLED": "0",
        "AGENTCORE_CODE_INTERPRETER_ENABLED": "no",
        "AGENTCORE_BROWSER_ENABLED": "false",
    }, clear=False)
    def test_boolean_parsing(self):
        """Test boolean flag parsing"""
        config = get_agentcore_config()
        
        assert config.runtime_enabled is False
        assert config.memory_enabled is False
        assert config.code_interpreter_enabled is False
    
    @patch.dict(os.environ, {
        "AGENTCORE_FALLBACK_TO_DATABASE": "true",
        "AGENTCORE_FALLBACK_TO_LEGACY_SANDBOX": "false",
        "AGENTCORE_S3_BUCKET_NAME": "test-bucket",
    }, clear=False)
    def test_fallback_configuration(self):
        """Test fallback configuration"""
        config = get_agentcore_config()
        
        assert config.fallback_to_database is True
        assert config.fallback_to_legacy_sandbox is False
