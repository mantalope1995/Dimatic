"""
AgentCore Data Models

Provides data classes for AgentCore sessions and results with
serialization support for persistence and round-trip conversion.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import json


class SessionStatus(str, Enum):
    """Status of an AgentCore session"""
    CREATING = "creating"
    READY = "ready"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class RuntimeStatus(str, Enum):
    """Status of an AgentCore Runtime execution"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class CodeInterpreterSession:
    """
    Represents a Code Interpreter session with metadata

    Attributes:
        session_id: Unique identifier for the session
        project_id: Associated project ID
        status: Current session status
        created_at: Session creation timestamp
        timeout_seconds: Session timeout in seconds
        memory_limit_mb: Memory limit in MB
        region: AWS region for the session
    """
    session_id: str
    project_id: str
    status: SessionStatus = SessionStatus.READY
    created_at: datetime = field(default_factory=datetime.utcnow)
    timeout_seconds: int = 900
    memory_limit_mb: int = 1024
    region: str = "ap-southeast-2"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['status'] = self.status.value
        data['created_at'] = self.created_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CodeInterpreterSession':
        """Create from dictionary for JSON deserialization"""
        data = data.copy()
        if isinstance(data.get('status'), str):
            data['status'] = SessionStatus(data['status'])
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        return cls(**data)


@dataclass
class BrowserSession:
    """
    Represents a Browser session with metadata

    Attributes:
        session_id: Unique identifier for the session
        project_id: Associated project ID
        status: Current session status
        created_at: Session creation timestamp
        timeout_seconds: Session timeout in seconds
        viewport_width: Viewport width in pixels
        viewport_height: Viewport height in pixels
        headless: Whether browser runs in headless mode
        region: AWS region for the session
        recording_enabled: Whether session recording is enabled
        recording_s3_bucket: S3 bucket for session recordings
    """
    session_id: str
    project_id: str
    status: SessionStatus = SessionStatus.READY
    created_at: datetime = field(default_factory=datetime.utcnow)
    timeout_seconds: int = 900
    viewport_width: int = 1920
    viewport_height: int = 1080
    headless: bool = True
    region: str = "ap-southeast-2"
    recording_enabled: bool = False
    recording_s3_bucket: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['status'] = self.status.value
        data['created_at'] = self.created_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BrowserSession':
        """Create from dictionary for JSON deserialization"""
        data = data.copy()
        if isinstance(data.get('status'), str):
            data['status'] = SessionStatus(data['status'])
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        return cls(**data)


@dataclass
class CodeExecutionResult:
    """
    Result from code execution in Code Interpreter

    Attributes:
        output: Standard output from code execution
        error: Error output if execution failed
        exit_code: Process exit code (0 for success)
        execution_time_seconds: Time taken to execute in seconds
        files_created: List of file paths created during execution
    """
    output: str
    error: Optional[str]
    exit_code: int
    execution_time_seconds: float
    files_created: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CodeExecutionResult':
        """Create from dictionary for JSON deserialization"""
        return cls(**data)


@dataclass
class ShellCommandResult:
    """
    Result from shell command execution

    Attributes:
        stdout: Standard output from command
        stderr: Standard error output
        exit_code: Process exit code (0 for success)
        execution_time_seconds: Time taken to execute in seconds
    """
    stdout: str
    stderr: str
    exit_code: int
    execution_time_seconds: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ShellCommandResult':
        """Create from dictionary for JSON deserialization"""
        return cls(**data)


@dataclass
class NavigationResult:
    """
    Result from browser navigation

    Attributes:
        url: Final URL after navigation
        title: Page title
        screenshot_s3_url: S3 URL to screenshot (if captured)
        success: Whether navigation succeeded
        error: Error message if navigation failed
        load_time_seconds: Time to load the page
    """
    url: str
    title: str
    screenshot_s3_url: Optional[str]
    success: bool
    error: Optional[str]
    load_time_seconds: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NavigationResult':
        """Create from dictionary for JSON deserialization"""
        return cls(**data)


@dataclass
class ActionResult:
    """
    Result from browser action (click, fill form, etc.)

    Attributes:
        action_type: Type of action performed
        success: Whether action succeeded
        screenshot_s3_url: S3 URL to screenshot after action
        error: Error message if action failed
        execution_time_seconds: Time to execute the action
        metadata: Additional action-specific metadata
    """
    action_type: str
    success: bool
    screenshot_s3_url: Optional[str]
    error: Optional[str]
    execution_time_seconds: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ActionResult':
        """Create from dictionary for JSON deserialization"""
        return cls(**data)


@dataclass
class ExtractionResult:
    """
    Result from content extraction

    Attributes:
        extracted_data: Structured data extracted from page
        format: Format of extracted data (json, text, markdown)
        success: Whether extraction succeeded
        error: Error message if extraction failed
    """
    extracted_data: Any
    format: str
    success: bool
    error: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExtractionResult':
        """Create from dictionary for JSON deserialization"""
        return cls(**data)


