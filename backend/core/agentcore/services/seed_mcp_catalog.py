"""
MCP Catalog Seeding Script

Pre-populates the MCP catalog with common third-party service integrations.
Run this module to seed the catalog with 15 core services.
"""

import asyncio
import logging
from typing import List

from .mcp_catalog_service import MCPCatalogService, MCPServiceDefinition
from ..config import get_config

logger = logging.getLogger(__name__)


# Initial service definitions for seeding
INITIAL_SERVICES: List[dict] = [
    {
        "service_name": "github",
        "display_name": "GitHub",
        "description": "GitHub repository management, issues, pull requests, and workflows",
        "category": "git",
        "auth_type": "oauth2",
        "oauth_config": {
            "authorization_url": "https://github.com/login/oauth/authorize",
            "token_url": "https://github.com/login/oauth/access_token",
            "scope": "repo,read:user,workflow",
            "callback_path": "/oauth/github/callback"
        },
        "mcp_server_config": {
            "image_uri": "ecr.aws/github-mcp-server:latest",
            "memory_mb": 512,
            "timeout_seconds": 30
        },
        "features": ["repositories", "issues", "pull_requests", "workflows", "actions"],
        "requires_callback": True
    },
    {
        "service_name": "slack",
        "display_name": "Slack",
        "description": "Slack messaging, channels, files, and workspace management",
        "category": "messaging",
        "auth_type": "oauth2",
        "oauth_config": {
            "authorization_url": "https://slack.com/oauth/v2/authorize",
            "token_url": "https://slack.com/api/oauth.v2.access",
            "scope": "chat:write,channels:read,files:write,im:write",
            "callback_path": "/oauth/slack/callback"
        },
        "mcp_server_config": {
            "image_uri": "ecr.aws/slack-mcp-server:latest",
            "memory_mb": 512,
            "timeout_seconds": 30
        },
        "features": ["messages", "channels", "files", "users", "reactions"],
        "requires_callback": True
    },
    {
        "service_name": "gmail",
        "display_name": "Gmail",
        "description": "Gmail email operations including send, read, search, and labels",
        "category": "email",
        "auth_type": "oauth2",
        "oauth_config": {
            "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "scope": "https://www.googleapis.com/auth/gmail.send,https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/gmail.labels",
            "callback_path": "/oauth/gmail/callback"
        },
        "mcp_server_config": {
            "image_uri": "ecr.aws/gmail-mcp-server:latest",
            "memory_mb": 512,
            "timeout_seconds": 30
        },
        "features": ["send_email", "read_email", "search", "labels", "drafts"],
        "requires_callback": True
    },
    {
        "service_name": "google_drive",
        "display_name": "Google Drive",
        "description": "Google Drive file operations, folders, sharing, and permissions",
        "category": "storage",
        "auth_type": "oauth2",
        "oauth_config": {
            "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "scope": "https://www.googleapis.com/auth/drive,https://www.googleapis.com/auth/drive.file",
            "callback_path": "/oauth/google-drive/callback"
        },
        "mcp_server_config": {
            "image_uri": "ecr.aws/google-drive-mcp-server:latest",
            "memory_mb": 512,
            "timeout_seconds": 30
        },
        "features": ["files", "folders", "sharing", "permissions", "search"],
        "requires_callback": True
    },
    {
        "service_name": "notion",
        "display_name": "Notion",
        "description": "Notion workspace, pages, databases, and content management",
        "category": "productivity",
        "auth_type": "oauth2",
        "oauth_config": {
            "authorization_url": "https://api.notion.com/v1/oauth/authorize",
            "token_url": "https://api.notion.com/v1/oauth/token",
            "scope": "",
            "callback_path": "/oauth/notion/callback"
        },
        "mcp_server_config": {
            "image_uri": "ecr.aws/notion-mcp-server:latest",
            "memory_mb": 512,
            "timeout_seconds": 30
        },
        "features": ["pages", "databases", "blocks", "search", "comments"],
        "requires_callback": True
    },
    {
        "service_name": "jira",
        "display_name": "Jira",
        "description": "Jira issue tracking, projects, sprints, and agile management",
        "category": "project_management",
        "auth_type": "oauth2",
        "oauth_config": {
            "authorization_url": "https://auth.atlassian.com/authorize",
            "token_url": "https://auth.atlassian.com/oauth/token",
            "scope": "read:jira-work,read:jira-user,write:jira-work",
            "callback_path": "/oauth/jira/callback"
        },
        "mcp_server_config": {
            "image_uri": "ecr.aws/jira-mcp-server:latest",
            "memory_mb": 512,
            "timeout_seconds": 30
        },
        "features": ["issues", "projects", "sprints", "boards", "worklogs"],
        "requires_callback": True
    },
    {
        "service_name": "linear",
        "display_name": "Linear",
        "description": "Linear project management, issues, workflows, and teams",
        "category": "project_management",
        "auth_type": "oauth2",
        "oauth_config": {
            "authorization_url": "https://linear.app/oauth/authorize",
            "token_url": "https://api.linear.app/oauth/token",
            "scope": "read,write",
            "callback_path": "/oauth/linear/callback"
        },
        "mcp_server_config": {
            "image_uri": "ecr.aws/linear-mcp-server:latest",
            "memory_mb": 512,
            "timeout_seconds": 30
        },
        "features": ["issues", "projects", "teams", "workflows", "cycles"],
        "requires_callback": True
    },
    {
        "service_name": "discord",
        "display_name": "Discord",
        "description": "Discord messaging, servers, channels, and bot interactions",
        "category": "messaging",
        "auth_type": "oauth2",
        "oauth_config": {
            "authorization_url": "https://discord.com/oauth2/authorize",
            "token_url": "https://discord.com/api/oauth2/token",
            "scope": "bot,messages.read,webhook.incoming",
            "callback_path": "/oauth/discord/callback"
        },
        "mcp_server_config": {
            "image_uri": "ecr.aws/discord-mcp-server:latest",
            "memory_mb": 512,
            "timeout_seconds": 30
        },
        "features": ["messages", "channels", "servers", "webhooks", "members"],
        "requires_callback": True
    },
    {
        "service_name": "trello",
        "display_name": "Trello",
        "description": "Trello boards, cards, lists, and project management",
        "category": "project_management",
        "auth_type": "oauth2",
        "oauth_config": {
            "authorization_url": "https://trello.com/1/authorize",
            "token_url": "https://trello.com/1/oauth2/token",
            "scope": "read,write",
            "callback_path": "/oauth/trello/callback"
        },
        "mcp_server_config": {
            "image_uri": "ecr.aws/trello-mcp-server:latest",
            "memory_mb": 512,
            "timeout_seconds": 30
        },
        "features": ["boards", "cards", "lists", "labels", "checklists"],
        "requires_callback": True
    },
    {
        "service_name": "dropbox",
        "display_name": "Dropbox",
        "description": "Dropbox file storage, sharing, and collaboration",
        "category": "storage",
        "auth_type": "oauth2",
        "oauth_config": {
            "authorization_url": "https://www.dropbox.com/oauth2/authorize",
            "token_url": "https://api.dropboxapi.com/oauth2/token",
            "scope": "files.content.write,files.content.read,sharing.write",
            "callback_path": "/oauth/dropbox/callback"
        },
        "mcp_server_config": {
            "image_uri": "ecr.aws/dropbox-mcp-server:latest",
            "memory_mb": 512,
            "timeout_seconds": 30
        },
        "features": ["files", "folders", "sharing", "search", "revisions"],
        "requires_callback": True
    },
    {
        "service_name": "stripe",
        "display_name": "Stripe",
        "description": "Stripe payments, subscriptions, invoices, and customers",
        "category": "payments",
        "auth_type": "api_key",
        "oauth_config": None,
        "mcp_server_config": {
            "image_uri": "ecr.aws/stripe-mcp-server:latest",
            "memory_mb": 512,
            "timeout_seconds": 30
        },
        "features": ["payments", "subscriptions", "invoices", "customers", "products"],
        "requires_callback": False
    },
    {
        "service_name": "twilio",
        "display_name": "Twilio",
        "description": "Twilio SMS, voice, messaging, and communications",
        "category": "communications",
        "auth_type": "api_key",
        "oauth_config": None,
        "mcp_server_config": {
            "image_uri": "ecr.aws/twilio-mcp-server:latest",
            "memory_mb": 512,
            "timeout_seconds": 30
        },
        "features": ["sms", "voice", "whatsapp", "email", "phone_numbers"],
        "requires_callback": False
    },
    {
        "service_name": "openai",
        "display_name": "OpenAI",
        "description": "OpenAI API integration for GPT models, DALL-E, and embeddings",
        "category": "ai",
        "auth_type": "api_key",
        "oauth_config": None,
        "mcp_server_config": {
            "image_uri": "ecr.aws/openai-mcp-server:latest",
            "memory_mb": 512,
            "timeout_seconds": 30
        },
        "features": ["chat", "completions", "embeddings", "images", "fine_tuning"],
        "requires_callback": False
    },
    {
        "service_name": "salesforce",
        "display_name": "Salesforce",
        "description": "Salesforce CRM, leads, opportunities, and customer data",
        "category": "crm",
        "auth_type": "oauth2",
        "oauth_config": {
            "authorization_url": "https://login.salesforce.com/services/oauth2/authorize",
            "token_url": "https://login.salesforce.com/services/oauth2/token",
            "scope": "api,refresh_token,full",
            "callback_path": "/oauth/salesforce/callback"
        },
        "mcp_server_config": {
            "image_uri": "ecr.aws/salesforce-mcp-server:latest",
            "memory_mb": 512,
            "timeout_seconds": 30
        },
        "features": ["leads", "opportunities", "accounts", "contacts", "reports"],
        "requires_callback": True
    },
    {
        "service_name": "hubspot",
        "display_name": "HubSpot",
        "description": "HubSpot CRM, marketing, sales, and customer service",
        "category": "crm",
        "auth_type": "oauth2",
        "oauth_config": {
            "authorization_url": "https://app.hubspot.com/oauth/authorize",
            "token_url": "https://api.hubapi.com/oauth/v1/token",
            "scope": "crm.objects.contacts.read,crm.objects.contacts.write,crm.schemas.contacts.read",
            "callback_path": "/oauth/hubspot/callback"
        },
        "mcp_server_config": {
            "image_uri": "ecr.aws/hubspot-mcp-server:latest",
            "memory_mb": 512,
            "timeout_seconds": 30
        },
        "features": ["contacts", "companies", "deals", "tickets", "forms"],
        "requires_callback": True
    }
]


