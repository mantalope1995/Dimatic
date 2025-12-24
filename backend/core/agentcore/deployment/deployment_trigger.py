"""
AgentCore Deployment Trigger Service

Handles automatic deployment triggering for agent version creation and updates.
Integrates with the versioning service to deploy agents to AgentCore Runtime.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from ..config import AgentCoreConfig, get_config
from ..errors import safe_log
from .deployment_manager import DeploymentManager, DeploymentResult

logger = logging.getLogger(__name__)


@dataclass
class DeploymentTriggerConfig:
    """Configuration for deployment triggering"""
    auto_deploy_enabled: bool = True
    async_deployment: bool = True  # Deploy in background
    deploy_on_create: bool = True  # Deploy when version is created
    deploy_on_activate: bool = False  # Deploy when version is activated
    retry_failed_deployments: bool = True
    max_retry_attempts: int = 3


class DeploymentTriggerService:
    """
    Service for triggering AgentCore deployments on agent version changes.

    This service integrates with the versioning system to automatically
    deploy agent versions to AWS Bedrock AgentCore Runtime.
    """

    def __init__(
        self,
        config: Optional[AgentCoreConfig] = None,
        trigger_config: Optional[DeploymentTriggerConfig] = None,
    ):
        """
        Initialize the deployment trigger service.

        Args:
            config: AgentCore configuration
            trigger_config: Deployment trigger configuration
        """
        self.config = config or get_config()
        self.trigger_config = trigger_config or DeploymentTriggerConfig()

        # Validate configuration
        if not self.config.runtime_enabled:
            safe_log("AgentCore Runtime is disabled. Deployment triggering will be skipped.")
            self.trigger_config.auto_deploy_enabled = False

        self._deployment_manager: Optional[DeploymentManager] = None

    @property
    def deployment_manager(self) -> DeploymentManager:
        """Lazy initialization of deployment manager"""
        if self._deployment_manager is None:
            self._deployment_manager = DeploymentManager(config=self.config)
        return self._deployment_manager

    async def trigger_deployment(
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
    ) -> Optional[DeploymentResult]:
        """
        Trigger deployment for an agent version.

        Args:
            agent_id: Agent identifier
            version_id: Version identifier
            system_prompt: System prompt
            model: Model identifier
            configured_mcps: Configured MCPs
            custom_mcps: Custom MCPs
            agentpress_tools: AgentPress tools
            triggers: Agent triggers
            metadata: Additional metadata

        Returns:
            DeploymentResult if deployment was triggered, None if skipped

        Raises:
            DeploymentError: If deployment fails
        """
        # Check if auto-deploy is enabled
        if not self.trigger_config.auto_deploy_enabled:
            safe_log(f"Auto-deploy disabled for agent {agent_id} version {version_id}")
            return None

        # Check if Runtime is enabled
        if not self.config.runtime_enabled:
            safe_log(f"AgentCore Runtime disabled. Skipping deployment for agent {agent_id} version {version_id}")
            return None

        try:
            safe_log(f"Triggering deployment for agent {agent_id} version {version_id}")

            # Trigger the deployment
            result = await self.deployment_manager.deploy_agent_version(
                agent_id=agent_id,
                version_id=version_id,
                system_prompt=system_prompt,
                model=model,
                configured_mcps=configured_mcps,
                custom_mcps=custom_mcps,
                agentpress_tools=agentpress_tools,
                triggers=triggers,
                metadata=metadata,
                enable_retry=self.trigger_config.retry_failed_deployments,
            )

            safe_log(f"Deployment triggered successfully: {result.deployment_id}")
            return result

        except Exception as e:
            safe_log(f"Failed to trigger deployment for agent {agent_id} version {version_id}: {e}")
            # Don't raise - deployment failure shouldn't break version creation
            return None

    async def trigger_deployment_from_create(
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
    ) -> Optional[DeploymentResult]:
        """
        Trigger deployment after agent version creation.

        This is called by the versioning service when a new version is created.

        Args:
            agent_id: Agent identifier
            version_id: Version identifier
            system_prompt: System prompt
            model: Model identifier
            configured_mcps: Configured MCPs
            custom_mcps: Custom MCPs
            agentpress_tools: AgentPress tools
            triggers: Agent triggers
            metadata: Additional metadata

        Returns:
            DeploymentResult if deployment was triggered, None if skipped
        """
        if not self.trigger_config.deploy_on_create:
            safe_log(f"Deploy on create disabled. Skipping deployment for agent {agent_id} version {version_id}")
            return None

        trigger_metadata = {
            **(metadata or {}),
            "trigger_type": "version_create",
        }

        if self.trigger_config.async_deployment:
            # Deploy in background
            asyncio.create_task(
                self.trigger_deployment(
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
            )
            safe_log(f"Background deployment triggered for agent {agent_id} version {version_id}")
            return None
        else:
            return await self.trigger_deployment(
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

    async def trigger_deployment_from_activate(
        self,
        agent_id: str,
        version_id: str,
    ) -> Optional[DeploymentResult]:
        """
        Trigger deployment when a version is activated.

        This is called by the versioning service when a version is activated.

        Args:
            agent_id: Agent identifier
            version_id: Version identifier being activated

        Returns:
            DeploymentResult if deployment was triggered, None if skipped
        """
        if not self.trigger_config.deploy_on_activate:
            return None

        # For activation, we trigger deployment with the existing version data
        # The deployment manager will fetch the version details
        safe_log(f"Version activation trigger for agent {agent_id} version {version_id}")

        trigger_metadata = {
            "trigger_type": "version_activate",
        }

        if self.trigger_config.async_deployment:
            asyncio.create_task(
                self._deploy_active_version(
                    agent_id=agent_id,
                    version_id=version_id,
                    metadata=trigger_metadata,
                )
            )
            return None
        else:
            return await self._deploy_active_version(
                agent_id=agent_id,
                version_id=version_id,
                metadata=trigger_metadata,
            )

    async def _deploy_active_version(
        self,
        agent_id: str,
        version_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[DeploymentResult]:
        """Deploy the currently active version"""
        # This would require fetching version details from the database
        # For Phase 1, we'll implement this when needed
        safe_log(f"Deploy active version for agent {agent_id} version {version_id}")
        return None

    async def update_deployment_status(
        self,
        version_id: str,
        deployment_id: str,
        deployment_status: str,
        deployment_metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Update deployment status in the database.

        This updates the agent_versions table with the deployment status.

        Args:
            version_id: Version identifier
            deployment_id: Deployment identifier
            deployment_status: New deployment status
            deployment_metadata: Additional deployment metadata

        Returns:
            True if update was successful, False otherwise
        """
        try:
            from core.services.supabase import DBConnection
            client = await DBConnection().client

            update_data = {
                "deployment_id": deployment_id,
                "deployment_status": deployment_status,
            }

            if deployment_metadata:
                update_data["deployment_metadata"] = deployment_metadata

            if deployment_status == "deployed":
                update_data["deployed_at"] = "now()"

            result = await client.table("agent_versions").update(update_data).eq(
                "version_id", version_id
            ).execute()

            if result.data:
                safe_log(f"Updated deployment status for version {version_id}: {deployment_status}")
                return True
            else:
                safe_log(f"Failed to update deployment status for version {version_id}: version not found")
                return False

        except Exception as e:
            safe_log(f"Error updating deployment status for version {version_id}: {e}")
            return False


