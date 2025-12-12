"""Obot Profile Service

Manages Obot MCP profiles stored in Suna's Supabase database.
Provides CRUD operations for user MCP server connections with proper tenant isolation.
"""

import json
import hashlib
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from uuid import uuid4

from core.services.supabase import DBConnection
from core.utils.logger import logger
from .models import ObotProfile


class ObotProfileService:
    """Manages Obot MCP profiles in Suna's database"""
    
    def __init__(self, db_connection: Optional[DBConnection] = None):
        self.db = db_connection or DBConnection()
    
    def _build_profile_from_row(self, row: Dict[str, Any]) -> ObotProfile:
        """Convert database row to ObotProfile model"""
        return ObotProfile(
            id=row['id'],
            account_id=row['account_id'],
            obot_server_id=row['obot_server_id'],
            catalog_entry_id=row['catalog_entry_id'],
            display_name=row['display_name'],
            icon_url=row.get('icon_url'),
            status=row.get('status', 'pending'),
            created_at=datetime.fromisoformat(row['created_at'].replace('Z', '+00:00')) if row.get('created_at') else None,
            updated_at=datetime.fromisoformat(row['updated_at'].replace('Z', '+00:00')) if row.get('updated_at') else None
        )
    
    async def _generate_unique_display_name(
        self, 
        base_name: str, 
        account_id: str, 
        client
    ) -> str:
        """Generate a unique display name for the profile"""
        original_name = base_name
        counter = 1
        current_name = base_name
        
        while True:
            existing = await client.table('obot_profiles').select('id').eq(
                'account_id', account_id
            ).eq('display_name', current_name).execute()
            
            if not existing.data:
                return current_name
            
            counter += 1
            current_name = f"{original_name} ({counter})"
    
    async def create_profile(
        self,
        account_id: str,
        obot_server_id: str,
        catalog_entry_id: str,
        display_name: str,
        icon_url: Optional[str] = None
    ) -> ObotProfile:
        """
        Create a new Obot profile record
        
        Args:
            account_id: Suna user/account ID
            obot_server_id: Obot MCP server ID
            catalog_entry_id: Original catalog entry ID
            display_name: User-friendly display name
            icon_url: Optional icon URL for UI
            
        Returns:
            Created ObotProfile instance
            
        Raises:
            Exception: If profile creation fails
        """
        try:
            logger.debug(f"Creating Obot profile for user: {account_id}, server: {obot_server_id}")
            
            client = await self.db.client
            
            # Generate unique display name if needed
            unique_display_name = await self._generate_unique_display_name(
                display_name, account_id, client
            )
            
            if unique_display_name != display_name:
                logger.debug(f"Generated unique display name: {unique_display_name} (original: {display_name})")
            
            profile_id = str(uuid4())
            now = datetime.now(timezone.utc)
            
            # Insert into obot_profiles table
            result = await client.table('obot_profiles').insert({
                'id': profile_id,
                'account_id': account_id,
                'obot_server_id': obot_server_id,
                'catalog_entry_id': catalog_entry_id,
                'display_name': unique_display_name,
                'icon_url': icon_url,
                'status': 'pending',
                'created_at': now.isoformat(),
                'updated_at': now.isoformat()
            }).execute()
            
            if not result.data:
                raise Exception("Failed to create Obot profile in database")
            
            logger.debug(f"Successfully created Obot profile: {profile_id}")
            
            # Return the created profile
            return ObotProfile(
                id=profile_id,
                account_id=account_id,
                obot_server_id=obot_server_id,
                catalog_entry_id=catalog_entry_id,
                display_name=unique_display_name,
                icon_url=icon_url,
                status='pending',
                created_at=now,
                updated_at=now
            )
            
        except Exception as e:
            logger.error(f"Failed to create Obot profile: {e}", exc_info=True)
            raise
    
    async def get_profiles(self, account_id: str) -> List[ObotProfile]:
        """
        Get all profiles for a user
        
        Args:
            account_id: Suna user/account ID
            
        Returns:
            List of ObotProfile instances for the user
            
        Raises:
            Exception: If database query fails
        """
        try:
            logger.debug(f"Getting Obot profiles for user: {account_id}")
            
            client = await self.db.client
            
            # Query obot_profiles table with RLS - only return profiles for this user
            result = await client.table('obot_profiles').select('*').eq(
                'account_id', account_id
            ).order('created_at', desc=True).execute()
            
            profiles = []
            for row in result.data:
                profiles.append(self._build_profile_from_row(row))
            
            logger.debug(f"Found {len(profiles)} Obot profiles for user {account_id}")
            return profiles
            
        except Exception as e:
            logger.error(f"Failed to get Obot profiles: {e}", exc_info=True)
            raise
    
    async def get_profile(self, profile_id: str, account_id: str) -> Optional[ObotProfile]:
        """
        Get a specific profile with ownership check
        
        Args:
            profile_id: Profile ID to retrieve
            account_id: Account ID for ownership verification
            
        Returns:
            ObotProfile if found and owned by user, None otherwise
            
        Raises:
            Exception: If database query fails
        """
        try:
            logger.debug(f"Getting Obot profile: {profile_id} for user: {account_id}")
            
            client = await self.db.client
            
            # Query with ownership check - RLS will also enforce this
            result = await client.table('obot_profiles').select('*').eq(
                'id', profile_id
            ).eq('account_id', account_id).execute()
            
            if not result.data:
                logger.debug(f"Obot profile {profile_id} not found or not owned by user {account_id}")
                return None
            
            profile = self._build_profile_from_row(result.data[0])
            logger.debug(f"Successfully retrieved Obot profile: {profile_id}")
            return profile
            
        except Exception as e:
            logger.error(f"Failed to get Obot profile {profile_id}: {e}", exc_info=True)
            raise
    
    async def delete_profile(self, profile_id: str, account_id: str) -> bool:
        """
        Delete a profile with ownership check
        
        Args:
            profile_id: Profile ID to delete
            account_id: Account ID for ownership verification
            
        Returns:
            True if profile was deleted, False if not found
            
        Raises:
            Exception: If database operation fails
        """
        try:
            logger.debug(f"Deleting Obot profile: {profile_id} for user: {account_id}")
            
            client = await self.db.client
            
            # First verify ownership
            profile = await self.get_profile(profile_id, account_id)
            if not profile:
                logger.debug(f"Obot profile {profile_id} not found or not owned by user {account_id}")
                return False
            
            # Delete the profile (RLS ensures only owner's data is deleted)
            result = await client.table('obot_profiles').delete().eq(
                'id', profile_id
            ).eq('account_id', account_id).execute()
            
            if result.data:
                logger.debug(f"Successfully deleted Obot profile: {profile_id}")
                return True
            else:
                logger.warning(f"Failed to delete Obot profile: {profile_id}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to delete Obot profile {profile_id}: {e}", exc_info=True)
            raise
    
    async def update_profile_status(self, profile_id: str, status: str) -> None:
        """
        Update profile connection status
        
        Args:
            profile_id: Profile ID to update
            status: New status ('pending', 'connected', 'error', 'oauth_required')
            
        Raises:
            Exception: If update fails
        """
        try:
            logger.debug(f"Updating Obot profile {profile_id} status to: {status}")
            
            client = await self.db.client
            now = datetime.now(timezone.utc)
            
            # Update status with timestamp
            result = await client.table('obot_profiles').update({
                'status': status,
                'updated_at': now.isoformat()
            }).eq('id', profile_id).execute()
            
            if not result.data:
                raise Exception(f"Failed to update profile status for {profile_id}")
            
            logger.debug(f"Successfully updated Obot profile {profile_id} status to {status}")
            
        except Exception as e:
            logger.error(f"Failed to update profile status for {profile_id}: {e}", exc_info=True)
            raise
    
    async def get_profile_by_server_id(self, account_id: str, obot_server_id: str) -> Optional[ObotProfile]:
        """
        Get profile by Obot server ID with ownership check
        
        Args:
            account_id: Account ID for ownership verification
            obot_server_id: Obot server ID to look up
            
        Returns:
            ObotProfile if found, None otherwise
            
        Raises:
            Exception: If database query fails
        """
        try:
            logger.debug(f"Getting Obot profile by server ID: {obot_server_id} for user: {account_id}")
            
            client = await self.db.client
            
            # Query by server ID with ownership check
            result = await client.table('obot_profiles').select('*').eq(
                'account_id', account_id
            ).eq('obot_server_id', obot_server_id).execute()
            
            if not result.data:
                logger.debug(f"No Obot profile found for server {obot_server_id} owned by user {account_id}")
                return None
            
            profile = self._build_profile_from_row(result.data[0])
            logger.debug(f"Found Obot profile for server {obot_server_id}: {profile.id}")
            return profile
            
        except Exception as e:
            logger.error(f"Failed to get Obot profile by server ID {obot_server_id}: {e}", exc_info=True)
            raise
    
    async def update_profile_display_name(self, profile_id: str, account_id: str, new_display_name: str) -> Optional[ObotProfile]:
        """
        Update profile display name with uniqueness check
        
        Args:
            profile_id: Profile ID to update
            account_id: Account ID for ownership verification
            new_display_name: New display name
            
        Returns:
            Updated ObotProfile if successful, None if not found
            
        Raises:
            Exception: If update fails
        """
        try:
            logger.debug(f"Updating display name for Obot profile {profile_id} to: {new_display_name}")
            
            client = await self.db.client
            
            # Verify ownership first
            profile = await self.get_profile(profile_id, account_id)
            if not profile:
                logger.debug(f"Obot profile {profile_id} not found or not owned by user {account_id}")
                return None
            
            # Generate unique name if needed
            unique_display_name = await self._generate_unique_display_name(
                new_display_name, account_id, client
            )
            
            now = datetime.now(timezone.utc)
            
            # Update display name
            result = await client.table('obot_profiles').update({
                'display_name': unique_display_name,
                'updated_at': now.isoformat()
            }).eq('id', profile_id).eq('account_id', account_id).execute()
            
            if not result.data:
                raise Exception(f"Failed to update display name for profile {profile_id}")
            
            # Return updated profile
            updated_profile = await self.get_profile(profile_id, account_id)
            logger.debug(f"Successfully updated display name for Obot profile {profile_id}")
            return updated_profile
            
        except Exception as e:
            logger.error(f"Failed to update display name for Obot profile {profile_id}: {e}", exc_info=True)
            raise