async def seed_catalog() -> dict:
    """
    Seed the MCP catalog with initial services

    Returns:
        Dictionary with seeding results:
        - total: Total number of services to seed
        - registered: Number of services successfully registered
        - skipped: Number of services already existing
        - failed: Number of services that failed to register
        - errors: List of error messages for failed services
    """
    config = get_config()
    catalog = MCPCatalogService(config=config)

    results = {
        "total": len(INITIAL_SERVICES),
        "registered": 0,
        "skipped": 0,
        "failed": 0,
        "errors": []
    }

    logger.info(f"Starting MCP catalog seeding with {results['total']} services")

    for service_data in INITIAL_SERVICES:
        service_name = service_data["service_name"]

        try:
            # Check if service already exists
            try:
                await catalog.get_service(service_name)
                logger.info(f"Service {service_name} already exists, skipping")
                results["skipped"] += 1
                continue
            except Exception:
                # Service doesn't exist, proceed with registration
                pass

            # Create service definition
            service_def = MCPServiceDefinition(**service_data)

            # Register service
            await catalog.register_service(service_def)
            logger.info(f"Successfully registered service: {service_name}")
            results["registered"] += 1

        except Exception as e:
            logger.error(f"Failed to register service {service_name}: {e}")
            results["failed"] += 1
            results["errors"].append(f"{service_name}: {str(e)}")

    logger.info(
        f"MCP catalog seeding complete: "
        f"{results['registered']} registered, "
        f"{results['skipped']} skipped, "
        f"{results['failed']} failed"
    )

    return results


async def list_seeded_services() -> List[str]:
    """
    List all service names that would be seeded

    Returns:
        List of service names
    """
    return [s["service_name"] for s in INITIAL_SERVICES]


async def get_service_count_by_category() -> dict:
    """
    Get count of services by category

    Returns:
        Dictionary mapping category to service count
    """
    category_counts = {}
    for service_data in INITIAL_SERVICES:
        category = service_data["category"]
        category_counts[category] = category_counts.get(category, 0) + 1

    return category_counts


# CLI entry point for manual seeding
if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    async def main():
        print("Starting MCP catalog seeding...")
        results = await seed_catalog()

        print("\nSeeding Results:")
        print(f"  Total services: {results['total']}")
        print(f"  Registered: {results['registered']}")
        print(f"  Skipped (already exists): {results['skipped']}")
        print(f"  Failed: {results['failed']}")

        if results['errors']:
            print("\nErrors:")
            for error in results['errors']:
                print(f"  - {error}")

        # Print category breakdown
        print("\nServices by Category:")
        category_counts = await get_service_count_by_category()
        for category, count in sorted(category_counts.items()):
            print(f"  {category}: {count}")

        return 0 if results['failed'] == 0 else 1

    sys.exit(asyncio.run(main()))
