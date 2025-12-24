"""
AWS Secrets Manager Adapter for AgentCore Gateway

Provides tenant-isolated credential storage for OAuth tokens and API keys.
Stores credentials in AWS Secrets Manager with path pattern: kortix/{account_id}/{service}
"""

import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from ..config import AgentCoreConfig, get_config
from ..errors import with_retry, AgentCoreError, AgentCoreNonRetryableError, redact_sensitive_data

logger = logging.getLogger(__name__)


class SecretNotFoundError(AgentCoreNonRetryableError):
    """Raised when a requested secret doesn't exist in Secrets Manager"""
    pass


class SecretAlreadyExistsError(AgentCoreNonRetryableError):
    """Raised when attempting to create a secret that already exists"""
    pass


class SecretsManagerAdapter:
    """
    Adapter for AWS Secrets Manager operations

    Handles tenant-isolated credential storage for OAuth tokens, API keys,
    and other sensitive data. Uses path pattern: kortix/{account_id}/{service}

    Example paths:
    - kortix/account-123/github          -> GitHub OAuth token for account-123
    - kortix/account-123/slack           -> Slack OAuth token for account-123
    - kortix/account-123/gmail           -> Gmail OAuth token for account-123
    """

    def __init__(self, config: Optional[AgentCoreConfig] = None):
        """
        Initialize AWS Secrets Manager adapter

        Args:
            config: AgentCore configuration (uses global config if not provided)
        """
        self.config = config or get_config()
        self._validate_config()
        self._initialize_client()

    def _validate_config(self):
        """Validate that required configuration is available"""
        if self.config.is_local():
            logger.warning("Secrets Manager adapter initialized in local mode (AWS calls will be mocked)")

        if not self.config.is_local():
            if not self.config.aws_access_key_id or not self.config.aws_secret_access_key:
                raise ValueError("AWS credentials required for Secrets Manager in non-local environment")

    def _initialize_client(self):
        """Initialize boto3 Secrets Manager client"""
        logger.info(
            f"Initializing AWS Secrets Manager adapter for {self.config.environment} environment "
            f"(region: {self.config.aws_region})"
        )

        if self.config.is_local():
            # For local development, create mock client
            self.client = None
            logger.debug("Secrets Manager adapter in local mode (no real AWS calls)")
        else:
            self.client = boto3.client(
                'secretsmanager',
                region_name=self.config.aws_region,
                aws_access_key_id=self.config.aws_access_key_id,
                aws_secret_access_key=self.config.aws_secret_access_key
            )
            logger.debug(f"Secrets Manager client initialized (region: {self.config.aws_region})")

    def _get_secret_path(self, account_id: str, service: str) -> str:
        """
        Generate Secrets Manager path for tenant-isolated credentials

        Args:
            account_id: Account identifier for tenant isolation
            service: Service name (github, slack, gmail, etc.)

        Returns:
            Secret path in format: {prefix}/{account_id}/{service}
        """
        prefix = self.config.secrets_manager_prefix
        return f"{prefix}/{account_id}/{service}"

    @with_retry(max_attempts=3)
    async def store_credentials(
        self,
        account_id: str,
        service: str,
        credentials: Dict[str, Any],
        description: Optional[str] = None
    ) -> str:
        """
        Store OAuth credentials in Secrets Manager

        Creates a new secret with the provided credentials. If a secret with
        the same path exists, it will be updated.

        Args:
            account_id: Account identifier for tenant isolation
            service: Service name (github, slack, gmail, etc.)
            credentials: Dictionary containing credentials (access_token, refresh_token, etc.)
            description: Optional description for the secret

        Returns:
            secret_arn: The ARN of the created/updated secret

        Raises:
            AgentCoreError: If storage fails after retries
        """
        secret_path = self._get_secret_path(account_id, service)
        logger.info(f"Storing credentials for {service} (account: {account_id})")

        # Prepare secret value
        secret_value = json.dumps({
            "service": service,
            "account_id": account_id,
            "credentials": credentials,
            "stored_at": datetime.now(timezone.utc).isoformat()
        })

        # Prepare secret description
        if description is None:
            description = f"OAuth credentials for {service} (account: {account_id})"

        try:
            if self.config.is_local():
                # Mock implementation for local development
                mock_arn = f"arn:aws:secretsmanager:{self.config.aws_region}:123456789:secret:{secret_path}"
                logger.debug(f"[LOCAL] Mock storing secret at {secret_path}")
                return mock_arn

            # Check if secret exists
            try:
                self.client.get_secret_value(SecretId=secret_path)
                # Secret exists, update it
                logger.debug(f"Secret exists at {secret_path}, updating...")
                response = self.client.update_secret(
                    SecretId=secret_path,
                    SecretString=secret_value,
                    Description=description
                )
                logger.info(f"Updated credentials at {secret_path}")
            except self.client.exceptions.ResourceNotFoundException:
                # Secret doesn't exist, create it
                logger.debug(f"Creating new secret at {secret_path}")
                response = self.client.create_secret(
                    Name=secret_path,
                    SecretString=secret_value,
                    Description=description
                )
                logger.info(f"Created credentials at {secret_path}")

            secret_arn = response['ARN']
            logger.debug(f"Credentials stored successfully (ARN: {redact_sensitive_data(secret_arn)})")
            return secret_arn

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"AWS Secrets Manager error: {error_code} - {error_message}")
            raise AgentCoreError(f"Failed to store credentials: {error_message}")

    @with_retry(max_attempts=3)
    async def get_credentials(
        self,
        account_id: str,
        service: str
    ) -> Dict[str, Any]:
        """
        Retrieve OAuth credentials from Secrets Manager

        Args:
            account_id: Account identifier for tenant isolation
            service: Service name (github, slack, gmail, etc.)

        Returns:
            credentials: Dictionary containing stored credentials

        Raises:
            SecretNotFoundError: If secret doesn't exist
            AgentCoreError: If retrieval fails after retries
        """
        secret_path = self._get_secret_path(account_id, service)
        logger.debug(f"Retrieving credentials for {service} (account: {account_id})")

        try:
            if self.config.is_local():
                # Mock implementation for local development
                mock_credentials = {
                    "service": service,
                    "account_id": account_id,
                    "credentials": {
                        "access_token": "mock_token",
                        "refresh_token": "mock_refresh_token"
                    }
                }
                logger.debug(f"[LOCAL] Mock retrieving secret from {secret_path}")
                return mock_credentials

            response = self.client.get_secret_value(SecretId=secret_path)

            if 'SecretString' not in response:
                raise AgentCoreError(f"Secret at {secret_path} has no SecretString")

            secret_data = json.loads(response['SecretString'])
            credentials = secret_data.get('credentials', {})

            logger.debug(f"Retrieved credentials for {service} (account: {account_id})")
            return credentials

        except self.client.exceptions.ResourceNotFoundException:
            logger.warning(f"Secret not found: {secret_path}")
            raise SecretNotFoundError(
                f"No credentials found for {service} (account: {account_id}). "
                f"Please authenticate first."
            )
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"AWS Secrets Manager error: {error_code} - {error_message}")
            raise AgentCoreError(f"Failed to retrieve credentials: {error_message}")

    @with_retry(max_attempts=3)
    async def delete_credentials(
        self,
        account_id: str,
        service: str,
        force_delete_without_recovery: bool = False
    ) -> bool:
        """
        Delete OAuth credentials from Secrets Manager

        Args:
            account_id: Account identifier for tenant isolation
            service: Service name (github, slack, gmail, etc.)
            force_delete_without_recovery: If True, delete without recovery window

        Returns:
            True if deletion was successful

        Raises:
            SecretNotFoundError: If secret doesn't exist
            AgentCoreError: If deletion fails after retries
        """
        secret_path = self._get_secret_path(account_id, service)
        logger.info(f"Deleting credentials for {service} (account: {account_id})")

        try:
            if self.config.is_local():
                # Mock implementation for local development
                logger.debug(f"[LOCAL] Mock deleting secret at {secret_path}")
                return True

            # Schedule deletion (with recovery window by default)
            deletion_params = {
                'SecretId': secret_path
            }

            if force_delete_without_recovery:
                deletion_params['ForceDeleteWithoutRecovery'] = True

            response = self.client.delete_secret(**deletion_params)
            logger.info(f"Deleted credentials at {secret_path} (ARN: {redact_sensitive_data(response.get('ARN', ''))})")
            return True

        except self.client.exceptions.ResourceNotFoundException:
            logger.warning(f"Secret not found for deletion: {secret_path}")
            raise SecretNotFoundError(
                f"No credentials found for {service} (account: {account_id})"
            )
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"AWS Secrets Manager error: {error_code} - {error_message}")
            raise AgentCoreError(f"Failed to delete credentials: {error_message}")

    @with_retry(max_attempts=3)
    async def list_services_for_account(
        self,
        account_id: str
    ) -> list[str]:
        """
        List all services with stored credentials for an account

        Args:
            account_id: Account identifier for tenant isolation

        Returns:
            services: List of service names that have credentials stored

        Raises:
            AgentCoreError: If listing fails after retries
        """
        prefix = f"{self.config.secrets_manager_prefix}/{account_id}/"
        logger.debug(f"Listing credentials for account: {account_id}")

        try:
            if self.config.is_local():
                # Mock implementation for local development
                mock_services = ['github', 'slack', 'gmail']
                logger.debug(f"[LOCAL] Mock listing services: {mock_services}")
                return mock_services

            services = []
            paginator = self.client.get_paginator('list_secrets')

            for page in paginator.paginate(PaginationConfig={'PageSize': 100}):
                for secret in page.get('SecretList', []):
                    secret_name = secret['Name']
                    if secret_name.startswith(prefix):
                        # Extract service name from path
                        service = secret_name[len(prefix):]
                        services.append(service)

            logger.debug(f"Found {len(services)} services for account {account_id}")
            return services

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"AWS Secrets Manager error: {error_code} - {error_message}")
            raise AgentCoreError(f"Failed to list credentials: {error_message}")

    @with_retry(max_attempts=3)
    async def update_credentials(
        self,
        account_id: str,
        service: str,
        credentials: Dict[str, Any],
        description: Optional[str] = None
    ) -> str:
        """
        Update existing OAuth credentials in Secrets Manager

        This is an alias for store_credentials for compatibility.
        In AWS Secrets Manager, create_secret and update_secret handle both cases.

        Args:
            account_id: Account identifier for tenant isolation
            service: Service name (github, slack, gmail, etc.)
            credentials: Dictionary containing updated credentials
            description: Optional new description for the secret

        Returns:
            secret_arn: The ARN of the updated secret

        Raises:
            SecretNotFoundError: If secret doesn't exist
            AgentCoreError: If update fails after retries
        """
        secret_path = self._get_secret_path(account_id, service)

        # Verify secret exists first
        try:
            if not self.config.is_local():
                self.client.get_secret_value(SecretId=secret_path)
        except self.client.exceptions.ResourceNotFoundException:
            raise SecretNotFoundError(
                f"Cannot update non-existent credentials for {service} (account: {account_id})"
            )

        # Proceed with update (same as store_credentials)
        return await self.store_credentials(account_id, service, credentials, description)

    async def credentials_exist(
        self,
        account_id: str,
        service: str
    ) -> bool:
        """
        Check if credentials exist for a service

        Args:
            account_id: Account identifier for tenant isolation
            service: Service name (github, slack, gmail, etc.)

        Returns:
            True if credentials exist, False otherwise
        """
        try:
            await self.get_credentials(account_id, service)
            return True
        except SecretNotFoundError:
            return False
        except Exception as e:
            logger.warning(f"Error checking credential existence: {e}")
            return False
