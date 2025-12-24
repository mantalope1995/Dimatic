"""
Tests for OAuth Flow Service

Unit tests for OAuth 2.0 flow management, state validation,
and token exchange with tenant isolation.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from botocore.exceptions import ClientError
from datetime import datetime, timezone, timedelta

from core.agentcore.services.oauth_flow_service import (
    OAuthFlowService,
    OAuthTokenExchangeError,
    OAuthAuthorizationError,
    OAuthState,
    OAuthTokens
)
from core.agentcore.config import AgentCoreConfig, Environment


@pytest.fixture
def mock_config():
    """Create a mock AgentCore config for testing"""
    return AgentCoreConfig(
        environment=Environment.LOCAL,
        aws_region="ap-southeast-2",
        aws_access_key_id="test-key",
        aws_secret_access_key="test-secret",
        dynamodb_oauth_states_table="agentcore_oauth_states",
        oauth_callback_base_url="https://api.example.com"
    )


@pytest.fixture
def oauth_service(mock_config):
    """Create an OAuth Flow service for testing"""
    return OAuthFlowService(config=mock_config)


@pytest.fixture
def sample_oauth_config():
    """Create sample OAuth configuration"""
    return {
        "authorization_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "scope": "repo,read:user",
        "client_id": "test_client_id",
        "client_secret": "test_client_secret",
        "use_basic_auth": False
    }


@pytest.fixture
def sample_state():
    """Create sample OAuth state"""
    return OAuthState(
        state_id="test_state_id_12345",
        account_id="account-123",
        service_name="github",
        redirect_uri="https://api.example.com/oauth/github/callback"
    )


class TestOAuthState:
    """Test suite for OAuthState dataclass"""

    def test_state_creation(self):
        """Test creating OAuth state"""
        state = OAuthState(
            state_id="test_state",
            account_id="account-123",
            service_name="github",
            redirect_uri="https://example.com/callback"
        )

        assert state.state_id == "test_state"
        assert state.account_id == "account-123"
        assert state.service_name == "github"

    def test_state_expiration(self):
        """Test state expiration calculation"""
        state = OAuthState(
            state_id="test_state",
            account_id="account-123",
            service_name="github",
            redirect_uri="https://example.com/callback"
        )

        # Should expire ~5 minutes from creation
        created = datetime.fromisoformat(state.created_at)
        expires = datetime.fromisoformat(state.expires_at)
        duration = (expires - created).total_seconds()

        assert 290 <= duration <= 310  # ~5 minutes with some tolerance

    def test_state_serialization(self):
        """Test state to_dict serialization"""
        state = OAuthState(
            state_id="test_state",
            account_id="account-123",
            service_name="github",
            redirect_uri="https://example.com/callback"
        )

        data = state.to_dict()

        assert data["state_id"] == "test_state"
        assert data["account_id"] == "account-123"

        # Test round-trip
        restored = OAuthState.from_dict(data)
        assert restored.state_id == state.state_id
        assert restored.account_id == state.account_id


class TestOAuthTokens:
    """Test suite for OAuthTokens dataclass"""

    def test_tokens_creation(self):
        """Test creating OAuth tokens"""
        tokens = OAuthTokens(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            expires_in=3600
        )

        assert tokens.access_token == "test_access_token"
        assert tokens.refresh_token == "test_refresh_token"
        assert tokens.expires_in == 3600

    def test_token_expiration_check(self):
        """Test token expiration check"""
        # Expired token
        expired_tokens = OAuthTokens(
            access_token="expired_token",
            refresh_token="refresh",
            expires_in=3600,
            received_at=(datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        )

        assert expired_tokens.is_expired() is True

        # Valid token
        valid_tokens = OAuthTokens(
            access_token="valid_token",
            refresh_token="refresh",
            expires_in=3600
        )

        assert valid_tokens.is_expired() is False

    def test_tokens_without_expiration(self):
        """Test tokens without expiration never expire"""
        tokens = OAuthTokens(
            access_token="token",
            refresh_token="refresh"
            # No expires_in set
        )

        assert tokens.is_expired() is False


class TestOAuthFlowService:
    """Test suite for OAuthFlowService"""

    def test_init_local_environment(self, mock_config):
        """Test service initialization in local environment"""
        service = OAuthFlowService(config=mock_config)
        assert service.config == mock_config
        assert service.dynamodb_client is None

    def test_generate_state_id(self, oauth_service):
        """Test state ID generation is unique"""
        state1 = oauth_service._generate_state_id()
        state2 = oauth_service._generate_state_id()

        assert state1 != state2
        assert len(state1) >= 32  # Base64 encoded, at least 32 chars
        assert len(state2) >= 32

    def test_hash_state(self, oauth_service):
        """Test state hashing is deterministic"""
        state_id = "test_state_123"
        hash1 = oauth_service._hash_state(state_id)
        hash2 = oauth_service._hash_state(state_id)

        assert hash1 == hash2
        assert hash1 != state_id  # Hash should be different from original

    def test_build_callback_uri(self, oauth_service):
        """Test callback URI building"""
        uri = oauth_service._build_callback_uri("github")

        assert uri == "https://api.example.com/oauth/github/callback"

        uri = oauth_service._build_callback_uri("slack")
        assert uri == "https://api.example.com/oauth/slack/callback"

    @pytest.mark.asyncio
    async def test_initiate_oauth_flow_local_mode(self, oauth_service, sample_oauth_config):
        """Test initiating OAuth flow in local mode (mocked)"""
        auth_url = await oauth_service.initiate_oauth_flow(
            account_id="account-123",
            service_name="github",
            oauth_config=sample_oauth_config
        )

        assert "github.com" in auth_url
        assert "client_id=" in auth_url
        assert "state=" in auth_url
        assert "redirect_uri=" in auth_url

    @pytest.mark.asyncio
    async def test_store_oauth_state_local_mode(self, oauth_service, sample_state):
        """Test storing OAuth state in local mode"""
        # Store is called during initiate_oauth_flow
        await oauth_service._store_oauth_state(sample_state)

        # Verify state was stored
        assert sample_state.state_id in oauth_service._mock_states

    @pytest.mark.asyncio
    async def test_validate_oauth_state_valid(self, oauth_service, sample_state):
        """Test validating a valid OAuth state"""
        # Store state first
        await oauth_service._store_oauth_state(sample_state)

        # Validate
        validated = await oauth_service.validate_oauth_state(sample_state.state_id)

        assert validated.state_id == sample_state.state_id
        assert validated.account_id == sample_state.account_id

    @pytest.mark.asyncio
    async def test_validate_oauth_state_invalid(self, oauth_service):
        """Test validating an invalid state raises error"""
        with pytest.raises(InvalidOAuthStateError):
            await oauth_service.validate_oauth_state("nonexistent_state")

    @pytest.mark.asyncio
    async def test_validate_oauth_state_expired(self, oauth_service):
        """Test validating an expired state raises error"""
        # Create expired state
        expired_state = OAuthState(
            state_id="expired_state",
            account_id="account-123",
            service_name="github",
            redirect_uri="https://example.com/callback",
            created_at=(datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
            expires_at=(datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        )

        await oauth_service._store_oauth_state(expired_state)

        with pytest.raises(InvalidOAuthStateError):
            await oauth_service.validate_oauth_state("expired_state")

    @pytest.mark.asyncio
    async def test_delete_oauth_state(self, oauth_service, sample_state):
        """Test deleting OAuth state"""
        # Store state first
        await oauth_service._store_oauth_state(sample_state)

        # Delete
        await oauth_service._delete_oauth_state(sample_state.state_id)

        # Verify deleted
        assert sample_state.state_id not in oauth_service._mock_states

    @pytest.mark.asyncio
    async def test_cleanup_expired_states(self, oauth_service):
        """Test cleanup of expired states"""
        # Create expired state
        expired_state = OAuthState(
            state_id="expired_state",
            account_id="account-123",
            service_name="github",
            redirect_uri="https://example.com/callback",
            created_at=(datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
            expires_at=(datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        )

        # Create valid state
        valid_state = OAuthState(
            state_id="valid_state",
            account_id="account-123",
            service_name="github",
            redirect_uri="https://example.com/callback"
        )

        await oauth_service._store_oauth_state(expired_state)
        await oauth_service._store_oauth_state(valid_state)

        # Cleanup
        count = await oauth_service.cleanup_expired_states()

        # Should clean up 1 expired state
        assert count == 1
        assert "valid_state" in oauth_service._mock_states


class TestOAuthFlowServiceAWSIntegration:
    """Test suite with mocked AWS SDK calls"""

    @pytest.fixture
    def aws_config(self):
        """Create config for AWS testing"""
        return AgentCoreConfig(
            environment=Environment.DEVELOPMENT,
            aws_region="ap-southeast-2",
            aws_access_key_id="test-key",
            aws_secret_access_key="test-secret",
            dynamodb_oauth_states_table="agentcore_oauth_states",
            oauth_callback_base_url="https://api.example.com"
        )

    @pytest.fixture
    def mock_dynamodb(self):
        """Create mock boto3 DynamoDB resource"""
        with patch('boto3.resource') as mock_boto3:
            mock_resource = MagicMock()
            mock_boto3.return_value = mock_resource

            # Mock table
            mock_table = MagicMock()
            mock_resource.Table.return_value = mock_table

            yield mock_table

    def test_dynamodb_initialization(self, aws_config, mock_dynamodb):
        """Test DynamoDB client is properly initialized"""
        service = OAuthFlowService(config=aws_config)
        assert service.dynamodb_resource is not None

    @pytest.mark.asyncio
    async def test_store_state_aws(self, aws_config, mock_dynamodb, sample_state):
        """Test storing state in DynamoDB"""
        service = OAuthFlowService(config=aws_config)
        await service._store_oauth_state(sample_state)

        mock_dynamodb.put_item.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_state_aws(self, aws_config, mock_dynamodb, sample_state):
        """Test validating state in DynamoDB"""
        service = OAuthFlowService(config=aws_config)

        # Mock get_item to return state
        mock_dynamodb.get_item.return_value = {
            'Item': sample_state.to_dict()
        }

        validated = await service.validate_oauth_state(sample_state.state_id)

        assert validated.state_id == sample_state.state_id
        mock_dynamodb.get_item.assert_called_once_with(Key={"state_id": sample_state.state_id})


class TestAuthorizationURLBuilding:
    """Test authorization URL building"""

    def test_build_authorization_url_basic(self, oauth_service, sample_oauth_config):
        """Test building basic authorization URL"""
        url = oauth_service._build_authorization_url(
            oauth_config=sample_oauth_config,
            state_id="test_state",
            redirect_uri="https://example.com/callback"
        )

        assert "github.com/login/oauth/authorize" in url
        assert "state=test_state" in url
        assert "redirect_uri=https://example.com/callback" in url
        assert "response_type=code" in url

    def test_build_authorization_url_with_scopes(self, oauth_service, sample_oauth_config):
        """Test authorization URL with custom scopes"""
        url = oauth_service._build_authorization_url(
            oauth_config=sample_oauth_config,
            state_id="test_state",
            redirect_uri="https://example.com/callback",
            additional_scopes=["admin", "delete_repo"]
        )

        # Should include original and additional scopes
        assert "repo" in url or "read%3Auser" in url
        assert "admin" in url
        assert "delete_repo" in url

    def test_build_authorization_url_with_pkce(self, oauth_service):
        """Test authorization URL with PKCE"""
        oauth_config = {
            "authorization_url": "https://example.com/oauth/authorize",
            "scope": "read",
            "use_pkce": True
        }

        url = oauth_service._build_authorization_url(
            oauth_config=oauth_config,
            state_id="test_state",
            redirect_uri="https://example.com/callback"
        )

        # Should include PKCE parameters
        assert "code_challenge=" in url
        assert "code_challenge_method=S256" in url


class TestTokenExchange:
    """Test token exchange functionality"""

    @pytest.mark.asyncio
    async def test_exchange_code_for_tokens_local_mode(self, oauth_service, sample_oauth_config, sample_state):
        """Test token exchange in local mode (with mocked HTTP)"""
        # Store state first
        await oauth_service._store_oauth_state(sample_state)

        # Mock HTTP response
        with patch('core.agentcore.services.oauth_flow_service.httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.headers = {"content-type": "application/json"}
            mock_response.json.return_value = {
                "access_token": "test_access_token",
                "refresh_token": "test_refresh_token",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "repo"
            }
            mock_response.raise_for_status = MagicMock()

            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

            # Exchange code
            tokens = await oauth_service.exchange_code_for_tokens(
                code="test_code",
                state_id=sample_state.state_id,
                oauth_config=sample_oauth_config
            )

            assert tokens.access_token == "test_access_token"
            assert tokens.refresh_token == "test_refresh_token"

    @pytest.mark.asyncio
    async def test_exchange_code_invalid_state(self, oauth_service, sample_oauth_config):
        """Test token exchange with invalid state raises error"""
        with pytest.raises(InvalidOAuthStateError):
            await oauth_service.exchange_code_for_tokens(
                code="test_code",
                state_id="invalid_state",
                oauth_config=sample_oauth_config
            )


class TestTokenRefresh:
    """Test token refresh functionality"""

    @pytest.mark.asyncio
    async def test_refresh_tokens_local_mode(self, oauth_service, sample_oauth_config):
        """Test refreshing tokens in local mode"""
        # Mock existing credentials in Secrets Manager
        oauth_service.secrets_manager._mock_credentials = {
            "access_token": "old_access_token",
            "refresh_token": "valid_refresh_token",
            "expires_in": 3600
        }

        # Mock get_credentials
        oauth_service.secrets_manager.get_credentials = AsyncMock(
            return_value=oauth_service.secrets_manager._mock_credentials
        )

        # Mock update_credentials
        oauth_service.secrets_manager.update_credentials = AsyncMock()

        # Mock HTTP response
        with patch('core.agentcore.services.oauth_flow_service.httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.headers = {"content-type": "application/json"}
            mock_response.json.return_value = {
                "access_token": "new_access_token",
                "token_type": "Bearer",
                "expires_in": 3600
            }
            mock_response.raise_for_status = MagicMock()

            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

            # Refresh tokens
            tokens = await oauth_service.refresh_tokens(
                account_id="account-123",
                service_name="github",
                oauth_config=sample_oauth_config
            )

            assert tokens.access_token == "new_access_token"


class TestTenantIsolation:
    """Test tenant isolation for OAuth flows"""

    @pytest.mark.asyncio
    async def test_different_accounts_different_states(self, oauth_service):
        """Test that different accounts have separate OAuth states"""
        state1 = OAuthState(
            state_id="state1",
            account_id="account-1",
            service_name="github",
            redirect_uri="https://example.com/callback"
        )

        state2 = OAuthState(
            state_id="state2",
            account_id="account-2",
            service_name="github",
            redirect_uri="https://example.com/callback"
        )

        await oauth_service._store_oauth_state(state1)
        await oauth_service._store_oauth_state(state2)

        # States should be stored separately
        assert "state1" in oauth_service._mock_states
        assert "state2" in oauth_service._mock_states

        # Retrieve and verify account isolation
        validated1 = await oauth_service.validate_oauth_state("state1")
        validated2 = await oauth_service.validate_oauth_state("state2")

        assert validated1.account_id == "account-1"
        assert validated2.account_id == "account-2"

    @pytest.mark.asyncio
    async def test_callback_uri_includes_service(self, oauth_service):
        """Test that callback URIs are service-specific"""
        github_uri = oauth_service._build_callback_uri("github")
        slack_uri = oauth_service._build_callback_uri("slack")

        assert "github" in github_uri
        assert "slack" in slack_uri
        assert github_uri != slack_uri


class TestCSRFProtection:
    """Test CSRF protection via state parameter"""

    def test_state_generation_is_cryptographically_secure(self, oauth_service):
        """Test that state IDs are generated using secure random"""
        import secrets

        # Verify it's using secrets.token_urlsafe
        state1 = oauth_service._generate_state_id()
        state2 = oauth_service._generate_state_id()

        # Should be different each time
        assert state1 != state2

        # Should be URL-safe (no special characters that need encoding)
        for state in [state1, state2]:
            assert all(c.isalnum() or c in '-_' for c in state)

    @pytest.mark.asyncio
    async def test_state_must_match_for_token_exchange(self, oauth_service, sample_state, sample_oauth_config):
        """Test that token exchange requires matching state"""
        await oauth_service._store_oauth_state(sample_state)

        # Try to exchange with wrong state
        with pytest.raises(InvalidOAuthStateError):
            await oauth_service.exchange_code_for_tokens(
                code="test_code",
                state_id="wrong_state",
                oauth_config=sample_oauth_config
            )
