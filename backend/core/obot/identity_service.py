"""Obot Identity Service

Manages Suna-to-Obot user identity mapping and token management.
"""

import os
import hashlib
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import logging
import jwt
from cryptography.fernet import Fernet

from .client import ObotClient, ObotClientError
from .models import ObotUserMapping


logger = logging.getLogger(__name__)


class IdentityServiceError(Exception):
    """Base exception for identity service errors"""
    pass


class ObotIdentityService:
    """Manages Suna-to-Obot user identity mapping"""
    
    def __init__(
        self,
        db_connection,
        obot_client: ObotClient,
        jwt_secret: Optional[str] = None,
        token_encryption_key: Optional[str] = None
    ):
        """Initialize identity service
        
        Args:
            db_connection: Database connection for storing mappings
            obot_client: Obot client for API communication
            jwt_secret: Secret for signing JWT tokens
            token_encryption_key: Key for encrypting cached tokens
        """
        self.db = db_connection
        self.obot_client = obot_client
        self.jwt_secret = jwt_secret or os.getenv("OBOT_JWT_SECRET", "default-secret-change-in-production")
        self.token_encryption_key = token_encryption_key or os.getenv("OBOT_TOKEN_ENCRYPTION_KEY")
        
        # Initialize token encryption if key is available
        if self.token_encryption_key:
            try:
                self.fernet = Fernet(self.token_encryption_key.encode())
            except Exception as e:
                logger.warning(f"Failed to initialize token encryption: {e}")
                self.fernet = None
        else:
            self.fernet = None
        
        logger.debug("Initialized ObotIdentityService")
    
    def _encrypt_token(self, token: str) -> str:
        """Encrypt a token for storage"""
        if not self.fernet:
            return token  # Return unencrypted if encryption not available
        
        try:
            return self.fernet.encrypt(token.encode()).decode()
        except Exception as e:
            logger.warning(f"Failed to encrypt token: {e}")
            return token
    
    def _decrypt_token(self, encrypted_token: str) -> str:
        """Decrypt a stored token"""
        if not self.fernet:
            return encrypted_token  # Return as-is if encryption not available
        
        try:
            return self.fernet.decrypt(encrypted_token.encode()).decode()
        except Exception as e:
            logger.warning(f"Failed to decrypt token: {e}")
            return encrypted_token
    
    def _generate_jwt_token(self, user_id: str, email: Optional[str] = None) -> str:
        """Generate JWT token for Obot user"""
        payload = {
            "sub": user_id,
            "email": email,
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(hours=24),  # 24 hour expiry
            "iss": "suna-platform"
        }
        
        try:
            return jwt.encode(payload, self.jwt_secret, algorithm="HS256")
        except Exception as e:
            logger.error(f"Failed to generate JWT token: {e}")
            raise IdentityServiceError(f"JWT generation failed: {e}")
    
    def _verify_jwt_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("JWT token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid JWT token: {e}")
            return None
    
    def generate_obot_username(self, suna_user_id: str, email: Optional[str] = None) -> str:
        """Generate deterministic Obot username from Suna user data
        
        Args:
            suna_user_id: Suna user UUID
            email: Optional user email
            
        Returns:
            Obot username in format: suna_{hash}
        """
        # Create hash from user ID (deterministic)
        hash_input = f"{suna_user_id}:{email or ''}"
        hash_bytes = hashlib.sha256(hash_input.encode()).hexdigest()
        username = f"suna_{hash_bytes[:12]}"  # Use first 12 chars
        
        logger.debug(f"Generated Obot username '{username}' for Suna user {suna_user_id}")
        return username
    
    async def get_or_create_obot_user(self, suna_user_id: str, email: Optional[str] = None) -> ObotUserMapping:
        """Get existing Obot user mapping or create new Obot user
        
        Args:
            suna_user_id: Suna user UUID
            email: Optional user email for account creation
            
        Returns:
            ObotUserMapping with user details and token
            
        Raises:
            IdentityServiceError: On mapping creation failure
        """
        try:
            # Check if mapping already exists
            existing_mapping = await self._get_existing_mapping(suna_user_id)
            if existing_mapping:
                logger.debug(f"Found existing mapping for Suna user {suna_user_id}")
                return existing_mapping
            
            # Create new mapping
            logger.info(f"Creating new Obot user mapping for Suna user {suna_user_id}")
            return await self._create_new_mapping(suna_user_id, email)
            
        except Exception as e:
            logger.error(f"Failed to get/create Obot user mapping: {e}")
            raise IdentityServiceError(f"User mapping failed: {e}")
    
    async def get_obot_token(self, suna_user_id: str) -> str:
        """Get valid Obot API token for a Suna user
        
        Args:
            suna_user_id: Suna user UUID
            
        Returns:
            Valid Obot API token
            
        Raises:
            IdentityServiceError: On token retrieval failure
        """
        try:
            # Get user mapping
            mapping = await self.get_or_create_obot_user(suna_user_id)
            
            # Check if cached token is still valid
            if mapping.token_expires_at and mapping.token_expires_at > datetime.utcnow():
                logger.debug(f"Using cached token for Suna user {suna_user_id}")
                return self._decrypt_token(mapping.cached_token) if mapping.cached_token else ""
            
            # Refresh token via Obot API
            logger.debug(f"Refreshing token for Suna user {suna_user_id}")
            new_token = await self.obot_client.get_token_for_user(mapping.obot_user_id)
            
            # Update cached token
            await self._update_cached_token(suna_user_id, new_token)
            
            return new_token
            
        except Exception as e:
            logger.error(f"Failed to get Obot token for user {suna_user_id}: {e}")
            raise IdentityServiceError(f"Token retrieval failed: {e}")
    
    async def delete_obot_user(self, suna_user_id: str) -> bool:
        """Delete Obot user when Suna user is deleted
        
        Args:
            suna_user_id: Suna user UUID
            
        Returns:
            True if deletion was successful
            
        Raises:
            IdentityServiceError: On deletion failure
        """
        try:
            # Get user mapping
            mapping = await self._get_existing_mapping(suna_user_id)
            if not mapping:
                logger.warning(f"No mapping found for Suna user {suna_user_id}")
                return False
            
            # Delete Obot user via API (if supported by Obot)
            try:
                # Note: This would require an Obot API endpoint for user deletion
                # For now, we just remove the local mapping
                logger.info(f"Would delete Obot user {mapping.obot_user_id} (API not implemented)")
                
            except Exception as e:
                logger.warning(f"Failed to delete Obot user via API: {e}")
            
            # Remove mapping from database
            await self._delete_mapping(suna_user_id)
            
            logger.info(f"Deleted Obot user mapping for Suna user {suna_user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete Obot user mapping: {e}")
            raise IdentityServiceError(f"User deletion failed: {e}")
    
    async def _get_existing_mapping(self, suna_user_id: str) -> Optional[ObotUserMapping]:
        """Get existing user mapping from database"""
        try:
            # This would be implemented with actual database queries
            # For now, return None to force creation
            return None
            
        except Exception as e:
            logger.error(f"Failed to query existing mapping: {e}")
            return None
    
    async def _create_new_mapping(self, suna_user_id: str, email: Optional[str] = None) -> ObotUserMapping:
        """Create new Obot user and mapping"""
        try:
            # Generate Obot username
            username = self.generate_obot_username(suna_user_id, email)
            
            # Create Obot user via API (this would need to be implemented)
            obot_user_id = await self._create_obot_user(username, email)
            
            # Get initial token
            initial_token = await self.obot_client.get_token_for_user(obot_user_id)
            
            # Create mapping record
            mapping_data = {
                "suna_user_id": suna_user_id,
                "obot_user_id": obot_user_id,
                "obot_username": username,
                "cached_token": self._encrypt_token(initial_token),
                "token_expires_at": datetime.utcnow() + timedelta(hours=24),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            # Store in database
            mapping = await self._store_mapping(mapping_data)
            
            logger.info(f"Created Obot user mapping: {mapping.id}")
            return mapping
            
        except Exception as e:
            logger.error(f"Failed to create new mapping: {e}")
            raise
    
    async def _create_obot_user(self, username: str, email: Optional[str] = None) -> str:
        """Create user in Obot system"""
        try:
            # This would require implementing a user creation endpoint in Obot
            # For now, use the username as the user ID (simplified)
            # In reality, this would call Obot's user management API
            
            logger.debug(f"Creating Obot user: {username}")
            
            # Generate a deterministic user ID based on username
            user_id_hash = hashlib.sha256(username.encode()).hexdigest()[:16]
            return f"obot_user_{user_id_hash}"
            
        except Exception as e:
            logger.error(f"Failed to create Obot user: {e}")
            raise IdentityServiceError(f"Obot user creation failed: {e}")
    
    async def _store_mapping(self, mapping_data: Dict[str, Any]) -> ObotUserMapping:
        """Store mapping in database"""
        try:
            # This would be implemented with actual database insert
            # For now, return a mock mapping
            return ObotUserMapping(
                id="mock-id",
                suna_user_id=mapping_data["suna_user_id"],
                obot_user_id=mapping_data["obot_user_id"],
                obot_username=mapping_data["obot_username"],
                token_expires_at=mapping_data["token_expires_at"],
                created_at=mapping_data["created_at"],
                updated_at=mapping_data["updated_at"]
            )
            
        except Exception as e:
            logger.error(f"Failed to store mapping: {e}")
            raise
    
    async def _update_cached_token(self, suna_user_id: str, new_token: str) -> None:
        """Update cached token in database"""
        try:
            # This would be implemented with actual database update
            # For now, just log the action
            logger.debug(f"Would update cached token for user {suna_user_id}")
            
        except Exception as e:
            logger.error(f"Failed to update cached token: {e}")
            raise
    
    async def _delete_mapping(self, suna_user_id: str) -> None:
        """Delete mapping from database"""
        try:
            # This would be implemented with actual database delete
            # For now, just log the action
            logger.debug(f"Would delete mapping for user {suna_user_id}")
            
        except Exception as e:
            logger.error(f"Failed to delete mapping: {e}")
            raise
    
    async def health_check(self) -> bool:
        """Check if identity service is healthy"""
        try:
            # Test Obot client health
            await self.obot_client.check_health()
            
            # Test database connection (would be implemented)
            # await self.db.ping()
            
            return True
            
        except Exception as e:
            logger.error(f"Identity service health check failed: {e}")
            return False


def create_identity_service(db_connection, obot_client: Optional[ObotClient] = None) -> ObotIdentityService:
    """Create identity service with configuration from environment
    
    Args:
        db_connection: Database connection
        obot_client: Optional Obot client (created from env if not provided)
        
    Returns:
        Configured ObotIdentityService instance
        
    Raises:
        ValueError: If required configuration is missing
    """
    if obot_client is None:
        from .client import create_obot_client
        obot_client = create_obot_client()
    
    return ObotIdentityService(
        db_connection=db_connection,
        obot_client=obot_client
    )
