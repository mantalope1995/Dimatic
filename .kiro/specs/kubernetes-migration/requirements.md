# Kubernetes Migration Spec

## Overview

Migrate the Kortix/Suna application from Docker Compose to a managed Kubernetes cluster to enable horizontal scaling, high availability, and production-grade orchestration.

## Current State

The application currently runs on Docker Compose with:
- **Frontend**: Next.js 15 application (port 3015)
- **Backend**: FastAPI Python application with Gunicorn (port 8000)
- **Worker**: Dramatiq background workers processing agent tasks via Redis
- **Redis**: Message broker and cache (port 6379)
- **External Services** (already managed, no migration needed):
  - Supabase (managed PostgreSQL, Auth, Storage, Realtime)
  - Daytona (managed sandbox environments for agent execution)

### Scaling Limitations
- Single-node deployment (no horizontal scaling)
- Manual scaling requires container restart
- No auto-scaling based on load
- Worker processes limited to single host resources
- No rolling deployments or zero-downtime updates

### Important Architecture Notes
1. **Agent Sandboxes are External**: Agent code execution uses Daytona's managed sandbox service (not local Docker). No K8s changes needed for sandboxes.
2. **SSE Streaming**: Backend uses Server-Sent Events (`text/event-stream`) for real-time agent responses. Requires proper Ingress/LB configuration.
3. **Long-Running Connections**: Agent runs can take 30+ minutes. Timeouts must be configured appropriately.

---

## User Stories

### Story 1: Horizontal Pod Autoscaling for Backend API
**As a** platform operator  
**I want** the backend API to automatically scale based on CPU/memory utilization  
**So that** the system handles traffic spikes without manual intervention

**Acceptance Criteria:**
- [ ] Backend Deployment with HorizontalPodAutoscaler (HPA)
- [ ] Min replicas: 2, Max replicas: 10
- [ ] Scale up at 70% CPU utilization
- [ ] Liveness probe: HTTP GET `/api/health` (initialDelay: 30s, period: 10s)
- [ ] Readiness probe: HTTP GET `/api/health-docker` (initialDelay: 10s, period: 5s)
- [ ] Resource requests: 500m CPU, 1Gi memory
- [ ] Resource limits: 2 CPU, 4Gi memory

---

### Story 2: Scalable Worker Deployment
**As a** platform operator  
**I want** Dramatiq workers to scale independently based on queue depth  
**So that** agent task processing keeps up with demand

**Acceptance Criteria:**
- [ ] Worker Deployment separate from backend
- [ ] HPA based on custom metrics (Redis queue depth via `/api/metrics/queue`)
- [ ] Min replicas: 2, Max replicas: 20
- [ ] Each worker runs: `uv run dramatiq --processes 4 --threads 4 run_agent_background`
- [ ] Liveness probe: exec `uv run worker_health.py` (timeout: 30s)
- [ ] Resource requests: 1 CPU, 2Gi memory
- [ ] Resource limits: 4 CPU, 8Gi memory
- [ ] Graceful shutdown with `terminationGracePeriodSeconds: 600`

---

### Story 3: Frontend Deployment with CDN-Ready Configuration
**As a** platform operator  
**I want** the Next.js frontend to scale horizontally  
**So that** user-facing traffic is handled efficiently

**Acceptance Criteria:**
- [ ] Frontend Deployment with HPA
- [ ] Min replicas: 2, Max replicas: 6
- [ ] Scale at 70% CPU utilization
- [ ] Liveness probe: HTTP GET `/` (port 3015)
- [ ] Resource requests: 250m CPU, 512Mi memory
- [ ] Resource limits: 1 CPU, 1Gi memory
- [ ] Environment variables via ConfigMap (public) and Secret (sensitive)

---

### Story 4: Redis High Availability
**As a** platform operator  
**I want** Redis to be highly available  
**So that** message broker failures don't halt the system

**Acceptance Criteria:**
- [ ] Option A (Recommended): Use managed Redis (AWS ElastiCache, GCP Memorystore, Azure Cache)
- [ ] Option B: Redis StatefulSet with persistence (for self-managed)
- [ ] Connection string configurable via Secret
- [ ] TLS support for production (`REDIS_SSL=true`)
- [ ] Persistence enabled with AOF
- [ ] Memory limit: 8GB (matches current `--maxmemory 8gb` config)
- [ ] Eviction policy: `allkeys-lru`

---

### Story 5: Secrets and Configuration Management
**As a** platform operator  
**I want** sensitive credentials stored securely in Kubernetes Secrets  
**So that** API keys and passwords are not exposed in manifests

**Acceptance Criteria:**
- [ ] Kubernetes Secret for sensitive env vars (API keys, DB credentials)
- [ ] ConfigMap for non-sensitive configuration
- [ ] External Secrets Operator integration (optional, for cloud secret managers)
- [ ] All 40+ environment variables from `.env.example` mapped appropriately

---

### Story 6: Ingress with TLS and SSE Support
**As a** platform operator  
**I want** HTTPS traffic routed to services via Ingress with proper streaming support  
**So that** the application is securely accessible and real-time features work correctly

**Acceptance Criteria:**
- [ ] Ingress resource with TLS termination
- [ ] Route `/` to frontend service
- [ ] Route `/api/*` to backend service
- [ ] cert-manager integration for automatic certificate renewal
- [ ] Support for cloud load balancer annotations (AWS ALB, GCP, Azure)
- [ ] SSE/streaming support: disable response buffering (`X-Accel-Buffering: no`)
- [ ] Extended timeouts for long-running agent connections (30+ minutes)
- [ ] Sticky sessions for SSE connections (optional, for multi-replica backend)

---

### Story 7: Service Definitions
**As a** platform operator  
**I want** Kubernetes Services to expose deployments internally  
**So that** pods can communicate reliably

