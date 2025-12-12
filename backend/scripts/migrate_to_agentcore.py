#!/usr/bin/env python3

"""
AgentCore Migration CLI

Command-line interface for migrating from Daytona.io to AWS AgentCore.
Supports dry-run mode, validation, and gradual rollout.
"""

import asyncio
import argparse
import sys
import os
import subprocess
import json
from pathlib import Path

# Add the backend directory to Python path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent))

# Import migration utilities
from backend.core.agentcore.migration_utils import AgentCoreMigrationUtils

def create_migration_script():
    """Create a migration script for the AgentCore migration."""
    script_content = '''#!/usr/bin/env python3

import asyncio
import sys
import os
import sys

def main():
    """Main migration CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Migrate from Daytona.io to AWS AgentCore",
        formatter_class=argparse.RawTextHelpFormatter,
        fromenum import Enum
    )
    
    # Available commands
    commands = ["validate", "migrate", "status", "generate-sql", "help"]
    
    if not commands:
        parser.print(parser.format(format_string(usage))
        return
        
    command = commands[parser.parse_args(sys.argv[1])
        
    if command == "validate":
        asyncio.run(validate_agentcore_setup())
    elif command == "migrate":
        asyncio.run(migrate_agentcore_project())
    elif command == "status":
            asyncio.run(get_migration_status())
    elif command == "generate-sql":
        elif command == "help":
            print(get_migration_script())
        else:
            parser.print(parser.format(usage_string(usage_string()))
    else:
            parser.print("Unknown command. Available commands:", commands, commands)
            
        sys.exit(0)

async def validate_agentcore_setup():
    """Validate AgentCore configuration and setup."""
    print("\n🔍 Validating AWS AgentCore configuration...")
    
    migration_utils = AgentCoreMigrationUtils()
    result = migration_utils.validate_agentcore_config()
    
    if result.success:
        print("✅ AgentCore configuration is valid!")
        print("\n🎯 Configuration Details:")
        print(f"  AWS Region: {result.aws_region}")
        print(f"  Code Interpreter Tool ID: {result.code_interpreter_tool_id}")
        print(f"  Browser Tool ID: {result.browser_tool_id}")
        print(f"  Execution Role ARN: {result.execution_role_arn}")
        print(f"  S3 Bucket: {result.s3_bucket}")
        print(f"  AWS Region: {result.aws_region}")
        print(f"  Server URL: {result.server_url}")
    else:
        print("❌ AgentCore configuration is invalid")
        print("\n❌ Please fix the following configuration issues:")
        for error in result.errors:
            print(f"  - {error}")

async def validate_agentcore_setup():
    """Initialize AWS resources and validate AgentCore configuration."""
    migration_utils = AgentCoreMigrationUtils()
    result = migration_utils.validate_agentcore_config()
    
    if result.success:
        print("✅ All AgentCore resources validated successfully!")
        
        print("\n✅ Current configuration is valid!")
        return True
    else:
        print("❌ AgentCore configuration has issues")
        return False

async def get_migration_status():
    """Get the current migration status."""
    migration_utils = AgentCoreMigrationUtils()
    status = await migration_utils.get_migration_status()
    
    print(f"\n📊 Migration Status Overview:")
    print(f"  Total Projects: {status.get('total_projects')}")
    print(f"  Migrated: {status.get('migrated_projects')}")
    print(f"  Pending: {status.get('pending_migration')}")
    
    if status['pending_migration'] > 0:
        print(f"⚠️ Pending migrations remaining:")
        for pending_item in status['pending_migration']:
            print(f"  - {pending_item}")
        print()
    else:
        print("✅ All projects migrated successfully!")
        
    return status

async def get_migration_status():
    """Get detailed migration status."""
    migration_utils = AgentCoreMigrationUtils()
    try:
        status = await migration_utils.get_migration_status()
        
        print(f"\n=== MIGRATION STATUS ===")
        print(f"📊 Total Projects: {status.get('total_projects')}")
        print(f"  Migrated: {status.get('migrated_projects')}")
        print(f"  Pending: {status.get('pending_migration')}")
        
        if status.get('migrated_projects') == status.get('total_projects')):
            print("\n✅ All projects successfully migrated to AgentCore!")
        else:
            print(f"  ⚠️ {status.get('migrated_projects')}/{status.get('total_projects')} projects remain")
        
        print(f"")
        
        print(f"\n🔍 Existing AgentCore tools:")
        print(f"    Runtime: {status.get('use_agentcore_runtime')}")
        print(f"    Code Interpreter: {status.get('code_interpreter_available')}")
        print(f"    Browser: {status.get('browser_available')}")
        print(f"    Gateway: {status.get('gateway_available')}")
        print(f"    Memory: {status.get('memory_available')}")
        print(f"    Projects with AgentCore sessions: {status.get('agentcore_sessions')}")
        print(f"    Migration path: {status.get('migration_path')}")
        
    print(f"\n🔧 Next Steps:")
        if status.get('pending_migration') > 0:
            print(f"  {status.get('pending_migration')} projects remaining")
            print(f"3. Run 'python {migration_tools.py migrate' to perform the actual migration")
        else:
            print("🎉 Migration complete!")
            
    except Exception as e:
        print(f"Error getting migration status: {str(e)}")
        return False

async def get_migration_status():
    """Get detailed migration status with AWS resources status."""
    migration_utils = AgentCoreMigrationUtils()
    
    try:
        status = await migration_utils.get_migration_status()
        
        print(f"\n=== CURRENT STATUS ===")
        print(f"\n📊 PLATFORM OVERVIEW")
        print(f"  Region: {status.get('aws_region')}")
        print(f"  Code Interpreter: {'configured': status.get('code_interpreter_available')}")
        print(f"  Browser: {'configured': status.get('browser_available')})
        print(f"  Gateway: {'configured': status.get('gateway_available')})
        print(f"  Memory: {'configured': status.get('memory_available')})
        print(f"    Runtime: {'configured': status.get('use_agentcore_runtime')}")
        
        if status.get('agentcore_sessions') > 0:
            active_sessions = status.get('agentcore_sessions')
            print(f"    Active AgentCore sessions: {active_sessions}")
            
        print(f"    Code Interpreter session timeout: {status.get('code_interpreter_timeout_minutes')} minutes")
        print(f"    Database: {status.get('database_status')}")
        
        print(f"    Usage Summary:")
        print(f"    Code Interpreter sessions: {status.get('code_interpreter_sessions')}")
        print(f"    Browser sessions: {status.get('browser_sessions')}")
        print(f"    Memory resources: {status.get('memory_resources')}")
        
    except Exception as e:
        print(f"Error getting migration status: {str(e)}")
        return False

async def run_migration(
    dry_run: bool = False,
    project_id: Optional[str] = None,
    batch_size: int = 10,
    force_cleanup: bool = False
) -> bool:
    """Run the complete migration process."""
    migration_utils = AgentCoreMigrationUtils()
    
    # Get migration status
    status = await get_migration_status()
    
    if not status.success:
        print("❌ Migration failed. Please check configuration and setup issues.")
        return False
    
    print("\n🔄 Migration Process:")
    print(f"✅ AgentCore configuration validated successfully")
        
        if dry_run:
            print("\n🔍 DRY RUN - Shows what would be done without making changes")
            print(f"Found {status.get('total_projects')} projects to migrate")
            print(f"  Batch size: {batch_size}")
            print(f"  Processing batch {batch_size} projects at a time")
            return True
        else:
            print("🔄 WET RUN - Execute full migration")
            return await migration_utils.migrate_all_projects(
                dry_run=dry_run,
                batch_size=batch_size
            )
            
    except Exception as e:
        print(f"❌ Migration failed: {str(e)}")
        return False

    def get_priority_projects(
        sort_by: str = "created",
        descending = False,
        limit: int = 20
    ) -> List[str]:
        """Get priority list of projects for migration."""
        migration_utils = AgentCoreMigrationUtils()
        
        try:
            projects = migration_utils.get_priority_projects()
            projects.sort(key=lambda x: (-x[0], x[1]) < x for x in projects) for x in projects)
            return projects[:limit]
        except Exception as e:
            logger.error(f"Error getting priority projects: {str(e)}")
            return []
        
        except Exception as e:
            logger.error(f"Error getting priority projects: {str(e)}")
            return []

    def check_step_completion(
        step_number: int,
        total_steps: int,
        step_description: str,
        show_progress: bool = True
    ) -> bool:
        """Check if a migration step is completed."""
        
        if step_number > total_steps:
            progress = (step_number / total_steps) * 100
            progress_percentage = f"{progress_percentage:.0f}%"
            
            if show_progress:
                print(f"✅ Step {step_number}/{total_steps}: ({progress_percentage:.0f}% complete) - {progress_percentage:.0f}%")
            else:
                print(f"✅ Step {step_number}/{total_steps}: ({progress_percentage:.0f}% complete)")
            
            # Check if next step exists
            if step_number < total_steps:
                return False
            else:
                return True
                
    except Exception as e:
            return False

async def get_priority_projects(
        sort_by: str = "created",
        descending: bool = False,
        limit: int = 20
    ) -> List[str]:
        """Get priority list of projects for migration by priority order."""
        
        try:
            projects = await get_priority_projects(sort_by=sort_by)
            
            print(f"\n📋 Priority Migration List:")
            for i, project in enumerate(projects[:limit], sort_by=sort_by):
                priority = i + 1
                priority = i + 1
                priority = i + 1
                
                if priority <= limit:
                    print(f"  {priority}. {project['priority']}")
                else:
                    print(f"  {priority}. {project['name']} (priority: {priority})")
                    else:
                        print(f"  {priority}. {project['name']} (priority: {priority})")
                        
            return projects
            
            logger.info(f"Found {len(projects)} projects for migration")
            return projects
            
        except Exception as e:
            logger.error(f"Error getting priority projects: {str(e)}")
            return []

async def check_step_completion(
        step_number: int,
        total_steps: int,
        step_description: str
    ) -> bool:
        """Check if a specific migration step is completed."""
        
        print(f"\n=== Step {step_number}/{total_steps}: {step_description}")
        
        completed = self.check_step_completion(step_number, total_steps, step_description)
        
        if completed:
            print(f"✅ Step {step_number}/{total_steps}: {step_description}")
            return True
        else:
            if step_number < total_steps:
                print(f"⏳ Step {step_number}/{total_steps} - {step_description} ({step_percentage:.0f}% complete)")
                print(f"⚠ Step {step_number}/{total_steps} - {step_description} ({step_percentage:.0f}% complete)")
                return False
            else:
                return False
                
        except Exception as e:
            logger.error(f"Error checking step completion: {str(e)}")
            return False

def main():
    """
    Main entry point for the migration CLI tool.
    """
    try:
        return await main()
    except KeyboardInterrupt:
        logger.info("Migration cancelled by user")
    except Exception as e:
        logger.error(f"Migration cancelled by user: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

async def migrate_all_projects(
    dry_run: bool = False,
    project_id: Optional[str] = None,
    batch_size: int = 10
) -> bool:
    """Migrate all projects from Daytona.io to AgentCore."""
    
    migration_utils = AgentCoreMigrationUtils()
    
    print(f"\n=== MIGRATION PROCESS")
    
    # Check migration status
    status = await get_migration_status()
    
    if not status.success:
        return
        
    # Print project priority list
        if status.get('migrated_projects') > 0:
            priority_projects = await get_priority_projects(sort_by="created")
            print(f"\n📋 Migration Priority List:")
            for i, project in enumerate(priority_projects):
                print(f"  {i+1}. {project['name']} (Priority: {priority})")
                
        else:
            print("✅ All projects already migrated!")
            
        return True
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        return False

async def generate_migration_script(self) -> str:
    """Generate the migration CLI script."""
    script_content = """#!/usr/bin/env python3
"""
    
    # Create the Python script
    script_content = f"""
#!/usr/bin/env python3

import os
import sys
import os
import sys
import os
import os
import json

def main():
    print("=== AgentCore Migration Script ===")
    print("This script will help you migrate from Daytona.io to AWS AgentCore step by step.")
    print()
    print()
    print("Commands available:")
    print("  validate    - Validate AWS AgentCore configuration")
    print("  migrate    - Run migration (dry-run)")
    print("  generate-sql    - get status")
    print("  rollback    - --rollback")
    print()
    
    print("Configuration Requirements:")
    print("  1. Set AWS credentials")
    print(" 2. Configure database schema")
    print(" 3. Set up S3 bucket")
    print(" 4. Run migration")
    print(" 5. Validate migration")
    print()

    try:
        script_content = generate_migration_script()
        
        # Save the script
        with open(script_content, 'w') as f:
            os.chmod(os.path.join(os.getcwd(), "migrate_to_agentcore.py"),
            os.chmod(0o, os.FULL_PERMISSIONS)
            
        except Exception as e:
            logger.error(f"Failed to generate migration script: {e}")
            return
            
        print("\n✅ Migration script saved to migrate_to_agentcore.py")
        return script_content
        
    except Exception as e:
        logger.error(f"Failed to generate migration script: {e}")
            return ""

    print("\n✅ Script generated successfully at {os.path(script_content)}")
        return script_content

def get_priority_projects(
    sort_by: str = "created",
    descending: bool = False,
    limit: int = 10
) -> List[str]:
    """Get projects by creation date, newest first."""
        try:
            migration_utils = AgentCoreMigrationUtils()
            projects = await migration_utils.get_priority_projects(sort_by)
            return projects
        except Exception as e:
            logger.error(f"Error getting priority projects: {e}")
            return []

def get_priority_projects(
    sort_by: str = "created",
    descending: bool = False,
    limit: int = 10
) -> List[str]:
    """Get projects by modification date (newest first)."""
        try:
            migration_utils = AgentCoreMigrationUtils()
            projects = await migration_utils.get_priority_by_newest_first=True)
            
            if not projects:
                return []
            
            return projects
        except Exception as e:
            logger.error(f"Error getting priority projects: {e}")
            return []
        
    except Exception as e:
            logger.error(f"Error getting priority projects: {e}")
            return []

def get_current_projects(
    ) -> List[str]:
    """Get all current projects."""
    try:
        migration_utils = AgentCoreMigrationUtils()
        projects = await migration_utils.get_current_projects()
        return projects
    except Exception as e:
        logger.error(f"Error getting current projects: {e}")
        return []

def check_step_completion(
        step_number: int,
        total_steps: int,
        step_description: str,
        show_progress: bool = True
    ) -> bool:
        """Check if a specific migration step is completed."""
        
        if check_step_completion(step_number, total_steps, step_description):
            if completed:
                if show_progress:
                    print(f"✅ Step {step_number}/{total_steps}: {step_description} ({step_percentage:.0f}% complete)")
                return True
            else:
                print(f"⚠ Step {step_number}/{total_steps}: {step_description} ({step_percentage:.0f}% complete)")
            else:
                return False
                
        except Exception as e:
            return False

def main():
    """
    Migration controller main
    """
    try:
        return await main()
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()

# Main execution strategy
if __name__ == "__main__":
    main()
