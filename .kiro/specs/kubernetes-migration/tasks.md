# Implementation Plan

## Kubernetes Migration for Kortix/Suna

- [ ] 1. Set up project structure and test framework
  - [ ] 1.1 Create `k8s/` directory structure
    - Create `k8s/` directory in project root
    - Create `k8s/tests/` directory for manifest tests
    - _Requirements: 8.1_
  - [ ] 1.2 Set up test framework for manifest validation
    - Add `kubeconform` for schema validation
    - Add pytest + pyyaml + hypothesis for property tests
    - Create `k8s/tests/conftest.py` with shared fixtures
    - _Requirements: All_

- [ ] 2. Create namespace and base configuration
  - [ ] 2.1 Create `k8s/namespace.yaml` with namespace definition
    - Define `kortix` namespace with standard labels
    - Add optional ResourceQuota
    - _Requirements: 8.1, 8.4_
  - [ ] 2.2 Create `k8s/configmap.yaml` with non-sensitive configuration
    - Map all non-sensitive environment variables from `.env.example`
    - Include Redis host/port, Daytona URL, Langfuse host, etc.
    - _Requirements: 5.1, 5.4_
  - [ ] 2.3 Create `k8s/secrets.yaml` template for sensitive credentials
    - Map all sensitive environment variables (API keys, passwords)
    - Include placeholder values with comments
    - _Requirements: 5.1, 5.2, 5.4_

- [ ] 3. Create backend deployment
  - [ ] 3.1 Create `k8s/backend-deployment.yaml` with Deployment and HPA
    - Configure image, ports, probes, resources, security context
    - Add pod anti-affinity for HA
    - Configure rolling update strategy
    - Reference ConfigMap and Secret for environment variables
    - Include HPA: Min 2, Max 10 replicas, 70% CPU target
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 10.1, 10.3_
  - [ ] 3.2 Write unit tests for backend deployment manifest
    - Validate probes, resources, HPA configuration
    - _Requirements: 1.1-1.7_

- [ ] 4. Create worker deployment
  - [ ] 4.1 Create `k8s/worker-deployment.yaml` with Deployment and HPA
    - Configure Dramatiq command with processes and threads
    - Set terminationGracePeriodSeconds: 600
    - Add preStop lifecycle hook
    - Configure exec probe for worker health
    - Include HPA: Min 2, Max 20 replicas, 70% CPU target
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 10.2, 10.3_
  - [ ] 4.2 Write unit tests for worker deployment manifest
    - Validate command, probes, graceful shutdown
    - _Requirements: 2.1-2.7_

- [ ] 5. Create frontend deployment
  - [ ] 5.1 Create `k8s/frontend-deployment.yaml` with Deployment and HPA
    - Configure image, port 3015, probes, resources
    - Set non-root security context (user 1001)
    - Reference ConfigMap for NEXT_PUBLIC_* variables
    - Include HPA: Min 2, Max 6 replicas, 70% CPU target
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_
  - [ ] 5.2 Write unit tests for frontend deployment manifest
    - Validate probes, resources, security context
    - _Requirements: 3.1-3.7_

- [ ] 6. Checkpoint - Validate deployment manifests
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Create service definitions
  - [ ] 7.1 Create `k8s/services.yaml` with all Service resources
    - backend-service: ClusterIP, port 8000
    - frontend-service: ClusterIP, port 3015
    - redis-service: ClusterIP, port 6379 (conditional)
    - _Requirements: 7.1, 7.2, 7.3, 7.4_
  - [ ] 7.2 Write unit tests for service manifests
    - Validate ports, selectors, service types
    - _Requirements: 7.1-7.4_

- [ ] 8. Create ingress configuration
  - [ ] 8.1 Create `k8s/ingress.yaml` with Ingress resource
    - Configure TLS with cert-manager annotations
    - Route `/` to frontend, `/api/*` to backend
    - Add SSE support annotations (disable buffering)
    - Set extended timeouts (1800s)
    - Include provider-specific annotation examples (commented)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_
  - [ ] 8.2 Write unit tests for ingress manifest
    - Validate TLS, routing rules, SSE annotations
    - _Requirements: 6.1-6.8_

- [ ] 9. Create Redis StatefulSet (optional self-managed)
  - [ ] 9.1 Create `k8s/redis.yaml` with StatefulSet and PVC
    - Configure Redis 7 Alpine image
    - Set memory limit 8GB with allkeys-lru eviction
    - Enable AOF persistence
    - _Requirements: 4.2, 4.4, 4.5, 4.6, 4.7_
  - [ ] 9.2 Write unit tests for Redis manifest
    - Validate persistence, memory settings
    - _Requirements: 4.2-4.7_

- [ ] 10. Create Pod Disruption Budgets
  - [ ] 10.1 Create `k8s/pdb.yaml` with PDB resources
    - Backend: minAvailable: 1
    - Frontend: minAvailable: 1
    - Worker: maxUnavailable: 25%
    - _Requirements: 9.1, 9.2, 9.3_
  - [ ] 10.2 Write unit tests for PDB manifests
    - Validate policies match requirements
    - _Requirements: 9.1-9.3_

- [ ] 11. Write property-based tests for manifest correctness
  - [ ] 11.1 Write property test for environment variable coverage
    - Parse `backend/.env.example` to extract all variable names
    - Parse ConfigMap and Secret manifests
    - Assert every env var is in exactly one of ConfigMap or Secret
    - **Property 1: Environment Variable Coverage**
    - **Validates: Requirements 5.4**
  - [ ] 11.2 Write property test for standard labels
    - Parse all manifest files in `k8s/` directory
    - Assert each resource has `app.kubernetes.io/name`, `app.kubernetes.io/component`, `app.kubernetes.io/part-of`
    - **Property 2: Standard Labels on All Resources**
    - **Validates: Requirements 8.4**

- [ ] 12. Checkpoint - Validate all manifests and properties
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 13. Create deployment documentation
  - [ ] 13.1 Create `k8s/README.md` with deployment guide
    - Prerequisites (cluster, kubectl, ingress controller, cert-manager)
    - Deployment order with kubectl commands
    - Provider-specific instructions (AWS EKS, GCP GKE, Azure AKS)
    - Managed Redis configuration examples
    - Troubleshooting section
    - _Requirements: All_

- [ ] 14. Final Checkpoint - Full validation
  - Ensure all tests pass, ask the user if questions arise.
