"""
AgentCore Migration Utilities

Utilities to help migrate from Daytona.io to AWS AgentCore Code Interpreter and Browser.
Provides database migration scripts and validation tools.
"""

import asyncio
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import json

from core.utils.logger import logger
from core.utils.config import config


@dataclass
class MigrationResult:
    """Result of a migration operation."""
    success: bool
    message: str
    migrated_projects: int = 0
    failed_projects: int = 0
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class AgentCoreMigrationUtils:
    """
    Utilities for migrating from Daytona.io to AWS AgentCore.
    
    Helps with:
    - Database schema updates
    - Project metadata migration
    - Configuration validation
    - Rollback capabilities
    """
    
    def __init__(self):
        self.region_name = getattr(config, 'AWS_REGION', 'us-east-1')
        self.code_interpreter_tool_id = getattr(config, 'AGENTCORE_CODE_INTERPRETER_TOOL_ID', None)
        self.browser_tool_id = getattr(config, 'AGENTCORE_BROWSER_TOOL_ID', None)
        
    def validate_agentcore_config(self) -> MigrationResult:
        """
        Validate that AgentCore configuration is properly set up.
        
        Returns:
            MigrationResult with validation status
        """
        errors = []
        
        # Check required AWS configuration
        if not self.region_name:
            errors.append("AWS_REGION not configured")
            
        # Check AgentCore tool IDs
        if not self.code_interpreter_tool_id:
            errors.append("AGENTCORE_CODE_INTERPRETER_TOOL_ID not configured")
            
        if not self.browser_tool_id:
            errors.append("AGENTCORE_BROWSER_TOOL_ID not configured")
            
        # Check execution role ARN
        execution_role_arn = getattr(config, 'AGENTCORE_EXECUTION_ROLE_ARN', None)
        if not execution_role_arn:
            errors.append("AGENTCORE_EXECUTION_ROLE_ARN not configured")
        
        # Check S3 bucket
        s3_bucket = getattr(config, 'AGENTCORE_S3_BUCKET', None)
        if not s3_bucket:
            errors.append("AGENTCORE_S3_BUCKET not configured")
        
        success = len(errors) == 0
        message = "AgentCore configuration is valid" if success else f"Configuration errors: {', '.join(errors)}"
        
        return MigrationResult(
            success=success,
            message=message,
            errors=errors
        )
    
    async def get_projects_with_daytona(self, db_client) -> List[Dict[str, Any]]:
        """
        Get all projects that have Daytona sandbox metadata.
        
        Args:
            db_client: Supabase database client
            
        Returns:
            List of project records with Daytona metadata
        """
        try:
            # Query projects with sandbox metadata (Daytona)
            response = await db_client.table('projects').select('*').neq('sandbox', None).execute()
            
            projects = response.data or []
            logger.info(f"Found {len(projects)} projects with Daytona sandbox metadata")
            
            return projects
            
        except Exception as e:
            logger.error(f"Failed to query projects with Daytona metadata: {e}")
            return []
    
    async def migrate_project_metadata(
        self, 
        db_client, 
        project_id: str,
        dry_run: bool = False
    ) -> MigrationResult:
        """
        Migrate a single project from Daytona to AgentCore metadata.
        
        Args:
            db_client: Supabase database client
            project_id: ID of the project to migrate
            dry_run: If True, don't actually update the database
            
        Returns:
            MigrationResult with migration status
        """
        try:
            # Get current project data
            response = await db_client.table('projects').select('*').eq('project_id', project_id).execute()
            
            if not response.data or len(response.data) == 0:
                return MigrationResult(
                    success=False,
                    message=f"Project {project_id} not found"
                )
            
            project = response.data[0]
            sandbox_info = project.get('sandbox', {})
            
            if not sandbox_info:
                return MigrationResult(
                    success=False,
                    message=f"Project {project_id} has no sandbox metadata to migrate"
                )
            
            # Prepare AgentCore metadata
            agentcore_metadata = {
                'migrated_from_daytona': True,
                'migration_timestamp': asyncio.get_event_loop().time(),
                'daytona_sandbox_id': sandbox_info.get('id'),
                'daytona_metadata': {
                    'pass': sandbox_info.get('pass'),
                    'vnc_preview': sandbox_info.get('vnc_preview'),
                    'sandbox_url': sandbox_info.get('sandbox_url'),
                    'token': sandbox_info.get('token')
                }
            }
            
            # Combine with existing AgentCore metadata if any
            existing_agentcore = project.get('agentcore', {})
            if existing_agentcore:
                agentcore_metadata.update(existing_agentcore)
            
            if dry_run:
                logger.info(f"DRY RUN: Would migrate project {project_id} to AgentCore metadata")
                return MigrationResult(
                    success=True,
                    message=f"DRY RUN: Project {project_id} migration validated"
                )
            
            # Update project with AgentCore metadata
            await db_client.table('projects').update({
                'agentcore': agentcore_metadata
            }).eq('project_id', project_id).execute()
            
            logger.info(f"Migrated project {project_id} from Daytona to AgentCore metadata")
            
            return MigrationResult(
                success=True,
                message=f"Project {project_id} migrated successfully"
            )
            
        except Exception as e:
            logger.error(f"Failed to migrate project {project_id}: {e}")
            return MigrationResult(
                success=False,
                message=f"Migration failed for project {project_id}: {str(e)}"
            )
    
    async def migrate_all_projects(
        self, 
        db_client,
        dry_run: bool = False,
        batch_size: int = 10
    ) -> MigrationResult:
        """
        Migrate all projects from Daytona to AgentCore metadata.
        
        Args:
            db_client: Supabase database client
            dry_run: If True, don't actually update the database
            batch_size: Number of projects to migrate in each batch
            
        Returns:
            MigrationResult with overall migration status
        """
        try:
            # Get all projects with Daytona metadata
            projects = await self.get_projects_with_daytona(db_client)
            
            if not projects:
                return MigrationResult(
                    success=True,
                    message="No projects with Daytona metadata found"
                )
            
            migrated_count = 0
            failed_count = 0
            errors = []
            
            # Process projects in batches
            for i in range(0, len(projects), batch_size):
                batch = projects[i:i + batch_size]
                logger.info(f"Processing batch {i//batch_size + 1} with {len(batch)} projects")
                
                for project in batch:
                    project_id = project['project_id']
                    
                    try:
                        result = await self.migrate_project_metadata(
                            db_client, 
                            project_id, 
                            dry_run
                        )
                        
                        if result.success:
                            migrated_count += 1
                        else:
                            failed_count += 1
                            errors.append(f"Project {project_id}: {result.message}")
                            
                    except Exception as e:
                        failed_count += 1
                        errors.append(f"Project {project_id}: {str(e)}")
                
                # Small delay between batches
                if not dry_run:
                    await asyncio.sleep(0.1)
            
            success = failed_count == 0
            message = f"Migration completed. {'DRY RUN: ' if dry_run else ''}Migrated: {migrated_count}, Failed: {failed_count}"
            
            return MigrationResult(
                success=success,
                message=message,
                migrated_projects=migrated_count,
                failed_projects=failed_count,
                errors=errors
            )
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            return MigrationResult(
                success=False,
                message=f"Migration failed: {str(e)}"
            )
    
    async def rollback_project_migration(
        self, 
        db_client, 
        project_id: str
    ) -> MigrationResult:
        """
        Rollback migration for a specific project.
        
        Args:
            db_client: Supabase database client
            project_id: ID of the project to rollback
            
        Returns:
            MigrationResult with rollback status
        """
        try:
            # Get current project data
            response = await db_client.table('projects').select('*').eq('project_id', project_id).execute()
            
            if not response.data or len(response.data) == 0:
                return MigrationResult(
                    success=False,
                    message=f"Project {project_id} not found"
                )
            
            project = response.data[0]
            agentcore_metadata = project.get('agentcore', {})
            
            if not agentcore_metadata.get('migrated_from_daytona'):
                return MigrationResult(
                    success=False,
                    message=f"Project {project_id} was not migrated from Daytona"
                )
            
            # Clear AgentCore metadata
            await db_client.table('projects').update({
                'agentcore': None
            }).eq('project_id', project_id).execute()
            
            logger.info(f"Rolled back migration for project {project_id}")
            
            return MigrationResult(
                success=True,
                message=f"Project {project_id} rollback completed"
            )
            
        except Exception as e:
            logger.error(f"Failed to rollback project {project_id}: {e}")
            return MigrationResult(
                success=False,
                message=f"Rollback failed for project {project_id}: {str(e)}"
            )
    
    async def get_migration_status(self, db_client) -> Dict[str, Any]:
        """
        Get overall migration status.
        
        Args:
            db_client: Supabase database client
            
        Returns:
            Dictionary with migration status information
        """
        try:
            # Get total projects
            total_response = await db_client.table('projects').select('project_id', count='exact').execute()
            total_projects = total_response.count or 0
            
            # Get projects with Daytona metadata
            daytona_projects = await self.get_projects_with_daytona(db_client)
            
            # Get projects with AgentCore metadata
            agentcore_response = await db_client.table('projects').select('*', count='exact').neq('agentcore', None).execute()
            agentcore_projects = agentcore_response.count or 0
            
            # Get migrated projects
            migrated_response = await db_client.table('projects').select('*', count='exact').eq('agentcore->>migrated_from_daytona', 'true').execute()
            migrated_projects = migrated_response.count or 0
            
            status = {
                'total_projects': total_projects,
                'daytona_projects': len(daytona_projects),
                'agentcore_projects': agentcore_projects,
                'migrated_projects': migrated_projects,
                'pending_migration': len(daytona_projects) - migrated_projects,
                'migration_percentage': (migrated_projects / len(daytona_projects) * 100) if daytona_projects else 0,
                'agentcore_config': {
                    'code_interpreter_configured': bool(self.code_interpreter_tool_id),
                    'browser_configured': bool(self.browser_tool_id),
                    'region': self.region_name
                }
            }
            
            return status
            
        except Exception as e:
            logger.error(f"Failed to get migration status: {e}")
            return {
                'error': str(e)
            }
    
    def generate_migration_script(self) -> str:
        """
        Generate a SQL script for database schema updates.
        
        Returns:
            SQL script as string
        """
        script = """
-- AgentCore Migration Script
-- Add AgentCore metadata column to projects table if it doesn't exist

DO $$ 
BEGIN
    -- Check if agentcore column exists
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'projects' AND column_name = 'agentcore'
    ) THEN
        -- Add agentcore column
        ALTER TABLE projects ADD COLUMN agentcore JSONB;
        
        -- Add index for better performance
        CREATE INDEX idx_projects_agentcore ON projects USING gin(agentcore);
        
        RAISE NOTICE 'Added agentcore column to projects table';
    ELSE
        RAISE NOTICE 'agentcore column already exists in projects table';
    END IF;
END $$;

-- Optional: Create a migration history table
CREATE TABLE IF NOT EXISTS migration_history (
    id SERIAL PRIMARY KEY,
    migration_name VARCHAR(255) NOT NULL,
    migration_timestamp TIMESTAMP DEFAULT NOW(),
    status VARCHAR(50) NOT NULL,
    details JSONB
);

-- Record this migration
INSERT INTO migration_history (migration_name, status, details) 
VALUES (
    'agentcore_migration_setup',
    'completed',
    '{"agentcore_column_added": true}'::jsonb
) ON CONFLICT DO NOTHING;
"""
        return script.strip()


# Utility functions for easy access
async def validate_agentcore_setup() -> MigrationResult:
    """Validate AgentCore configuration."""
    utils = AgentCoreMigrationUtils()
    return utils.validate_agentcore_config()

async def get_migration_overview(db_client) -> Dict[str, Any]:
    """Get overview of migration status."""
    utils = AgentCoreMigrationUtils()
    return await utils.get_migration_status(db_client)

async def run_migration(
    db_client, 
    dry_run: bool = False,
    batch_size: int = 10
) -> MigrationResult:
    """Run full migration from Daytona to AgentCore."""
    utils = AgentCoreMigrationUtils()
    return await utils.migrate_all_projects(db_client, dry_run, batch_size)
