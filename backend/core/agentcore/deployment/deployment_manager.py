"""
AgentCore Deployment Manager

Orchestrates agent deployment to AWS Bedrock AgentCore Runtime.
Handles packaging, deployment, status tracking, and rollback.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from ..config import AgentCoreConfig, get_config
from ..models import RuntimeDeployment
from ..errors import (
    AgentCoreError,
    AgentCoreConfigurationError as ConfigurationError,
    AgentCoreExecutionError as DeploymentError,
    AgentCoreRetryableError as TransientError,
    with_retry,
    safe_log,
)
from ..adapters.runtime import AgentCoreRuntimeAdapter, RuntimeDeploymentResult
from .agent_packager import AgentPackager, AgentCorePackage, package_agent_for_deployment

logger = logging.getLogger(__name__)


@dataclass
class DeploymentStatus:
    """Status of an agent deployment"""
    deployment_id: str
    agent_id: str
    version_id: str
    status: str  # pending, deploying, deployed, failed, rolling_back
    created_at: datetime
    updated_at: datetime = field(default_factory=datetime.utcnow)
    deployment_arn: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "deployment_id": self.deployment_id,
            "agent_id": self.agent_id,
            "version_id": self.version_id,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "deployment_arn": self.deployment_arn,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DeploymentStatus':
        """Create from dictionary for JSON deserialization"""
        data = data.copy()
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if isinstance(data.get('updated_at'), str):
            data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class DeploymentResult:
    """Result of a deployment operation"""
    success: bool
    deployment_id: str
    agent_id: str
    version_id: str
    status: str
    deployment_arn: Optional[str] = None
    error_message: Optional[str] = None
    rollback_performed: bool = False
    previous_deployment_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "success": self.success,
            "deployment_id": self.deployment_id,
            "agent_id": self.agent_id,
            "version_id": self.version_id,
            "status": self.status,
            "deployment_arn": self.deployment_arn,
            "error_message": self.error_message,
            "rollback_performed": self.rollback_performed,
            "previous_deployment_id": self.previous_deployment_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DeploymentResult':
        """Create from dictionary for JSON deserialization"""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class DeploymentManager:
    """
    Manages agent deployment lifecycle to AgentCore Runtime.

    This manager orchestrates the full deployment workflow:
    1. Package agent configuration for AgentCore
    2. Deploy to Runtime using adapter
    3. Track deployment status
    4. Handle rollback on failure
    5. Retry transient failures

    All deployments use ap-southeast-2 region for Phase 1 compliance.
    """

    # Deployment status constants
    STATUS_PENDING = "pending"
    STATUS_DEPLOYING = "deploying"
    STATUS_DEPLOYED = "deployed"
    STATUS_FAILED = "failed"
    STATUS_ROLLING_BACK = "rolling_back"
    STATUS_ROLLED_BACK = "rolled_back"

    def __init__(
        self,
        config: Optional[AgentCoreConfig] = None,
        packager: Optional[AgentPackager] = None,
        runtime_adapter: Optional[AgentCoreRuntimeAdapter] = None,
    ):
        """
        Initialize the deployment manager.

        Args:
            config: AgentCore configuration. If None, uses global config.
            packager: Agent packager instance. If None, creates new instance.
            runtime_adapter: Runtime adapter instance. If None, creates new instance.

        Raises:
            ConfigurationError: If Runtime is not enabled or config is invalid.
        """
        self.config = config or get_config()
        self._validate_config()

        self.packager = packager or AgentPackager(config=self.config)
        self.runtime_adapter = runtime_adapter or AgentCoreRuntimeAdapter(config=self.config)

        # In-memory deployment tracking (in production, use database)
        self._deployments: Dict[str, DeploymentStatus] = {}

        safe_log("DeploymentManager initialized")

    def _validate_config(self) -> None:
        """Validate configuration for deployment manager"""
        if not self.config.runtime_enabled:
            raise ConfigurationError(
                "AgentCore Runtime is not enabled. "
                "Set AGENTCORE_RUNTIME_ENABLED=true to use deployment features."
            )

        # Phase 1: Enforce ap-southeast-2 region
        if self.config.aws_region != "ap-southeast-2":
            safe_log(
                f"Deployment manager initialized with region '{self.config.aws_region}'. "
                f"Phase 1 requires 'ap-southeast-2' for Runtime deployments."
            )

    async def deploy_agent_version(
        self,
        agent_id: str,
        version_id: str,
        system_prompt: str,
        model: Optional[str] = None,
        configured_mcps: Optional[List[Dict[str, Any]]] = None,
        custom_mcps: Optional[List[Dict[str, Any]]] = None,
        agentpress_tools: Optional[Dict[str, Any]] = None,
        triggers: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        timeout_seconds: int = 300,
        enable_retry: bool = True,
        enable_rollback: bool = True,
    ) -> DeploymentResult:
        """
        Deploy an agent version to AgentCore Runtime with full workflow.

        This method:
        1. Packages the agent configuration
        2. Validates the package
        3. Deploys to Runtime
        4. Tracks deployment status
        5. Handles rollback on failure if enabled

        Args:
            agent_id: Unique identifier for the agent
            version_id: Version identifier for this deployment
            system_prompt: Agent's system prompt/instructions
            model: Model identifier (e.g., "anthropic/claude-3-5-sonnet")
            configured_mcps: List of configured MCP integrations
            custom_mcps: List of custom MCP integrations
            agentpress_tools: AgentPress tool configuration
            triggers: Agent triggers configuration
            metadata: Additional deployment metadata
            timeout_seconds: Deployment timeout in seconds
            enable_retry: Enable retry on transient failures
            enable_rollback: Enable rollback to previous version on failure

        Returns:
            DeploymentResult with deployment status and details

        Raises:
            DeploymentError: If deployment fails after retries
            ConfigurationError: If agent configuration is invalid
        """
        # Initialize deployment status
        deployment_id = f"{agent_id}-{version_id}-{int(datetime.utcnow().timestamp())}"
        status = DeploymentStatus(
            deployment_id=deployment_id,
            agent_id=agent_id,
            version_id=version_id,
            status=self.STATUS_PENDING,
            created_at=datetime.utcnow(),
            metadata=metadata or {},
        )
        self._deployments[deployment_id] = status

        # Get previous deployment for rollback
        previous_deployment = await self._get_previous_deployment(agent_id, version_id)

        try:
            # Step 1: Package agent
            safe_log(f"Packaging agent {agent_id} version {version_id}")
            status.status = self.STATUS_DEPLOYING
            status.updated_at = datetime.utcnow()

            package = await self._package_agent_with_validation(
                agent_id=agent_id,
                version_id=version_id,
                system_prompt=system_prompt,
                model=model,
                configured_mcps=configured_mcps,
                custom_mcps=custom_mcps,
                agentpress_tools=agentpress_tools,
                triggers=triggers,
                metadata=metadata,
            )

            # Step 2: Deploy to Runtime
            safe_log(f"Deploying packaged agent {agent_id} to Runtime")
            deployment_config = package.to_deployment_config()

            runtime_result = await self._deploy_with_retry(
                agent_id=agent_id,
                agent_config=deployment_config,
                version_id=version_id,
                timeout_seconds=timeout_seconds,
                enable_retry=enable_retry,
            )

            # Step 3: Update status
            status.status = self.STATUS_DEPLOYED
            status.deployment_arn = runtime_result.deployment_arn
            status.updated_at = datetime.utcnow()

            safe_log(f"Agent {agent_id} version {version_id} deployed successfully: {deployment_id}")

            return DeploymentResult(
                success=True,
                deployment_id=deployment_id,
                agent_id=agent_id,
                version_id=version_id,
                status=runtime_result.status,
                deployment_arn=runtime_result.deployment_arn,
                metadata={
                    "package": package.to_dict(),
                    "runtime_result": {
                        "agent_version": runtime_result.agent_version,
                        "readiness_status": runtime_result.readiness_status,
                    },
                },
            )

        except Exception as e:
            safe_log(f"Deployment failed for {agent_id} version {version_id}: {e}")

            status.status = self.STATUS_FAILED
            status.error_message = str(e)
            status.updated_at = datetime.utcnow()

            # Handle rollback if enabled
            rollback_performed = False
            if enable_rollback and previous_deployment:
                rollback_performed = await self._rollback_deployment(
                    agent_id=agent_id,
                    failed_deployment_id=deployment_id,
                    previous_deployment_id=previous_deployment,
                )

            if isinstance(e, (DeploymentError, ConfigurationError)):
                # Non-retryable errors
                raise
            else:
                # Wrap unexpected errors
                raise DeploymentError(
                    f"Failed to deploy agent {agent_id} version {version_id}: {e}"
                ) from e

    async def trigger_deployment(
        self,
        agent_id: str,
        version_id: str,
        agent_config: Dict[str, Any],
        trigger_type: str = "manual",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DeploymentResult:
        """
        Trigger a deployment from an external trigger (agent create/update).

        This is a convenience method for deployments triggered by:
        - Agent creation
        - Agent update
        - Version promotion
        - Manual trigger

        Args:
            agent_id: Unique identifier for the agent
            version_id: Version identifier for this deployment
            agent_config: Full agent configuration dictionary
            trigger_type: Type of trigger (create, update, promote, manual)
            metadata: Additional deployment metadata

        Returns:
            DeploymentResult with deployment status
        """
        trigger_metadata = {
            **(metadata or {}),
            "trigger_type": trigger_type,
            "triggered_at": datetime.utcnow().isoformat(),
        }

        # Extract common fields from agent_config
        system_prompt = agent_config.get("system_prompt", "")
        model = agent_config.get("model")
        configured_mcps = agent_config.get("configured_mcps", [])
        custom_mcps = agent_config.get("custom_mcps", [])
        agentpress_tools = agent_config.get("agentpress_tools", {})
        triggers = agent_config.get("triggers", [])

        return await self.deploy_agent_version(
            agent_id=agent_id,
            version_id=version_id,
            system_prompt=system_prompt,
            model=model,
            configured_mcps=configured_mcps,
            custom_mcps=custom_mcps,
            agentpress_tools=agentpress_tools,
            triggers=triggers,
            metadata=trigger_metadata,
        )

    async def get_deployment_status(
        self,
        deployment_id: str,
    ) -> Optional[DeploymentStatus]:
        """
        Get status of a deployment.

        Args:
            deployment_id: Deployment identifier

        Returns:
            DeploymentStatus if found, None otherwise
        """
        return self._deployments.get(deployment_id)

    async def list_deployments(
        self,
        agent_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[DeploymentStatus]:
        """
        List deployments with optional filtering.

        Args:
            agent_id: Filter by agent ID
            status: Filter by status
            limit: Maximum number of results

        Returns:
            List of deployment statuses
        """
        deployments = list(self._deployments.values())

        # Apply filters
        if agent_id:
            deployments = [d for d in deployments if d.agent_id == agent_id]
        if status:
            deployments = [d for d in deployments if d.status == status]

        # Sort by created_at descending
        deployments.sort(key=lambda d: d.created_at, reverse=True)

        return deployments[:limit]

    async def delete_deployment(
        self,
        deployment_id: str,
    ) -> bool:
        """
        Delete a deployment from tracking.

        Note: This only removes local tracking. The actual agent
        in AWS Bedrock Runtime is not deleted.

        Args:
            deployment_id: Deployment identifier

        Returns:
            True if deployment was deleted, False if not found
        """
        if deployment_id in self._deployments:
            del self._deployments[deployment_id]
            safe_log(f"Deleted deployment tracking for {deployment_id}")
            return True
        return False

    async def _package_agent_with_validation(
        self,
        agent_id: str,
        version_id: str,
        system_prompt: str,
        model: Optional[str] = None,
        configured_mcps: Optional[List[Dict[str, Any]]] = None,
        custom_mcps: Optional[List[Dict[str, Any]]] = None,
        agentpress_tools: Optional[Dict[str, Any]] = None,
        triggers: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentCorePackage:
        """
        Package agent with validation.

        Args:
            agent_id: Agent identifier
            version_id: Version identifier
            system_prompt: System prompt
            model: Model identifier
            configured_mcps: Configured MCPs
            custom_mcps: Custom MCPs
            agentpress_tools: AgentPress tools
            triggers: Triggers
            metadata: Additional metadata

        Returns:
            Validated AgentCorePackage

        Raises:
            ConfigurationError: If validation fails
        """
        # Package the agent
        package = self.packager.package_agent_version(
            agent_id=agent_id,
            version_id=version_id,
            system_prompt=system_prompt,
            model=model,
            configured_mcps=configured_mcps,
            custom_mcps=custom_mcps,
            agentpress_tools=agentpress_tools,
            triggers=triggers,
            metadata=metadata,
        )

        # Validate the package
        validation_errors = self.packager.validate_package(package)
        if validation_errors:
            raise ConfigurationError(
                f"Agent package validation failed: {', '.join(validation_errors)}"
            )

        return package

    async def _deploy_with_retry(
        self,
        agent_id: str,
        agent_config: Dict[str, Any],
        version_id: str,
        timeout_seconds: int = 300,
        enable_retry: bool = True,
    ) -> RuntimeDeploymentResult:
        """
        Deploy agent with retry logic.

        Args:
            agent_id: Agent identifier
            agent_config: Agent configuration
            version_id: Version identifier
            timeout_seconds: Deployment timeout
            enable_retry: Enable retry on transient failures

        Returns:
            RuntimeDeploymentResult from adapter

        Raises:
            DeploymentError: If deployment fails after retries
        """
        if enable_retry:
            return await with_retry(
                self.runtime_adapter.deploy_agent,
                max_attempts=self.config.deployment_retry_attempts,
                base_delay=self.config.retry_base_delay_seconds,
                max_delay=self.config.retry_max_delay_seconds,
                agent_id=agent_id,
                agent_config=agent_config,
                version_id=version_id,
                timeout_seconds=timeout_seconds,
            )
        else:
            return await self.runtime_adapter.deploy_agent(
                agent_id=agent_id,
                agent_config=agent_config,
                version_id=version_id,
                timeout_seconds=timeout_seconds,
            )

    async def _get_previous_deployment(
        self,
        agent_id: str,
        current_version_id: str,
    ) -> Optional[str]:
        """
        Get the previous successful deployment for an agent.

        Args:
            agent_id: Agent identifier
            current_version_id: Current version being deployed

        Returns:
            Previous deployment ID if found, None otherwise
        """
        deployments = await self.list_deployments(
            agent_id=agent_id,
            status=self.STATUS_DEPLOYED,
        )

        # Filter out current version and get most recent
        previous = [
            d for d in deployments
            if d.version_id != current_version_id
        ]

        if previous:
            return previous[0].deployment_id
        return None

    async def _rollback_deployment(
        self,
        agent_id: str,
        failed_deployment_id: str,
        previous_deployment_id: str,
    ) -> bool:
        """
        Rollback to a previous deployment.

        Note: For Phase 1, rollback is logical (updates deployment tracking).
        The actual agent in Runtime is not reverted.

        Args:
            agent_id: Agent identifier
            failed_deployment_id: Failed deployment to rollback from
            previous_deployment_id: Previous deployment to rollback to

        Returns:
            True if rollback was successful, False otherwise
        """
        try:
            safe_log(
                f"Rolling back agent {agent_id} from {failed_deployment_id} "
                f"to {previous_deployment_id}"
            )

            # Update failed deployment status
            if failed_deployment_id in self._deployments:
                self._deployments[failed_deployment_id].status = self.STATUS_ROLLED_BACK
                self._deployments[failed_deployment_id].updated_at = datetime.utcnow()
                self._deployments[failed_deployment_id].metadata["rolled_back_to"] = previous_deployment_id

            safe_log(f"Rollback completed for agent {agent_id}")
            return True

        except Exception as e:
            safe_log(f"Rollback failed for agent {agent_id}: {e}")
            return False


# Convenience functions for common operations

async def deploy_agent_for_runtime(
    agent_id: str,
    version_id: str,
    system_prompt: str,
    model: Optional[str] = None,
    configured_mcps: Optional[List[Dict[str, Any]]] = None,
    custom_mcps: Optional[List[Dict[str, Any]]] = None,
    agentpress_tools: Optional[Dict[str, Any]] = None,
    triggers: Optional[List[Dict[str, Any]]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    config: Optional[AgentCoreConfig] = None,
) -> DeploymentResult:
    """
    Convenience function to deploy an agent to AgentCore Runtime.

    This function creates a DeploymentManager and deploys the agent
    in a single call.

    Args:
        agent_id: Unique identifier for the agent
        version_id: Version identifier for this deployment
        system_prompt: Agent's system prompt/instructions
        model: Model identifier
        configured_mcps: List of configured MCP integrations
        custom_mcps: List of custom MCP integrations
        agentpress_tools: AgentPress tool configuration
        triggers: Agent triggers configuration
        metadata: Additional deployment metadata
        config: AgentCore configuration

    Returns:
        DeploymentResult with deployment status
    """
    manager = DeploymentManager(config=config)
    return await manager.deploy_agent_version(
        agent_id=agent_id,
        version_id=version_id,
        system_prompt=system_prompt,
        model=model,
        configured_mcps=configured_mcps,
        custom_mcps=custom_mcps,
        agentpress_tools=agentpress_tools,
        triggers=triggers,
        metadata=metadata,
    )


async def trigger_agent_deployment(
    agent_id: str,
    version_id: str,
    agent_config: Dict[str, Any],
    trigger_type: str = "manual",
    config: Optional[AgentCoreConfig] = None,
) -> DeploymentResult:
    """
    Convenience function to trigger an agent deployment.

    Args:
        agent_id: Unique identifier for the agent
        version_id: Version identifier for this deployment
        agent_config: Full agent configuration dictionary
        trigger_type: Type of trigger (create, update, promote, manual)
        config: AgentCore configuration

    Returns:
        DeploymentResult with deployment status
    """
    manager = DeploymentManager(config=config)
    return await manager.trigger_deployment(
        agent_id=agent_id,
        version_id=version_id,
        agent_config=agent_config,
        trigger_type=trigger_type,
    )
