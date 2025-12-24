"""
AgentCore Configuration Management

Handles environment-based configuration for AgentCore services.
Supports development and production environments with proper validation.

IMPORTANT: For Phase 1 migration, all AgentCore services MUST run in ap-southeast-2
(Australia region) to meet data residency requirements.
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class Environment(str, Enum):
    """Supported deployment environments"""
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    LOCAL = "local"


@dataclass
class AgentCoreConfig:
    """
    Configuration for AWS Bedrock AgentCore services

    Attributes:
        environment: Deployment environment (development/production/local)
        aws_region: AWS region for AgentCore services (ENFORCED to ap-southeast-2 for Phase 1)
        aws_access_key_id: AWS access key ID
        aws_secret_access_key: AWS secret access key
        runtime_enabled: Enable AgentCore Runtime
        memory_enabled: Enable AgentCore Memory
        code_interpreter_enabled: Enable AgentCore Code Interpreter
        browser_enabled: Enable AgentCore Browser
        gateway_enabled: Enable AgentCore Gateway
        runtime_timeout_seconds: Default timeout for agent execution
        memory_retention_days: Default retention period for memory resources
        code_interpreter_timeout_seconds: Default timeout for code execution
        browser_timeout_seconds: Default timeout for browser operations
        gateway_timeout_seconds: Default timeout for Gateway API calls
        code_interpreter_session_timeout_seconds: Code Interpreter session timeout (default 900)
        browser_session_timeout_seconds: Browser session timeout (default 900)
        browser_recording_enabled: Enable browser session recording to S3
        browser_recording_s3_bucket: S3 bucket for browser recordings
        retry_max_attempts: Maximum retry attempts for transient failures
        retry_base_delay_seconds: Base delay for exponential backoff
        retry_max_delay_seconds: Maximum delay between retries
    """

    # Environment configuration
    environment: Environment = Environment.LOCAL
    aws_region: str = "ap-southeast-2"  # Phase 1 requires Australia region
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None

    # Feature flags
    runtime_enabled: bool = True
    memory_enabled: bool = True
    code_interpreter_enabled: bool = True
    browser_enabled: bool = True
    gateway_enabled: bool = True

    # Runtime configuration
    runtime_timeout_seconds: int = 300
    runtime_memory_limit_mb: int = 2048

    # Memory configuration
    memory_retention_days: int = 90
    memory_max_messages: int = 10000
    memory_semantic_search_enabled: bool = True

    # Code Interpreter configuration
    code_interpreter_timeout_seconds: int = 30
    code_interpreter_memory_limit_mb: int = 1024
    code_interpreter_session_timeout_seconds: int = 900  # 15 minutes default

    # Browser configuration
    browser_timeout_seconds: int = 60
    browser_headless: bool = True
    browser_session_timeout_seconds: int = 900  # 15 minutes default
    browser_recording_enabled: bool = False
    browser_recording_s3_bucket: Optional[str] = None

    # Gateway configuration
    gateway_timeout_seconds: int = 30
    gateway_rate_limit_per_minute: int = 60

    # Retry configuration
    retry_max_attempts: int = 3
    retry_base_delay_seconds: float = 1.0
    retry_max_delay_seconds: float = 10.0

    # S3 configuration for file storage
    s3_bucket_name: Optional[str] = None
    s3_bucket_region: Optional[str] = None

    # DynamoDB configuration for MCP catalog
    dynamodb_mcp_catalog_table: str = "mcp_catalog"
    dynamodb_oauth_states_table: str = "oauth_states"

    # Secrets Manager configuration
    secrets_manager_prefix: str = "kortix"

    # Fallback configuration
    fallback_to_database: bool = True
    fallback_to_legacy_sandbox: bool = False

    # Phase 1: Enforce ap-southeast-2 region
    _phase1_required_region: str = "ap-southeast-2"
    
    def __post_init__(self):
        """Validate configuration after initialization"""
        self._validate_config()
    
    def _validate_config(self):
        """Validate configuration values"""
        # Phase 1: Enforce ap-southeast-2 region for all non-local environments
        if self.environment != Environment.LOCAL:
            # Warn and override if non-Australia region is specified
            if self.aws_region != self._phase1_required_region:
                logger.warning(
                    f"AgentCore region '{self.aws_region}' specified, "
                    f"but Phase 1 requires '{self._phase1_required_region}'. "
                    f"Overriding to {self._phase1_required_region} for compliance."
                )
                self.aws_region = self._phase1_required_region

            # Validate AWS credentials for non-local environments
            if not self.aws_access_key_id or not self.aws_secret_access_key:
                raise ValueError(
                    f"AWS credentials required for {self.environment} environment. "
                    "Set AGENTCORE_AWS_ACCESS_KEY_ID and AGENTCORE_AWS_SECRET_ACCESS_KEY"
                )

        # Validate S3 bucket for file storage
        if self.code_interpreter_enabled or self.browser_enabled:
            if not self.s3_bucket_name:
                raise ValueError(
                    "S3 bucket name required when Code Interpreter or Browser is enabled. "
                    "Set AGENTCORE_S3_BUCKET_NAME"
                )
            # Validate S3 bucket is in ap-southeast-2 for Phase 1
            if self.s3_bucket_region and self.s3_bucket_region != self._phase1_required_region:
                logger.warning(
                    f"S3 bucket region '{self.s3_bucket_region}' specified, "
                    f"but Phase 1 requires '{self._phase1_required_region}'. "
                    f"Overriding S3 bucket region to {self._phase1_required_region}."
                )
                self.s3_bucket_region = self._phase1_required_region

        # Validate timeouts
        if self.runtime_timeout_seconds <= 0:
            raise ValueError("Runtime timeout must be positive")
        if self.code_interpreter_timeout_seconds <= 0:
            raise ValueError("Code Interpreter timeout must be positive")
        if self.browser_timeout_seconds <= 0:
            raise ValueError("Browser timeout must be positive")
        if self.gateway_timeout_seconds <= 0:
            raise ValueError("Gateway timeout must be positive")

        # Validate session timeouts (Requirement 21.4: between 60 and 28800 seconds)
        if not (60 <= self.code_interpreter_session_timeout_seconds <= 28800):
            raise ValueError(
                f"Code Interpreter session timeout must be between 60 and 28800 seconds, "
                f"got {self.code_interpreter_session_timeout_seconds}"
            )
        if not (60 <= self.browser_session_timeout_seconds <= 28800):
            raise ValueError(
                f"Browser session timeout must be between 60 and 28800 seconds, "
                f"got {self.browser_session_timeout_seconds}"
            )

        # Validate browser recording configuration
        if self.browser_recording_enabled:
            if not self.browser_recording_s3_bucket:
                raise ValueError(
                    "browser_recording_s3_bucket required when browser_recording_enabled is True. "
                    "Set AGENTCORE_BROWSER_RECORDING_S3_BUCKET"
                )

        # Validate retry configuration
        if self.retry_max_attempts < 0:
            raise ValueError(f"retry_max_attempts must be non-negative, got {self.retry_max_attempts}")
        if self.retry_base_delay_seconds <= 0:
            raise ValueError(f"retry_base_delay_seconds must be positive, got {self.retry_base_delay_seconds}")
        if self.retry_max_delay_seconds < self.retry_base_delay_seconds:
            raise ValueError(
                f"retry_max_delay_seconds ({self.retry_max_delay_seconds}) must be >= "
                f"retry_base_delay_seconds ({self.retry_base_delay_seconds})"
            )
    
    def get_resource_prefix(self) -> str:
        """Get resource prefix for AgentCore resources based on environment"""
        return f"agentcore-{self.environment.value}"
    
    def is_production(self) -> bool:
        """Check if running in production environment"""
        return self.environment == Environment.PRODUCTION
    
    def is_development(self) -> bool:
        """Check if running in development environment"""
        return self.environment == Environment.DEVELOPMENT
    
    def is_local(self) -> bool:
        """Check if running in local environment"""
        return self.environment == Environment.LOCAL


def get_agentcore_config() -> AgentCoreConfig:
    """
    Load AgentCore configuration from environment variables

    Environment Variables:
        AGENTCORE_ENVIRONMENT: Environment mode (development/production/local)
        AGENTCORE_AWS_REGION: AWS region (OVERRIDDEN to ap-southeast-2 for Phase 1)
        AGENTCORE_AWS_ACCESS_KEY_ID: AWS access key ID
        AGENTCORE_AWS_SECRET_ACCESS_KEY: AWS secret access key
        AGENTCORE_RUNTIME_ENABLED: Enable Runtime (default: true)
        AGENTCORE_MEMORY_ENABLED: Enable Memory (default: true)
        AGENTCORE_CODE_INTERPRETER_ENABLED: Enable Code Interpreter (default: true)
        AGENTCORE_BROWSER_ENABLED: Enable Browser (default: true)
        AGENTCORE_GATEWAY_ENABLED: Enable Gateway (default: true)
        AGENTCORE_S3_BUCKET_NAME: S3 bucket for file storage
        AGENTCORE_S3_BUCKET_REGION: S3 bucket region (OVERRIDDEN to ap-southeast-2 for Phase 1)
        AGENTCORE_CODE_INTERPRETER_SESSION_TIMEOUT_SECONDS: Session timeout (default: 900)
        AGENTCORE_BROWSER_SESSION_TIMEOUT_SECONDS: Browser session timeout (default: 900)
        AGENTCORE_BROWSER_RECORDING_ENABLED: Enable browser recording (default: false)
        AGENTCORE_BROWSER_RECORDING_S3_BUCKET: S3 bucket for recordings
        AGENTCORE_RETRY_MAX_ATTEMPTS: Max retry attempts (default: 3)
        AGENTCORE_RETRY_BASE_DELAY_SECONDS: Base retry delay (default: 1.0)
        AGENTCORE_RETRY_MAX_DELAY_SECONDS: Max retry delay (default: 10.0)
        AGENTCORE_FALLBACK_TO_DATABASE: Enable database fallback (default: true)
        AGENTCORE_FALLBACK_TO_LEGACY_SANDBOX: Enable legacy sandbox fallback (default: false)

    Returns:
        AgentCoreConfig: Configured AgentCore settings

    Raises:
        ValueError: If configuration is invalid
    """
    
    # Parse environment
    env_str = os.getenv("AGENTCORE_ENVIRONMENT", "local").lower()
    try:
        environment = Environment(env_str)
    except ValueError:
        raise ValueError(
            f"Invalid AGENTCORE_ENVIRONMENT: {env_str}. "
            f"Must be one of: {', '.join([e.value for e in Environment])}"
        )
    
    # Parse boolean flags
    def parse_bool(value: Optional[str], default: bool = True) -> bool:
        if value is None:
            return default
        return value.lower() in ("true", "1", "yes", "on")
    
    # Parse integer values
    def parse_int(value: Optional[str], default: int) -> int:
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            return default
    
    config = AgentCoreConfig(
        # Environment
        environment=environment,
        aws_region=os.getenv("AGENTCORE_AWS_REGION", "ap-southeast-2"),  # Phase 1 requires Australia region
        aws_access_key_id=os.getenv("AGENTCORE_AWS_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AGENTCORE_AWS_SECRET_ACCESS_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY"),

        # Feature flags
        runtime_enabled=parse_bool(os.getenv("AGENTCORE_RUNTIME_ENABLED"), True),
        memory_enabled=parse_bool(os.getenv("AGENTCORE_MEMORY_ENABLED"), True),
        code_interpreter_enabled=parse_bool(os.getenv("AGENTCORE_CODE_INTERPRETER_ENABLED"), True),
        browser_enabled=parse_bool(os.getenv("AGENTCORE_BROWSER_ENABLED"), True),
        gateway_enabled=parse_bool(os.getenv("AGENTCORE_GATEWAY_ENABLED"), True),

        # Runtime configuration
        runtime_timeout_seconds=parse_int(os.getenv("AGENTCORE_RUNTIME_TIMEOUT_SECONDS"), 300),
        runtime_memory_limit_mb=parse_int(os.getenv("AGENTCORE_RUNTIME_MEMORY_LIMIT_MB"), 2048),

        # Memory configuration
        memory_retention_days=parse_int(os.getenv("AGENTCORE_MEMORY_RETENTION_DAYS"), 90),
        memory_max_messages=parse_int(os.getenv("AGENTCORE_MEMORY_MAX_MESSAGES"), 10000),
        memory_semantic_search_enabled=parse_bool(os.getenv("AGENTCORE_MEMORY_SEMANTIC_SEARCH_ENABLED"), True),

        # Code Interpreter configuration
        code_interpreter_timeout_seconds=parse_int(os.getenv("AGENTCORE_CODE_INTERPRETER_TIMEOUT_SECONDS"), 30),
        code_interpreter_memory_limit_mb=parse_int(os.getenv("AGENTCORE_CODE_INTERPRETER_MEMORY_LIMIT_MB"), 1024),
        code_interpreter_session_timeout_seconds=parse_int(os.getenv("AGENTCORE_CODE_INTERPRETER_SESSION_TIMEOUT_SECONDS"), 900),

        # Browser configuration
        browser_timeout_seconds=parse_int(os.getenv("AGENTCORE_BROWSER_TIMEOUT_SECONDS"), 60),
        browser_headless=parse_bool(os.getenv("AGENTCORE_BROWSER_HEADLESS"), True),
        browser_session_timeout_seconds=parse_int(os.getenv("AGENTCORE_BROWSER_SESSION_TIMEOUT_SECONDS"), 900),
        browser_recording_enabled=parse_bool(os.getenv("AGENTCORE_BROWSER_RECORDING_ENABLED"), False),
        browser_recording_s3_bucket=os.getenv("AGENTCORE_BROWSER_RECORDING_S3_BUCKET"),

        # Gateway configuration
        gateway_timeout_seconds=parse_int(os.getenv("AGENTCORE_GATEWAY_TIMEOUT_SECONDS"), 30),
        gateway_rate_limit_per_minute=parse_int(os.getenv("AGENTCORE_GATEWAY_RATE_LIMIT_PER_MINUTE"), 60),

        # Retry configuration
        retry_max_attempts=parse_int(os.getenv("AGENTCORE_RETRY_MAX_ATTEMPTS"), 3),
        retry_base_delay_seconds=float(os.getenv("AGENTCORE_RETRY_BASE_DELAY_SECONDS", "1.0")),
        retry_max_delay_seconds=float(os.getenv("AGENTCORE_RETRY_MAX_DELAY_SECONDS", "10.0")),

        # S3 configuration
        s3_bucket_name=os.getenv("AGENTCORE_S3_BUCKET_NAME"),
        s3_bucket_region=os.getenv("AGENTCORE_S3_BUCKET_REGION") or os.getenv("AGENTCORE_AWS_REGION", "ap-southeast-2"),  # Phase 1 requires Australia region

        # DynamoDB configuration
        dynamodb_mcp_catalog_table=os.getenv("AGENTCORE_DYNAMODB_MCP_CATALOG_TABLE", "mcp_catalog"),
        dynamodb_oauth_states_table=os.getenv("AGENTCORE_DYNAMODB_OAUTH_STATES_TABLE", "oauth_states"),

        # Secrets Manager configuration
        secrets_manager_prefix=os.getenv("AGENTCORE_SECRETS_MANAGER_PREFIX", "kortix"),

        # Fallback configuration
        fallback_to_database=parse_bool(os.getenv("AGENTCORE_FALLBACK_TO_DATABASE"), True),
        fallback_to_legacy_sandbox=parse_bool(os.getenv("AGENTCORE_FALLBACK_TO_LEGACY_SANDBOX"), False),
    )
    
    return config


# Global configuration instance (lazy loaded)
_config: Optional[AgentCoreConfig] = None


def get_config() -> AgentCoreConfig:
    """
    Get the global AgentCore configuration instance
    
    Returns:
        AgentCoreConfig: Global configuration instance
    """
    global _config
    if _config is None:
        _config = get_agentcore_config()
    return _config


def reset_config():
    """Reset the global configuration instance (useful for testing)"""
    global _config
    _config = None
