"""
AWS Cognito OAuth Flow Service for AgentCore Gateway

Manages 3-legged OAuth 2.0 flows for third-party service integrations.
Handles state management for CSRF protection and token exchange.
"""

import json
import logging
import secrets
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode, urlparse, urlunparse

import boto3
from botocore.exceptions import ClientError

from ..config import AgentCoreConfig, get_config
from ..errors import with_retry, AgentCoreError, InvalidOAuthStateError, redact_sensitive_data

logger = logging.getLogger(__name__)


class OAuthTokenExchangeError(AgentCoreError):
    """Raised when OAuth token exchange fails"""
    pass


class OAuthAuthorizationError(AgentCoreError):
    """Raised when OAuth authorization fails"""
    pass


@dataclass
class OAuthState:
    """
    OAuth state for CSRF protection

    Attributes:
        state_id: Unique state identifier
        account_id: Account ID for tenant isolation
        service_name: Target service (github, slack, etc.)
        redirect_uri: OAuth callback URL
        code_verifier: PKCE code verifier (if using PKCE)
        created_at: State creation timestamp
        expires_at: State expiration timestamp
    """
    state_id: str
    account_id: str
    service_name: str
    redirect_uri: str
    code_verifier: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: str = field(default_factory=lambda: (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OAuthState':
        """Create from dictionary for storage"""
        return cls(**data)


@dataclass
class OAuthTokens:
    """
    OAuth tokens received from provider

    Attributes:
        access_token: OAuth access token
        refresh_token: Optional refresh token
        token_type: Token type (usually "Bearer")
        expires_in: Time until token expiration (seconds)
        scope: Granted OAuth scope
        received_at: Token receipt timestamp
    """
    access_token: str
    refresh_token: Optional[str]
    token_type: str = "Bearer"
    expires_in: Optional[int] = None
    scope: Optional[str] = None
    received_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OAuthTokens':
        """Create from dictionary for storage"""
        return cls(**data)

    def is_expired(self) -> bool:
        """Check if the access token is expired"""
        if not self.expires_in:
            return False  # No expiration set

        received = datetime.fromisoformat(self.received_at)
        expiration = received + timedelta(seconds=self.expires_in)
        return datetime.now(timezone.utc) >= expiration


class OAuthFlowService:
    """
    AWS Cognito-backed OAuth 2.0 flow management

    Manages 3-legged OAuth flows for third-party service integrations.
    Uses DynamoDB for state storage with automatic cleanup of expired states.

    Flow:
    1. initiate_oauth_flow() -> Returns authorization URL with state
    2. User authorizes at provider -> Redirects to callback with code
    3. exchange_code_for_tokens() -> Exchanges code for access/refresh tokens
    4. Tokens stored in Secrets Manager for future use
    """

    # OAuth state storage table (can use same DynamoDB pattern)
    def __init__(self, config: Optional[AgentCoreConfig] = None):
        """
        Initialize OAuth Flow service

        Args:
            config: AgentCore configuration (uses global config if not provided)
        """
        self.config = config or get_config()
        self._validate_config()
        self._initialize_client()

        # Import SecretsManager for token storage
        from .secrets_manager_adapter import SecretsManagerAdapter
        self.secrets_manager = SecretsManagerAdapter(config=self.config)

    def _validate_config(self):
        """Validate that required configuration is available"""
        if self.config.is_local():
            logger.warning("OAuth Flow service initialized in local mode (AWS calls will be mocked)")

        if not self.config.is_local():
            if not self.config.aws_access_key_id or not self.config.aws_secret_access_key:
                raise ValueError("AWS credentials required for OAuth Flow in non-local environment")

            if not self.config.oauth_callback_base_url:
                raise ValueError("OAUTH_CALLBACK_BASE_URL must be configured")

    def _initialize_client(self):
        """Initialize boto3 clients"""
        logger.info(
            f"Initializing OAuth Flow service for {self.config.environment} environment "
            f"(callback base: {self.config.oauth_callback_base_url or 'mock'})"
        )

        if self.config.is_local():
            # For local development, create mock clients
            self.dynamodb_client = None
            self._mock_states: Dict[str, OAuthState] = {}
            logger.debug("OAuth Flow service in local mode (no real AWS calls)")
        else:
            # DynamoDB for state storage
            self.dynamodb_resource = boto3.resource(
                'dynamodb',
                region_name=self.config.aws_region,
                aws_access_key_id=self.config.aws_access_key_id,
                aws_secret_access_key=self.config.aws_secret_access_key
            )
            logger.debug(f"DynamoDB client initialized (region: {self.config.aws_region})")

    def _get_states_table(self):
        """Get DynamoDB table for OAuth states"""
        if self.config.is_local():
            return None
        return self.dynamodb_resource.Table(self.config.dynamodb_oauth_states_table)

    def _generate_state_id(self) -> str:
        """Generate cryptographically secure random state ID"""
        return secrets.token_urlsafe(32)

    def _hash_state(self, state_id: str) -> str:
        """Hash state ID for verification"""
        return hashlib.sha256(state_id.encode()).hexdigest()

    def _build_callback_uri(self, service_name: str) -> str:
        """
        Build OAuth callback URI for a service

        Args:
            service_name: Service name (github, slack, etc.)

        Returns:
            Full callback URL
        """
        base_url = self.config.oauth_callback_base_url.rstrip("/")
        # Get callback path from service definition or use default
        callback_path = f"/oauth/{service_name}/callback"
        return f"{base_url}{callback_path}"

    async def initiate_oauth_flow(
        self,
        account_id: str,
        service_name: str,
        oauth_config: Dict[str, Any],
        additional_scopes: Optional[list] = None
    ) -> str:
        """
        Initiate OAuth 2.0 authorization flow

        Generates authorization URL with state parameter for CSRF protection.
        Stores state in DynamoDB for later verification.

        Args:
            account_id: Account ID for tenant isolation
            service_name: Target service (github, slack, etc.)
            oauth_config: OAuth configuration from MCP catalog
            additional_scopes: Optional additional scopes to request

        Returns:
            Authorization URL to redirect user to

        Raises:
            AgentCoreError: If flow initiation fails
        """
        logger.info(f"Initiating OAuth flow for {service_name} (account: {account_id})")

        try:
            # Generate state for CSRF protection
            state_id = self._generate_state_id()
            redirect_uri = self._build_callback_uri(service_name)

            # Create OAuth state
            oauth_state = OAuthState(
                state_id=state_id,
                account_id=account_id,
                service_name=service_name,
                redirect_uri=redirect_uri
            )

            # Store state
            await self._store_oauth_state(oauth_state)

            # Build authorization URL
            auth_url = self._build_authorization_url(
                oauth_config=oauth_config,
                state_id=state_id,
                redirect_uri=redirect_uri,
                additional_scopes=additional_scopes
            )

            logger.info(f"OAuth flow initiated (state: {state_id[:8]}...)")
            return auth_url

        except Exception as e:
            logger.error(f"Failed to initiate OAuth flow: {e}")
            raise AgentCoreError(f"Failed to initiate OAuth flow: {str(e)}")

    def _build_authorization_url(
        self,
        oauth_config: Dict[str, Any],
        state_id: str,
        redirect_uri: str,
        additional_scopes: Optional[list] = None
    ) -> str:
        """Build OAuth authorization URL with parameters"""
        base_url = oauth_config["authorization_url"]

        # Get scopes
        scope = oauth_config.get("scope", "")
        if additional_scopes:
            # Combine scopes (comma or space separated)
            existing_scopes = scope.replace(",", " ").split()
            new_scopes = [s for s in additional_scopes if s not in existing_scopes]
            scope = " ".join(existing_scopes + new_scopes)

        # Build query parameters
        params = {
            "client_id": oauth_config.get("client_id", ""),  # May be empty for some providers
            "redirect_uri": redirect_uri,
            "state": state_id,
            "response_type": "code",
        }

        if scope:
            params["scope"] = scope

        # Add provider-specific parameters
        if "approval_prompt" in oauth_config:
            params["approval_prompt"] = oauth_config["approval_prompt"]
        if "access_type" in oauth_config:
            params["access_type"] = oauth_config["access_type"]

        # Add PKCE if enabled (generate code challenge)
        if oauth_config.get("use_pkce", False):
            code_verifier = secrets.token_urlsafe(32)
            code_challenge = hashlib.sha256(code_verifier.encode()).hexdigest()
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"

            # Store code verifier with state
            # (In production, would need to update state storage)

        # Construct URL
        url_parts = list(urlparse(base_url))
        query = urlencode(params)
        url_parts[4] = query
        return urlunparse(url_parts)

    @with_retry(max_attempts=3)
    async def _store_oauth_state(self, oauth_state: OAuthState) -> None:
        """Store OAuth state in DynamoDB"""
        state_id = oauth_state.state_id

        try:
            if self.config.is_local():
                # Mock implementation
                self._mock_states[state_id] = oauth_state
                logger.debug(f"[LOCAL] Mock stored OAuth state: {state_id[:8]}...")
                return

            table = self._get_states_table()

            # Calculate TTL (5 minutes from now)
            ttl = int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp())

            item = {
                "state_id": state_id,
                "account_id": oauth_state.account_id,
                "service_name": oauth_state.service_name,
                "redirect_uri": oauth_state.redirect_uri,
                "created_at": oauth_state.created_at,
                "expires_at": oauth_state.expires_at,
                "ttl": ttl
            }

            table.put_item(Item=item)
            logger.debug(f"Stored OAuth state: {state_id[:8]}...")

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"DynamoDB error storing state: {error_code} - {error_message}")
            raise AgentCoreError(f"Failed to store OAuth state: {error_message}")

    @with_retry(max_attempts=3)
    async def validate_oauth_state(
        self,
        state_id: str
    ) -> OAuthState:
        """
        Validate OAuth state and retrieve metadata

        Args:
            state_id: State ID from authorization callback

        Returns:
            OAuth state metadata

        Raises:
            InvalidOAuthStateError: If state is invalid or expired
            AgentCoreError: If validation fails
        """
        logger.debug(f"Validating OAuth state: {state_id[:8]}...")

        try:
            if self.config.is_local():
                # Mock implementation
                if state_id not in self._mock_states:
                    raise InvalidOAuthStateError(
                        f"Invalid OAuth state: {state_id[:8]}..."
                    )
                state = self._mock_states[state_id]

                # Check expiration
                if datetime.now(timezone.utc) >= datetime.fromisoformat(state.expires_at):
                    del self._mock_states[state_id]
                    raise InvalidOAuthStateError(
                        f"OAuth state expired: {state_id[:8]}..."
                    )

                logger.debug(f"OAuth state validated: {state_id[:8]}...")
                return state

            table = self._get_states_table()

            # Get state
            response = table.get_item(Key={"state_id": state_id})

            if "Item" not in response:
                raise InvalidOAuthStateError(
                    f"Invalid OAuth state: {state_id[:8]}..."
                )

            item = response["Item"]
            state = OAuthState(
                state_id=item["state_id"],
                account_id=item["account_id"],
                service_name=item["service_name"],
                redirect_uri=item["redirect_uri"],
                created_at=item["created_at"],
                expires_at=item["expires_at"]
            )

            # Check expiration
            if datetime.now(timezone.utc) >= datetime.fromisoformat(state.expires_at):
                # Delete expired state
                await self._delete_oauth_state(state_id)
                raise InvalidOAuthStateError(
                    f"OAuth state expired: {state_id[:8]}..."
                )

            logger.debug(f"OAuth state validated: {state_id[:8]}...")
            return state

        except InvalidOAuthStateError:
            raise
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"DynamoDB error validating state: {error_code} - {error_message}")
            raise AgentCoreError(f"Failed to validate OAuth state: {error_message}")

    @with_retry(max_attempts=3)
    async def _delete_oauth_state(self, state_id: str) -> None:
        """Delete OAuth state after use"""
        try:
            if self.config.is_local():
                # Mock implementation
                if state_id in self._mock_states:
                    del self._mock_states[state_id]
                logger.debug(f"[LOCAL] Mock deleted OAuth state: {state_id[:8]}...")
                return

            table = self._get_states_table()
            table.delete_item(Key={"state_id": state_id})
            logger.debug(f"Deleted OAuth state: {state_id[:8]}...")

        except ClientError as e:
            # Log but don't raise - state cleanup is best-effort
            logger.warning(f"Failed to delete OAuth state: {e}")

    async def exchange_code_for_tokens(
        self,
        code: str,
        state_id: str,
        oauth_config: Dict[str, Any]
    ) -> OAuthTokens:
        """
        Exchange authorization code for access/refresh tokens

        Args:
            code: Authorization code from OAuth callback
            state_id: State ID for validation
            oauth_config: OAuth configuration from MCP catalog

        Returns:
            OAuth tokens (access_token, refresh_token, etc.)

        Raises:
            InvalidOAuthStateError: If state validation fails
            OAuthTokenExchangeError: If token exchange fails
            AgentCoreError: If operation fails
        """
        logger.info(f"Exchanging code for tokens (state: {state_id[:8]}...)")

        try:
            # Validate state first
            oauth_state = await self.validate_oauth_state(state_id)

            # Build token exchange request
            token_response = await self._perform_token_exchange(
                code=code,
                redirect_uri=oauth_state.redirect_uri,
                oauth_config=oauth_config
            )

            # Parse tokens
            tokens = OAuthTokens(
                access_token=token_response.get("access_token"),
                refresh_token=token_response.get("refresh_token"),
                token_type=token_response.get("token_type", "Bearer"),
                expires_in=token_response.get("expires_in"),
                scope=token_response.get("scope"),
                received_at=datetime.now(timezone.utc).isoformat()
            )

            # Store tokens in Secrets Manager
            await self.secrets_manager.store_credentials(
                account_id=oauth_state.account_id,
                service=oauth_state.service_name,
                credentials=tokens.to_dict()
            )

            # Clean up state
            await self._delete_oauth_state(state_id)

            logger.info(f"Successfully exchanged tokens for {oauth_state.service_name}")
            return tokens

        except InvalidOAuthStateError:
            raise
        except Exception as e:
            logger.error(f"Failed to exchange code for tokens: {e}")
            raise OAuthTokenExchangeError(f"Token exchange failed: {str(e)}")

    async def _perform_token_exchange(
        self,
        code: str,
        redirect_uri: str,
        oauth_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Perform HTTP request to exchange code for tokens

        Args:
            code: Authorization code
            redirect_uri: OAuth callback URI
            oauth_config: OAuth configuration

        Returns:
            Token response from OAuth provider
        """
        import httpx

        token_url = oauth_config["token_url"]

        # Build request parameters
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }

        # Add client authentication
        if "client_id" in oauth_config:
            data["client_id"] = oauth_config["client_id"]
        if "client_secret" in oauth_config:
            data["client_secret"] = oauth_config["client_secret"]

        # For some providers, use Basic auth
        headers = {"Accept": "application/json"}
        if oauth_config.get("use_basic_auth", False):
            credentials = f"{oauth_config['client_id']}:{oauth_config['client_secret']}"
            headers["Authorization"] = f"Basic {credentials.encode().decode()}"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                token_url,
                data=data,
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()

            # Parse JSON response
            if response.headers.get("content-type", "").startswith("application/json"):
                return response.json()
            else:
                # Some providers return form-encoded
                return dict(urlparse.parse_qs(response.text))

    async def refresh_tokens(
        self,
        account_id: str,
        service_name: str,
        oauth_config: Dict[str, Any]
    ) -> OAuthTokens:
        """
        Refresh expired access tokens using refresh token

        Args:
            account_id: Account ID for tenant isolation
            service_name: Service name
            oauth_config: OAuth configuration

        Returns:
            New OAuth tokens

        Raises:
            OAuthTokenExchangeError: If refresh fails
            AgentCoreError: If operation fails
        """
        logger.info(f"Refreshing tokens for {service_name} (account: {account_id})")

        try:
            # Get current credentials (including refresh token)
            credentials = await self.secrets_manager.get_credentials(account_id, service_name)

            refresh_token = credentials.get("refresh_token")
            if not refresh_token:
                raise OAuthTokenExchangeError("No refresh token available")

            # Perform token refresh
            token_response = await self._perform_token_refresh(
                refresh_token=refresh_token,
                oauth_config=oauth_config
            )

            # Create new tokens object
            new_tokens = OAuthTokens(
                access_token=token_response.get("access_token"),
                refresh_token=token_response.get("refresh_token", refresh_token),  # Keep old if not returned
                token_type=token_response.get("token_type", "Bearer"),
                expires_in=token_response.get("expires_in"),
                scope=token_response.get("scope"),
                received_at=datetime.now(timezone.utc).isoformat()
            )

            # Update stored tokens
            await self.secrets_manager.update_credentials(
                account_id=account_id,
                service=service_name,
                credentials=new_tokens.to_dict()
            )

            logger.info(f"Successfully refreshed tokens for {service_name}")
            return new_tokens

        except OAuthTokenExchangeError:
            raise
        except Exception as e:
            logger.error(f"Failed to refresh tokens: {e}")
            raise AgentCoreError(f"Token refresh failed: {str(e)}")

    async def _perform_token_refresh(
        self,
        refresh_token: str,
        oauth_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Perform HTTP request to refresh tokens

        Args:
            refresh_token: Refresh token
            oauth_config: OAuth configuration

        Returns:
            Token response from OAuth provider
        """
        import httpx

        token_url = oauth_config["token_url"]

        # Build request parameters
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }

        # Add client authentication
        if "client_id" in oauth_config:
            data["client_id"] = oauth_config["client_id"]
        if "client_secret" in oauth_config:
            data["client_secret"] = oauth_config["client_secret"]

        # For some providers, use Basic auth
        headers = {"Accept": "application/json"}
        if oauth_config.get("use_basic_auth", False):
            credentials = f"{oauth_config['client_id']}:{oauth_config['client_secret']}"
            headers["Authorization"] = f"Basic {credentials.encode()}"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                token_url,
                data=data,
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()

            # Parse JSON response
            if response.headers.get("content-type", "").startswith("application/json"):
                return response.json()
            else:
                # Some providers return form-encoded
                return dict(urlparse.parse_qs(response.text))

    async def cleanup_expired_states(self) -> int:
        """
        Clean up expired OAuth states from storage

        Returns:
            Number of states cleaned up

        Raises:
            AgentCoreError: If cleanup fails
        """
        logger.debug("Cleaning up expired OAuth states")

        try:
            if self.config.is_local():
                # Mock implementation - clean up mock states
                now = datetime.now(timezone.utc)
                expired_keys = [
                    state_id for state_id, state in self._mock_states.items()
                    if now >= datetime.fromisoformat(state.expires_at)
                ]

                for state_id in expired_keys:
                    del self._mock_states[state_id]

                logger.debug(f"[LOCAL] Mock cleaned up {len(expired_keys)} expired states")
                return len(expired_keys)

            # For DynamoDB, rely on TTL
            # Just scan for logging
            table = self._get_states_table()
            response = table.scan(ProjectionExpression="state_id,expires_at")

            now = datetime.now(timezone.utc)
            expired_count = 0

            for item in response.get("Items", []):
                expires_at = datetime.fromisoformat(item["expires_at"])
                if now >= expires_at:
                    expired_count += 1
                    # Optionally delete (TTL should handle this)
                    # table.delete_item(Key={"state_id": item["state_id"]})

            logger.debug(f"Found {expired_count} expired states (TTL will clean them)")
            return expired_count

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"DynamoDB error during cleanup: {error_code} - {error_message}")
            raise AgentCoreError(f"Failed to cleanup states: {error_message}")