@dataclass
class ScreenshotResult:
    """
    Result from screenshot capture

    Attributes:
        s3_url: S3 URL where screenshot was stored
        width: Screenshot width in pixels
        height: Screenshot height in pixels
        full_page: Whether screenshot captured full page
        success: Whether screenshot capture succeeded
        error: Error message if capture failed
    """
    s3_url: str
    width: int
    height: int
    full_page: bool
    success: bool
    error: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ScreenshotResult':
        """Create from dictionary for JSON deserialization"""
        return cls(**data)


# Helper functions for JSON serialization/deserialization

def serialize_session(session: Any) -> str:
    """
    Serialize a session object to JSON string

    Args:
        session: CodeInterpreterSession or BrowserSession

    Returns:
        JSON string representation
    """
    return json.dumps(session.to_dict())


def deserialize_session(json_str: str, session_type: str) -> Any:
    """
    Deserialize a JSON string to session object

    Args:
        json_str: JSON string representation
        session_type: 'code_interpreter' or 'browser'

    Returns:
        CodeInterpreterSession or BrowserSession instance
    """
    data = json.loads(json_str)
    if session_type == 'code_interpreter':
        return CodeInterpreterSession.from_dict(data)
    elif session_type == 'browser':
        return BrowserSession.from_dict(data)
    else:
        raise ValueError(f"Unknown session type: {session_type}")


def serialize_result(result: Any) -> str:
    """
    Serialize a result object to JSON string

    Args:
        result: Any result dataclass

    Returns:
        JSON string representation
    """
    return json.dumps(result.to_dict())


def deserialize_result(json_str: str, result_type: str) -> Any:
    """
    Deserialize a JSON string to result object

    Args:
        json_str: JSON string representation
        result_type: Type of result (e.g., 'code_execution', 'navigation')

    Returns:
        Result dataclass instance
    """
    data = json.loads(json_str)
    result_classes = {
        'code_execution': CodeExecutionResult,
        'shell_command': ShellCommandResult,
        'navigation': NavigationResult,
        'action': ActionResult,
        'extraction': ExtractionResult,
        'screenshot': ScreenshotResult,
        'runtime_execution': RuntimeExecutionResult,
        'memory_resource': MemoryResource,
        'stored_message': StoredMessage,
        'mcp_server_deployment': MCPServerDeployment,
        'mcp_tool_invocation': MCPToolInvocationResult,
        'gateway_config': GatewayConfig,
    }
    if result_type not in result_classes:
        raise ValueError(f"Unknown result type: {result_type}")
    return result_classes[result_type].from_dict(data)


# Runtime-specific models

@dataclass
class RuntimeSession:
    """
    Represents an AgentCore Runtime session

    Attributes:
        session_id: Unique identifier for the session
        agent_id: Agent identifier for this session
        status: Current session status
        created_at: Session creation timestamp
        timeout_seconds: Session timeout in seconds
        region: AWS region for the session
    """
    session_id: str
    agent_id: str
    status: SessionStatus = SessionStatus.READY
    created_at: datetime = field(default_factory=datetime.utcnow)
    timeout_seconds: int = 900
    region: str = "ap-southeast-2"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['status'] = self.status.value
        data['created_at'] = self.created_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RuntimeSession':
        """Create from dictionary for JSON deserialization"""
        data = data.copy()
        if isinstance(data.get('status'), str):
            data['status'] = SessionStatus(data['status'])
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        return cls(**data)


@dataclass
class RuntimeDeployment:
    """
    Represents an AgentCore Runtime deployment

    Attributes:
        deployment_id: Unique identifier for the deployment
        agent_id: Agent identifier
        version_id: Version identifier
        status: Deployment status
        created_at: Deployment creation timestamp
        deployed_at: When deployment was completed
        deployment_arn: ARN of the deployed agent
    """
    deployment_id: str
    agent_id: str
    version_id: str
    status: str
    created_at: datetime
    deployed_at: Optional[datetime] = None
    deployment_arn: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['created_at'] = self.created_at.isoformat()
        if data['deployed_at']:
            data['deployed_at'] = self.deployed_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RuntimeDeployment':
        """Create from dictionary for JSON deserialization"""
        data = data.copy()
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if isinstance(data.get('deployed_at'), str):
            data['deployed_at'] = datetime.fromisoformat(data['deployed_at'])
        return cls(**data)


@dataclass
class RuntimeExecutionResult:
    """
    Result from Runtime agent execution

    Attributes:
        execution_id: Unique identifier for the execution
        session_id: Session identifier
        agent_id: Agent identifier
        status: Execution status
        output: Output content from agent execution
        error: Error message if execution failed
        execution_time_seconds: Time taken to execute in seconds
        tokens_used: Number of tokens used (if available)
        trace_data: Execution trace data (if enabled)
    """
    execution_id: str
    session_id: str
    agent_id: str
    status: RuntimeStatus
    output: str
    error: Optional[str]
    execution_time_seconds: float
    tokens_used: Optional[int] = None
    trace_data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['status'] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RuntimeExecutionResult':
        """Create from dictionary for JSON deserialization"""
        data = data.copy()
        if isinstance(data.get('status'), str):
            data['status'] = RuntimeStatus(data['status'])
        return cls(**data)