# Global service instance
_deployment_trigger_service: Optional[DeploymentTriggerService] = None


async def get_deployment_trigger_service(
    config: Optional[AgentCoreConfig] = None,
) -> DeploymentTriggerService:
    """
    Get the global deployment trigger service instance.

    Args:
        config: Optional AgentCore configuration

    Returns:
        DeploymentTriggerService instance
    """
    global _deployment_trigger_service
    if _deployment_trigger_service is None:
        _deployment_trigger_service = DeploymentTriggerService(config=config)
    return _deployment_trigger_service


# Convenience function for triggering deployment from version creation

async def trigger_deployment_on_version_create(
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
) -> Optional[DeploymentResult]:
    """
    Convenience function to trigger deployment after version creation.

    This can be called from the versioning service after creating a new version.

    Args:
        agent_id: Agent identifier
        version_id: Version identifier
        system_prompt: System prompt
        model: Model identifier
        configured_mcps: Configured MCPs
        custom_mcps: Custom MCPs
        agentpress_tools: AgentPress tools
        triggers: Agent triggers
        metadata: Additional metadata
        config: AgentCore configuration

    Returns:
        DeploymentResult if deployment was triggered, None if skipped
    """
    service = await get_deployment_trigger_service(config=config)
    return await service.trigger_deployment_from_create(
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
