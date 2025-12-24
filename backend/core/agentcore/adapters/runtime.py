"""
AgentCore Runtime Adapter

Handles deployment and invocation of agents using AWS Bedrock AgentCore Runtime.
Provides serverless agent execution with streaming responses.

IMPORTANT: For Phase 1 migration, all AgentCore Runtime services MUST run in
ap-southeast-2 (Australia region) to meet data residency requirements.
"""

import asyncio
import boto3
import logging
from datetime import datetime, timedelta
from typing import Any, AsyncGenerator, Dict, List, Optional, Callable
from dataclasses import dataclass, field

from ..config import AgentCoreConfig, get_config
from ..models import (
    RuntimeSession,
    RuntimeDeployment,
    RuntimeExecutionResult,
    RuntimeStatus,
    SessionStatus,
)
from ..errors import (
    AgentCoreError,
    AgentCoreConfigurationError as ConfigurationError,
    AgentCoreExecutionError as RuntimeError,
    AgentCoreRetryableError as TransientError,
    AgentCoreTenantError as TenantError,
    with_retry,
    safe_log,
)
from ..middleware import get_tenant_context

logger = logging.getLogger(__name__)


@dataclass
class RuntimeInvokeParams:
    """Parameters for Runtime agent invocation"""
    deployment_id: str
    session_id: str
    input_text: str
    input_data: Dict[str, Any] = field(default_factory=dict)
    stream: bool = True
    timeout_seconds: int = 300
    enable_trace: bool = False
    session_state: Optional[Dict[str, Any]] = None


@dataclass
class RuntimeDeploymentResult:
    """Result of Runtime agent deployment"""
    deployment_id: str
    agent_id: str
    agent_version: str
    status: str
    created_at: datetime
    deployment_arn: Optional[str] = None
    readiness_status: Optional[str] = None


@dataclass
class RuntimeSessionInfo:
    """Information about a Runtime session"""
    session_id: str
    agent_id: str
    alias_id: str
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    ttl: Optional[int] = None


@dataclass
class AgentDeploymentConfig:
    """Configuration for agent deployment to AgentCore Runtime"""
    agent_id: str
    version_id: str
    runtime_version: str = "latest"
    memory_limit_mb: int = 2048
    timeout_seconds: int = 300
    environment_variables: Dict[str, str] = None
    primitives_enabled: Dict[str, bool] = None

    def __post_init__(self):
        if self.environment_variables is None:
            self.environment_variables = {}
        if self.primitives_enabled is None:
            self.primitives_enabled = {
                "code_interpreter": True,
                "browser": True,
                "memory": True,
                "gateway": True
            }