@dataclass
class MemoryResource:
    """
    Represents an AgentCore Memory resource

    Attributes:
        memory_resource_id: Unique identifier for the Memory resource
        thread_id: Associated thread ID
        account_id: Account ID for tenant isolation
        status: Current resource status
        created_at: Resource creation timestamp
        retention_days: Message retention period in days
        semantic_search_enabled: Whether semantic search is enabled
        max_messages: Maximum number of messages to store
        region: AWS region for the resource
    """
    memory_resource_id: str
    thread_id: str
    account_id: str
    status: SessionStatus = SessionStatus.READY
    created_at: datetime = field(default_factory=datetime.utcnow)
    retention_days: int = 90
    semantic_search_enabled: bool = True
    max_messages: int = 10000
    region: str = "ap-southeast-2"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['status'] = self.status.value
        data['created_at'] = self.created_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MemoryResource':
        """Create from dictionary for JSON deserialization"""
        data = data.copy()
        if isinstance(data.get('status'), str):
            data['status'] = SessionStatus(data['status'])
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        return cls(**data)


@dataclass
class StoredMessage:
    """
    Represents a message stored in AgentCore Memory

    Attributes:
        message_id: Unique identifier for the stored message
        memory_resource_id: Memory resource identifier
        role: Message role (user, assistant, system, tool)
        content: Message content
        metadata: Additional message metadata
        created_at: Message creation timestamp
        embedding_id: Vector embedding ID for semantic search
    """
    message_id: str
    memory_resource_id: str
    role: str
    content: Any
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    embedding_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['created_at'] = self.created_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StoredMessage':
        """Create from dictionary for JSON deserialization"""
        data = data.copy()
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        return cls(**data)


# Gateway-specific models for MCP integration

@dataclass
class MCPServerDeployment:
    """
    Represents an MCP server deployment in AgentCore Gateway

    Attributes:
        deployment_id: Unique Gateway deployment identifier
        service_name: Name of the MCP service (github, slack, etc.)
        account_id: Account ID for tenant isolation
        status: Current deployment status
        created_at: Deployment creation timestamp
        deployed_at: When deployment was completed
        endpoint_url: Gateway endpoint URL for this deployment
        mcp_config: Original MCP server configuration
        region: AWS region for the deployment
    """
    deployment_id: str
    service_name: str
    account_id: str
    status: SessionStatus = SessionStatus.READY
    created_at: datetime = field(default_factory=datetime.utcnow)
    deployed_at: Optional[datetime] = None
    endpoint_url: Optional[str] = None
    mcp_config: Optional[Dict[str, Any]] = None
    region: str = "ap-southeast-2"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['status'] = self.status.value
        data['created_at'] = self.created_at.isoformat()
        if data['deployed_at']:
            data['deployed_at'] = self.deployed_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MCPServerDeployment':
        """Create from dictionary for JSON deserialization"""
        data = data.copy()
        if isinstance(data.get('status'), str):
            data['status'] = SessionStatus(data['status'])
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if isinstance(data.get('deployed_at'), str):
            data['deployed_at'] = datetime.fromisoformat(data['deployed_at'])
        return cls(**data)


@dataclass
class MCPToolInvocationResult:
    """
    Result from MCP tool invocation via Gateway

    Attributes:
        tool_name: Name of the invoked tool
        deployment_id: Gateway deployment identifier
        success: Whether invocation succeeded
        output: Tool output data (if successful)
        error: Error message (if failed)
        execution_time_seconds: Time taken to execute the tool
        metadata: Additional invocation metadata
        is_cached: Whether result was from cache
    """
    tool_name: str
    deployment_id: str
    success: bool
    output: Optional[Any]
    error: Optional[str]
    execution_time_seconds: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_cached: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MCPToolInvocationResult':
        """Create from dictionary for JSON deserialization"""
        return cls(**data)


@dataclass
class GatewayConfig:
    """
    Gateway configuration for MCP deployment

    Attributes:
        timeout_seconds: Timeout for tool invocations
        rate_limit_per_minute: Max invocations per minute
        max_concurrent_invocations: Max concurrent tool calls
        enable_caching: Whether to cache tool results
        cache_ttl_seconds: Cache TTL in seconds
        enable_metrics: Whether to collect metrics
    """
    timeout_seconds: int = 60
    rate_limit_per_minute: int = 100
    max_concurrent_invocations: int = 10
    enable_caching: bool = True
    cache_ttl_seconds: int = 300
    enable_metrics: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GatewayConfig':
        """Create from dictionary for JSON deserialization"""
        return cls(**data)