**Acceptance Criteria:**
- [ ] `backend-service`: ClusterIP, port 8000
- [ ] `frontend-service`: ClusterIP, port 3015
- [ ] `redis-service`: ClusterIP, port 6379 (if self-managed)
- [ ] Service discovery via DNS (e.g., `backend-service.default.svc.cluster.local`)

---

### Story 8: Namespace and Resource Organization
**As a** platform operator  
**I want** resources organized in a dedicated namespace  
**So that** the application is isolated and manageable

**Acceptance Criteria:**
- [ ] Dedicated namespace: `kortix` or `suna`
- [ ] Resource quotas defined
- [ ] Network policies for pod-to-pod communication (optional)
- [ ] Labels and annotations for observability

---

### Story 9: Pod Disruption Budgets
**As a** platform operator  
**I want** Pod Disruption Budgets to ensure availability during cluster maintenance  
**So that** the application remains available during node upgrades and scaling events

**Acceptance Criteria:**
- [ ] PDB for backend: `minAvailable: 1` or `maxUnavailable: 50%`
- [ ] PDB for frontend: `minAvailable: 1`
- [ ] PDB for workers: `maxUnavailable: 25%` (allow gradual draining)

---

### Story 10: Graceful Shutdown and Lifecycle Hooks
**As a** platform operator  
**I want** pods to gracefully handle termination signals  
**So that** in-flight requests and agent runs complete without interruption

**Acceptance Criteria:**
- [ ] Backend: `terminationGracePeriodSeconds: 120` (allow SSE connections to close)
- [ ] Worker: `terminationGracePeriodSeconds: 600` (agent runs can be long)
- [ ] PreStop hooks to drain connections before SIGTERM
- [ ] Proper signal handling in application code (already exists via Gunicorn)

---

## Technical Requirements

### Managed Kubernetes Compatibility
The manifests should work with:
- AWS EKS
- Google GKE
- Azure AKS
- DigitalOcean Kubernetes

### Container Images
- Backend: `ghcr.io/suna-ai/suna-backend:latest`
- Frontend: Build from `frontend/Dockerfile`
- Redis: `redis:7-alpine` (if self-managed)

### Health Endpoints
| Service | Liveness | Readiness | Notes |
|---------|----------|-----------|-------|
| Backend | `/api/health` | `/api/health-docker` | health-docker checks Redis + DB |
| Worker | `uv run worker_health.py` | Same | Checks Redis connectivity |
| Frontend | `/` | `/` | Static page check |

### Timeout Considerations
| Component | Timeout | Reason |
|-----------|---------|--------|
| Ingress proxy | 1800s (30min) | Agent runs can be long |
| Backend Gunicorn | 1800s | Match ingress timeout |
| SSE connections | No buffering | Real-time streaming |
| Worker graceful shutdown | 600s | Complete in-flight agent tasks |

### Environment Variables
See `backend/.env.example` for full list. Key categories:
- Database: `SUPABASE_*`
- Redis: `REDIS_*`
- LLM Providers: `ANTHROPIC_*`, `OPENAI_*`, etc.
- Billing: `STRIPE_*`
- Integrations: `COMPOSIO_*`, `GOOGLE_*`

---

## Deliverables

1. **`k8s/namespace.yaml`** - Namespace definition
2. **`k8s/configmap.yaml`** - Non-sensitive configuration
3. **`k8s/secrets.yaml`** - Template for sensitive credentials
4. **`k8s/backend-deployment.yaml`** - Backend API deployment + HPA
5. **`k8s/worker-deployment.yaml`** - Dramatiq worker deployment + HPA
6. **`k8s/frontend-deployment.yaml`** - Frontend deployment + HPA
7. **`k8s/services.yaml`** - Service definitions
8. **`k8s/ingress.yaml`** - Ingress with TLS and SSE support
9. **`k8s/redis.yaml`** - Redis StatefulSet (optional, for self-managed)
10. **`k8s/pdb.yaml`** - Pod Disruption Budgets
11. **`k8s/README.md`** - Deployment guide with provider-specific instructions

---

## Additional Considerations

### Scheduled Tasks (pg_cron)
The application uses **Supabase pg_cron** for scheduled tasks (e.g., account deletion, subscription management). These run in the database layer, not in K8s. No CronJob resources needed.

### File Storage
File uploads use **Supabase Storage** (S3-compatible). No persistent volumes needed for the application pods - they are stateless.

### Presence/Realtime
User presence tracking uses Redis. With multiple backend replicas, presence data is shared via Redis (already handled). No additional K8s configuration needed.

### Network Egress
Backend pods need outbound access to:
- Supabase (database, auth, storage)
- Daytona API (sandbox management)
- LLM providers (Anthropic, OpenAI, etc.)
- External APIs (Stripe, Composio, etc.)

Ensure network policies (if used) allow egress to these services.

---

## Out of Scope

- CI/CD pipeline configuration (GitHub Actions, ArgoCD)
- Monitoring stack (Prometheus, Grafana) - but health endpoints are ready
- Log aggregation (ELK, Loki)
- Service mesh (Istio, Linkerd)
- Database migration (Supabase remains external managed service)
- Sandbox infrastructure (Daytona remains external managed service)
- Custom metrics adapter for queue-based HPA (document as future enhancement)
- Kubernetes CronJobs (scheduled tasks handled by Supabase pg_cron)

---

## References

- Current Docker Compose: `docker-compose.yaml`, `deploy-dockercompose.yml`
- Backend Dockerfile: `backend/Dockerfile`
- Frontend Dockerfile: `frontend/Dockerfile`
- Environment template: `backend/.env.example`
- Health endpoints: `backend/api.py`, `backend/worker_health.py`