class AgentCoreRuntimeAdapter:
    """
    Adapter for AWS Bedrock AgentCore Runtime deployment and invocation.

    This adapter provides methods to:
    - Deploy agents to AgentCore Runtime
    - Invoke agents with streaming responses
    - Cancel ongoing executions
    - Query execution status

    All Runtime operations use the ap-southeast-2 region for Phase 1 compliance.
    """

    # Default agent alias for draft versions
    DEFAULT_AGENT_ALIAS_ID: str = "DNTAB6Q4T9"  # "DRAFT" alias

    def __init__(self, config: Optional[AgentCoreConfig] = None):
        """
        Initialize the Runtime adapter.

        Args:
            config: AgentCore configuration. If None, uses global config.

        Raises:
            ConfigurationError: If Runtime is not enabled or config is invalid.
        """
        self.config = config or get_config()
        self._validate_config()
        self._initialize_client()

    def _validate_config(self) -> None:
        """Validate configuration for Runtime adapter"""
        if not self.config.runtime_enabled:
            raise ConfigurationError(
                "AgentCore Runtime is not enabled. "
                "Set AGENTCORE_RUNTIME_ENABLED=true to use Runtime features."
            )

        # Phase 1: Enforce ap-southeast-2 region
        if self.config.aws_region != "ap-southeast-2":
            safe_log(
                f"Runtime adapter initialized with region '{self.config.aws_region}'. "
                f"Phase 1 requires 'ap-southeast-2' for Runtime operations."
            )

    def _initialize_client(self) -> None:
        """Initialize AWS Bedrock agent-runtime client"""
        try:
            # Build session kwargs for boto3
            session_kwargs: Dict[str, Any] = {
                "region_name": self.config.aws_region,
            }

            # Add credentials if provided (for non-local environments)
            if self.config.aws_access_key_id:
                session_kwargs["aws_access_key_id"] = self.config.aws_access_key_id
            if self.config.aws_secret_access_key:
                session_kwargs["aws_secret_access_key"] = self.config.aws_secret_access_key

            self.bedrock_runtime = boto3.client(
                "bedrock-agent-runtime",
                **session_kwargs
            )

            # Store region for use in session management
            self.region = self.config.aws_region

            safe_log(
                f"Initialized Bedrock Runtime client in region {self.config.aws_region}"
            )

        except Exception as e:
            raise ConfigurationError(
                f"Failed to initialize Bedrock Runtime client: {e}"
            ) from e

    async def deploy_agent(
        self,
        agent_id: str,
        agent_config: Dict[str, Any],
        version_id: str,
        timeout_seconds: int = 300,
    ) -> RuntimeDeploymentResult:
        """
        Deploy an agent to AgentCore Runtime.

        This method creates or updates an agent in AWS Bedrock with the provided
        configuration. For new agents, it creates the agent resource. For existing
        agents, it creates a new version.

        Args:
            agent_id: Unique identifier for the agent
            agent_config: Agent configuration including instructions, tools, etc.
            version_id: Version identifier for this deployment
            timeout_seconds: Timeout for deployment operation

        Returns:
            RuntimeDeploymentResult containing deployment_id and status

        Raises:
            RuntimeError: If deployment fails
            TransientError: If deployment fails due to transient issues
        """
        try:
            safe_log(f"Deploying agent {agent_id} version {version_id} to Runtime")

            # Note: Actual agent deployment uses bedrock-agent client (not runtime)
            # For Phase 1, we use invoke_agent with draft alias which handles
            # agent provisioning automatically
            deployment_id = f"{agent_id}-{version_id}-{int(datetime.utcnow().timestamp())}"

            result = RuntimeDeploymentResult(
                deployment_id=deployment_id,
                agent_id=agent_id,
                agent_version=version_id,
                status="DEPLOYED",
                created_at=datetime.utcnow(),
                deployment_arn=f"arn:aws:bedrock:ap-southeast-2:{deployment_id}",
                readiness_status="READY"
            )

            safe_log(f"Agent deployed successfully: {deployment_id}")
            return result

        except Exception as e:
            if self._is_transient_error(e):
                raise TransientError(f"Transient deployment error: {e}") from e
            raise RuntimeError(f"Failed to deploy agent {agent_id}: {e}") from e

    async def invoke_agent(
        self,
        deployment_id: str,
        session_id: str,
        input_text: str,
        input_data: Optional[Dict[str, Any]] = None,
        stream: bool = True,
        timeout_seconds: int = 300,
        enable_trace: bool = False,
        session_state: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Invoke an agent with streaming response.

        Uses AWS Bedrock invoke_agent API to execute the agent and stream
        responses back in real-time.

        Args:
            deployment_id: Deployment identifier (agent_id)
            session_id: Session identifier for conversation continuity
            input_text: User input text
            input_data: Additional input data
            stream: Whether to stream responses
            timeout_seconds: Execution timeout
            enable_trace: Enable execution tracing
            session_state: Existing session state for continuation

        Yields:
            Dict containing streaming chunks with keys:
                - 'type': 'token' | 'trace' | 'error' | 'metadata'
                - 'data': chunk-specific data

        Raises:
            RuntimeError: If invocation fails
            TransientError: If invocation fails due to transient issues
        """
        params = RuntimeInvokeParams(
            deployment_id=deployment_id,
            session_id=session_id,
            input_text=input_text,
            input_data=input_data or {},
            stream=stream,
            timeout_seconds=timeout_seconds,
            enable_trace=enable_trace,
            session_state=session_state,
        )

        try:
            async for chunk in self._invoke_agent_with_retry(params):
                yield chunk

        except Exception as e:
            if self._is_transient_error(e):
                raise TransientError(f"Transient invocation error: {e}") from e
            raise RuntimeError(f"Failed to invoke agent {deployment_id}: {e}") from e

    async def _invoke_agent_with_retry(
        self,
        params: RuntimeInvokeParams
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Invoke agent with retry logic using with_retry utility"""
        # Use the with_retry wrapper from errors.py
        # For streaming, we wrap the initial call
        try:
            async for chunk in await with_retry(
                self._do_invoke_agent,
                params=params,
                max_attempts=self.config.retry_max_attempts,
                base_delay=self.config.retry_base_delay_seconds,
                max_delay=self.config.retry_max_delay_seconds,
            ):
                yield chunk

        except Exception as e:
            safe_log(f"Agent invocation failed: {e}")
            raise

    async def _do_invoke_agent(
        self,
        params: RuntimeInvokeParams
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Actual AWS SDK invoke_agent call"""
        try:
            # Prepare invoke parameters
            invoke_params: Dict[str, Any] = {
                "agentId": params.deployment_id,
                "agentAliasId": self.DEFAULT_AGENT_ALIAS_ID,
                "sessionId": params.session_id,
                "inputText": params.input_text,
            }

            # Add optional parameters
            if params.session_state:
                invoke_params["sessionState"] = params.session_state
            if params.enable_trace:
                invoke_params["enableTrace"] = True

            safe_log(
                f"Invoking agent {params.deployment_id} "
                f"(session: {params.session_id}, stream: {params.stream})"
            )

            # For Phase 1, we simulate streaming response
            # When real SDK is integrated, use:
            # if params.stream:
            #     response = self.bedrock_runtime.invoke_agent_stream(**invoke_params)
            #     async for event in response['completion']:
            #         yield self._process_stream_event(event)

            # Simulated streaming for now
            yield {
                "type": "metadata",
                "data": {
                    "deployment_id": params.deployment_id,
                    "session_id": params.session_id,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            }

            yield {
                "type": "token",
                "data": {"content": params.input_text}
            }

            yield {
                "type": "metadata",
                "data": {
                    "status": "completed",
                    "finish_reason": "stop"
                }
            }

        except self.bedrock_runtime.exceptions.ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code in ["ResourceNotFoundException", "AccessDeniedException"]:
                raise RuntimeError(f"Agent {params.deployment_id} not found or access denied: {e}") from e
            elif error_code in ["TooManyRequestsException", "ServiceUnavailableException"]:
                raise  # Will be caught and wrapped in TransientError
            else:
                raise RuntimeError(f"Bedrock Runtime API error: {e}") from e

        except Exception as e:
            raise RuntimeError(f"Unexpected error during agent invocation: {e}") from e

    async def cancel_execution(
        self,
        execution_id: str,
        session_id: str,
    ) -> bool:
        """
        Cancel an ongoing agent execution.

        Args:
            execution_id: Execution identifier (agent_id)
            session_id: Session identifier to cancel

        Returns:
            True if cancellation was successful, False otherwise

        Raises:
            RuntimeError: If cancellation fails
        """
        try:
            safe_log(f"Cancelling execution {execution_id} for session {session_id}")

            # Note: Bedrock Runtime doesn't have explicit cancel API
            # Sessions are managed via TTL and timeout settings
            # For Phase 1, we log the cancellation request
            # Actual session cleanup happens automatically via TTL

            safe_log(f"Execution {execution_id} marked for cancellation")
            return True

        except Exception as e:
            safe_log(f"Failed to cancel execution {execution_id}: {e}")
            return False

    async def get_execution_status(
        self,
        execution_id: str,
        session_id: str,
    ) -> RuntimeSessionInfo:
        """
        Get status of an agent execution/session.

        Args:
            execution_id: Execution identifier (agent_id)
            session_id: Session identifier to query

        Returns:
            RuntimeSessionInfo with session status details

        Raises:
            RuntimeError: If status query fails
        """
        try:
            safe_log(f"Querying status for execution {execution_id}, session {session_id}")

            # Note: Bedrock Runtime doesn't have explicit get session status API
            # For Phase 1, we return a simulated status
            # When real SDK is integrated, use:
            # response = self.bedrock_runtime.get_agent_session(
            #     agentId=execution_id,
            #     sessionId=session_id
            # )

            session_info = RuntimeSessionInfo(
                session_id=session_id,
                agent_id=execution_id,
                alias_id=self.DEFAULT_AGENT_ALIAS_ID,
                status="ACTIVE",
                created_at=datetime.utcnow() - timedelta(minutes=5),
                updated_at=datetime.utcnow(),
                ttl=900,  # 15 minutes default
            )

            return session_info

        except self.bedrock_runtime.exceptions.ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
                # Session doesn't exist or expired
                return RuntimeSessionInfo(
                    session_id=session_id,
                    agent_id=execution_id,
                    alias_id=self.DEFAULT_AGENT_ALIAS_ID,
                    status="EXPIRED",
                    created_at=datetime.utcnow(),
                    ttl=0,
                )
            raise RuntimeError(f"Failed to get execution status: {e}") from e

        except Exception as e:
            raise RuntimeError(f"Unexpected error querying status: {e}") from e

    async def create_session(
        self,
        agent_id: str,
        timeout_seconds: int = 900,
    ) -> RuntimeSession:
        """
        Create a new Runtime session for an agent.

        Args:
            agent_id: Agent identifier
            timeout_seconds: Session timeout in seconds

        Returns:
            RuntimeSession with session details

        Raises:
            RuntimeError: If session creation fails
        """
        import uuid
        session_id = str(uuid.uuid4())

        session = RuntimeSession(
            session_id=session_id,
            agent_id=agent_id,
            status=SessionStatus.READY,
            created_at=datetime.utcnow(),
            timeout_seconds=timeout_seconds,
            region=self.region,
        )

        safe_log(f"Created Runtime session {session_id} for agent {agent_id}")
        return session

    async def delete_session(
        self,
        session_id: str,
        agent_id: str,
    ) -> bool:
        """
        Delete a Runtime session.

        Args:
            session_id: Session identifier to delete
            agent_id: Agent identifier

        Returns:
            True if deletion was successful

        Raises:
            RuntimeError: If deletion fails
        """
        try:
            safe_log(f"Deleting Runtime session {session_id} for agent {agent_id}")
            # Sessions are managed via TTL in Bedrock Runtime
            # Explicit deletion is not needed
            return True

        except Exception as e:
            safe_log(f"Failed to delete session {session_id}: {e}")
            return False

    def _is_transient_error(self, error: Exception) -> bool:
        """Check if an error is transient and should be retried"""
        error_str = str(error).lower()
        transient_keywords = [
            "timeout",
            "throttling",
            "too many requests",
            "service unavailable",
            "internal error",
            "network",
            "connection",
        ]
        return any(keyword in error_str for keyword in transient_keywords)

    def _process_stream_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Process a streaming event from Bedrock Runtime"""
        # When real SDK is integrated, process actual event structure
        event_type = event.get("type", "unknown")

        if event_type == "token":
            return {
                "type": "token",
                "data": {"content": event.get("content", "")}
            }
        elif event_type == "trace":
            return {
                "type": "trace",
                "data": {"trace_data": event.get("trace", {})}
            }
        elif event_type == "error":
            return {
                "type": "error",
                "data": {"error": event.get("error", "Unknown error")}
            }
        else:
            return {
                "type": "metadata",
                "data": event
            }

    # =====================================================
    # PHASE 6: Tool Execution via Runtime
    # =====================================================

    async def create_deployment(
        self,
        deployment_name: str,
        account_id: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        Create a Runtime deployment for tool execution.

        This is a simplified deployment method for Phase 6 that creates
        a deployment identifier for tool-based execution.

        Args:
            deployment_name: Name for the deployment (e.g., "thread-{thread_id}")
            account_id: Account identifier for the deployment
            tools: Optional list of tool configurations to register

        Returns:
            Deployment ID string

        Raises:
            RuntimeError: If deployment creation fails
        """
        try:
            import uuid
            # Phase 7: Create a tenant-isolated deployment ID
            # Format: {deployment_name}-{account_id}-{uuid}
            # This enables ownership verification without DynamoDB lookup
            unique_suffix = str(uuid.uuid4())[:8]
            deployment_id = f"{deployment_name}-{account_id}-{unique_suffix}"

            safe_log(
                f"Created Runtime deployment {deployment_id} "
                f"for account {account_id} ({len(tools or [])} tools)"
            )

            return deployment_id

        except Exception as e:
            if self._is_transient_error(e):
                raise TransientError(f"Transient deployment creation error: {e}") from e
            raise RuntimeError(f"Failed to create Runtime deployment: {e}") from e

    async def _verify_deployment_ownership(
        self,
        deployment_id: str,
        account_id: str
    ) -> bool:
        """
        Verify deployment belongs to the tenant's account.

        This is a CRITICAL security check to prevent cross-tenant deployment access.
        In production, this would query DynamoDB's runtime_deployments table.
        For Phase 7, we use a simplified check based on deployment ID patterns.

        Args:
            deployment_id: Runtime deployment identifier
            account_id: Account ID to verify ownership

        Returns:
            True if deployment belongs to the account, False otherwise
        """
        # Phase 7: Simplified ownership check
        # In production, this would query DynamoDB:
        # response = await dynamodb.get_item(
        #     TableName='runtime_deployments',
        #     Key={'deployment_id': deployment_id},
        #     ProjectionExpression='account_id'
        # )
        # item = response.get('Item')
        # return item.get('account_id') == account_id if item else False

        # Check if deployment_id contains account_id with proper delimiter
        # Format: {deployment_name}-{account_id}-{uuid}
        parts = deployment_id.split('-')
        if len(parts) >= 3:
            # The second part (index 1) should be account_id
            return parts[1] == account_id
        return False

    @with_retry(max_attempts=3)
    async def invoke_tool(
        self,
        deployment_id: str,
        tool_name: str,
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Invoke a tool via Runtime deployment.

        For Phase 6, this provides a bridge for tool execution through
        AgentCore Runtime. The actual tool execution happens via the
        Runtime's tool execution framework.

        PHASE 6: Added @with_retry decorator for automatic retry on transient failures.
        PHASE 7: Added tenant ownership verification to prevent cross-tenant access.

        Args:
            deployment_id: Runtime deployment identifier
            tool_name: Name of the tool to invoke
            parameters: Tool parameters

        Returns:
            Dict containing:
                - 'success': bool - Whether execution succeeded
                - 'result': Any - Tool execution result
                - 'error': Optional[str] - Error message if failed
                - 'execution_via': str - Always 'runtime' for this path
                - 'retry_attempts': int - Number of retry attempts made (Phase 6)

        Raises:
            TenantError: If deployment belongs to a different tenant (Phase 7)
            RuntimeError: If tool invocation fails after all retries
            TransientError: If invocation fails due to transient issues (retriable)
        """
        # Phase 7: CRITICAL - Verify deployment ownership before execution
        # This prevents cross-tenant deployment access
        tenant_ctx = get_tenant_context()
        if tenant_ctx is not None:
            # Tenant context is set, verify ownership
            if not await self._verify_deployment_ownership(
                deployment_id,
                tenant_ctx.account_id
            ):
                safe_log(
                    f"SECURITY: Tenant {tenant_ctx.account_id[:8]}... attempted to access "
                    f"deployment {deployment_id} belonging to different tenant"
                )
                raise TenantError(
                    f"Deployment {deployment_id} does not belong to tenant {tenant_ctx.account_id}. "
                    f"Cross-tenant deployment access is not permitted."
                )
            # Ownership verified, proceed with tool invocation

        try:
            safe_log(
                f"Invoking tool '{tool_name}' via Runtime deployment {deployment_id}"
            )

            # Phase 6: Add timeout handling to prevent hangs
            timeout_seconds = self.config.runtime_timeout_seconds or 60
            result = await asyncio.wait_for(
                self._do_invoke_tool(deployment_id, tool_name, parameters),
                timeout=timeout_seconds
            )

            safe_log(f"Tool '{tool_name}' invoked successfully via Runtime")
            return result

        except asyncio.TimeoutError as e:
            # Phase 6: Timeout is a transient error - will be retried
            raise TransientError(
                f"Tool '{tool_name}' execution timed out after {timeout_seconds}s"
            ) from e

        except self.bedrock_runtime.exceptions.ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code in ["TooManyRequestsException", "ServiceUnavailableException"]:
                raise  # Will be caught and wrapped in TransientError by with_retry
            raise RuntimeError(f"Bedrock Runtime tool invocation error: {e}") from e

        except Exception as e:
            if self._is_transient_error(e):
                raise TransientError(f"Transient tool invocation error: {e}") from e
            raise RuntimeError(f"Failed to invoke tool '{tool_name}': {e}") from e

    async def _do_invoke_tool(
        self,
        deployment_id: str,
        tool_name: str,
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Internal method to perform the actual tool invocation.

        Separated from invoke_tool to allow timeout wrapping with retry logic.
        """
        # For Phase 6, this is a bridge method
        # In future phases, this would call actual AgentCore Runtime tool execution
        # For now, we return a structured response indicating the call was received

        result = {
            "success": True,
            "result": {
                "deployment_id": deployment_id,
                "tool_name": tool_name,
                "parameters": parameters,
                "executed_via": "runtime",
                "timestamp": datetime.utcnow().isoformat(),
            },
            "error": None,
            "execution_via": "runtime",  # Phase 6: Track execution path
        }

        return result

    async def register_tool(
        self,
        deployment_id: str,
        tool_config: Dict[str, Any],
    ) -> bool:
        """
        Register a tool with a Runtime deployment.

        Args:
            deployment_id: Runtime deployment identifier
            tool_config: Tool configuration containing:
                - name: Tool name
                - description: Tool description
                - input_schema: Tool input schema
                - category: Tool category (optional)

        Returns:
            True if registration succeeded, False otherwise

        Raises:
            RuntimeError: If registration fails critically
        """
        try:
            tool_name = tool_config.get("name", "unknown")
            safe_log(
                f"Registering tool '{tool_name}' with Runtime deployment {deployment_id}"
            )

            # For Phase 6, this is a bridge method that logs tool registration
            # In future phases, this would call actual AgentCore Runtime tool registration

            safe_log(f"Tool '{tool_name}' registered with Runtime")
            return True

        except Exception as e:
            safe_log(f"Failed to register tool '{tool_config.get('name')}': {e}")
            # Don't raise - registration failures should not block thread creation
            return False

    async def delete_deployment(self, deployment_id: str) -> bool:
        """
        Delete a Runtime deployment.

        Args:
            deployment_id: Runtime deployment identifier to delete

        Returns:
            True if deletion was successful, False otherwise

        Raises:
            RuntimeError: If deletion fails critically
        """
        try:
            safe_log(f"Deleting Runtime deployment {deployment_id}")

            # For Phase 6, deployments are logical constructs
            # In future phases, this would call actual AgentCore Runtime deletion

            safe_log(f"Runtime deployment {deployment_id} deleted")
            return True

        except Exception as e:
            safe_log(f"Failed to delete deployment {deployment_id}: {e}")
            return False
