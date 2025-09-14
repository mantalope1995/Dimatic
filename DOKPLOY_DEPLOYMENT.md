# Dokploy Deployment Guide for Kortix/Suna

This guide provides comprehensive instructions for deploying the Kortix/Suna AI platform using Dokploy.

## Prerequisites

1. A Dokploy instance running on your server
2. Domain names configured for your application
3. Supabase project with database configured
4. API keys for required services

## Deployment Steps

### 1. Create New Project in Dokploy

1. Log into your Dokploy dashboard
2. Click "Create Project"
3. Name it "kortix-suna" or your preferred name

### 2. Add Docker Compose Service

1. Inside the project, click "Add Service"
2. Select "Docker Compose"
3. Name it "kortix-app"

### 3. Configure Git Repository

1. In the service settings, go to "Git" tab
2. Add your repository URL
3. Set branch to `main` or your deployment branch
4. Configure deploy key if using private repository

### 4. Upload Docker Compose Configuration

1. Go to "General" tab
2. In the "Compose File" section, either:
   - Set path to `docker-compose.dokploy.yaml`
   - Or copy the contents of `docker-compose.dokploy.yaml` directly into the editor

### 5. Configure Environment Variables

Navigate to the "Environment" tab and add the following variables:

#### Required Core Variables

```env
# Environment
ENV_MODE=production

# Domains (adjust to your domains)
APP_DOMAIN=app.yourdomain.com
BACKEND_DOMAIN=api.yourdomain.com

# Database (Supabase)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_JWT_SECRET=your-jwt-secret

# Frontend URLs
NEXT_PUBLIC_ENV_MODE=production
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
NEXT_PUBLIC_BACKEND_URL=https://api.yourdomain.com/api
NEXT_PUBLIC_URL=https://app.yourdomain.com

# Search & Data (Required)
RAPID_API_KEY=your-rapid-api-key
TAVILY_API_KEY=your-tavily-api-key

# Web Scraping (Required)
FIRECRAWL_API_KEY=your-firecrawl-api-key

# Agent Sandbox (Required for agent execution)
DAYTONA_API_KEY=your-daytona-api-key
DAYTONA_SERVER_URL=https://app.daytona.io/api
DAYTONA_TARGET=us
```

#### LLM Provider Variables (At least one required)

```env
# Anthropic
ANTHROPIC_API_KEY=your-anthropic-key

# OpenAI
OPENAI_API_KEY=your-openai-key

# Google
GEMINI_API_KEY=your-gemini-key

# Groq
GROQ_API_KEY=your-groq-key

# OpenRouter
OPENROUTER_API_KEY=your-openrouter-key

# X.AI
XAI_API_KEY=your-xai-key

# Z AI (for GLM-4.5)
Z_AI_API_KEY=your-z-ai-key
Z_AI_API_BASE=https://api.z.ai/api/coding/paas/v4
```

#### Optional Variables

```env
# Redis (if using authentication)
REDIS_PASSWORD=your-redis-password

# AWS Bedrock (if using)
AWS_ACCESS_KEY_ID=your-aws-key
AWS_SECRET_ACCESS_KEY=your-aws-secret
AWS_REGION_NAME=us-east-1

# Security
MCP_CREDENTIAL_ENCRYPTION_KEY=your-encryption-key
TRIGGER_WEBHOOK_SECRET=your-webhook-secret

# Observability
LANGFUSE_PUBLIC_KEY=your-langfuse-key
LANGFUSE_SECRET_KEY=your-langfuse-secret
LANGFUSE_HOST=https://cloud.langfuse.com

# Billing (Stripe)
STRIPE_SECRET_KEY=your-stripe-secret
STRIPE_WEBHOOK_SECRET=your-stripe-webhook-secret
STRIPE_DEFAULT_PLAN_ID=your-default-plan-id
STRIPE_DEFAULT_TRIAL_DAYS=14

# Admin
KORTIX_ADMIN_API_KEY=your-admin-api-key

# Google Integration
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=https://api.yourdomain.com/api/google/callback

# PostHog Analytics
NEXT_PUBLIC_POSTHOG_KEY=your-posthog-key

# Edge Config (Vercel)
EDGE_CONFIG=your-edge-config-url
```

### 6. Configure Storage

1. Go to "Storage" tab
2. Ensure the Redis data directory is configured:
   - Mount Path: `/data`
   - Host Path: `../files/redis-data`
3. This ensures Redis data persists between deployments

### 7. Configure Domains

1. Go to "Domains" tab
2. Add your domains:
   - Frontend: `app.yourdomain.com`
   - Backend API: `api.yourdomain.com`
3. Enable SSL/TLS certificates (Let's Encrypt)

### 8. Deploy

1. Go to "General" tab
2. Click "Deploy" button
3. Monitor the deployment logs for any issues

### 9. Verify Deployment

After deployment completes:

1. Check that all services are running:
   - Redis: Should show healthy status
   - Backend: Should be accessible at `https://api.yourdomain.com/health`
   - Worker: Should be processing background tasks
   - Frontend: Should be accessible at `https://app.yourdomain.com`

2. Test the application:
   - Visit the frontend URL
   - Create an account
   - Test agent creation and execution

## Important Notes

### Redis Persistence

The configuration uses Dokploy's `../files/` directory pattern to ensure Redis data persists between deployments. The Redis configuration includes:
- AOF persistence for durability
- RDB snapshots for backup
- Memory management with LRU eviction
- Performance optimizations

### Environment Variable Management

- In production/staging, the backend uses system environment variables directly (no .env file loading)
- Frontend environment variables prefixed with `NEXT_PUBLIC_` are built into the application at build time
- Sensitive variables should never be prefixed with `NEXT_PUBLIC_`

### Network Configuration

All services use the `dokploy-network` for internal communication:
- Backend connects to Redis using hostname `redis`
- Frontend connects to backend using hostname `backend`
- External traffic is routed through Traefik

### Scaling Considerations

For production deployments:
1. Adjust Redis `maxmemory` in `redis.conf` based on available RAM
2. Configure worker process count based on workload
3. Consider using external Redis service for high availability
4. Use external Supabase database (already configured)

## Troubleshooting

### Common Issues

1. **Services not starting**: Check environment variables are properly set
2. **Redis connection errors**: Ensure Redis is healthy and network is configured
3. **Database connection errors**: Verify Supabase credentials and network access
4. **Domain routing issues**: Check Traefik labels and domain configuration

### Viewing Logs

In Dokploy:
1. Go to your service
2. Click "Logs" tab
3. Select the container to view logs for

### Health Checks

- Backend health: `https://api.yourdomain.com/health`
- Redis health: Check container status in Dokploy
- Worker health: Monitor Dramatiq worker logs

## Updating the Application

To deploy updates:
1. Push changes to your Git repository
2. In Dokploy, go to your service
3. Click "Redeploy" or set up auto-deployment on push

## Backup Strategy

1. **Database**: Supabase handles backups automatically
2. **Redis**: Data persists in `../files/redis-data` with AOF and RDB
3. **Environment Variables**: Export from Dokploy UI regularly
4. **Application Code**: Maintained in Git repository

## Security Recommendations

1. Use strong, unique API keys for all services
2. Enable Redis password authentication in production
3. Regularly rotate sensitive credentials
4. Monitor logs for suspicious activity
5. Keep Docker images updated
6. Use HTTPS for all public endpoints

## Support

For issues specific to:
- Kortix/Suna platform: Check the GitHub repository issues
- Dokploy deployment: Consult Dokploy documentation
- Service integrations: Refer to respective service documentation