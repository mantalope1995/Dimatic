#### Role-Based Access Control

```python
from enum import Enum

class UserRole(Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"

def check_permission(user_role: UserRole, required_role: UserRole) -> bool:
    """Check if user role has required permission level"""
    role_hierarchy = [UserRole.VIEWER, UserRole.MEMBER, UserRole.ADMIN, UserRole.OWNER]
    return role_hierarchy.index(user_role) >= role_hierarchy.index(required_role)
```

#### API Security

- Rate limiting on all endpoints
- Input validation using Pydantic models
- SQL injection prevention via Supabase client
- XSS protection with proper escaping
- CORS configuration for allowed origins

```python
from fastapi import RateLimitExceeded
from slowapi import Limiter

limiter = Limiter(key_func=get_remote_address)

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded"}
    )
```

### Data Encryption

#### At Rest

- **Database**: PostgreSQL with encrypted connections
- **Credentials**: AES-256 encryption for stored API keys
- **File Storage**: Server-side encryption for uploaded files
- **Backups**: Encrypted backup files

#### In Transit

- **TLS 1.3** for all HTTPS connections
- **Certificate rotation** every 90 days
- **HSTS headers** enabled
- **Secure cookies** with HttpOnly and Secure flags

### Agent Sandbox Security

#### Container Isolation

```python
# Docker security options
SECURITY_OPTIONS = {
    "cap_drop": ["ALL"],
    "cap_add": ["NET_BIND_SERVICE"],
    "read_only": True,
    "no_new_privileges": True,
    "network_mode": "none",
    "memory": "512m",
    "cpus": "0.5"
}
```

#### Resource Limits

- Maximum execution time: 300 seconds per agent run
- Memory limit: 512MB per container
- CPU limit: 0.5 cores
- Network access: Restricted to necessary endpoints only
- File system: Read-only with specific write directories

### Sensitive Data Handling

#### Data Classification

| Category | Examples | Handling |
|----------|----------|----------|
| **Critical** | API keys, passwords, tokens | Encrypted at rest, access logged |
| **Sensitive** | User emails, payment info | Encrypted, access controlled |
| **Internal** | Agent prompts, thread content | Access logged, retention policy |
| **Public** | Agent names, public threads | No restrictions |

#### Data Retention

- **Agent conversations**: Retained for 30 days (configurable)
- **User data**: Retained until account deletion
- **Logs**: Retained for 90 days
- **Backups**: Retained for 30 days

### Compliance

#### GDPR Compliance

- **Data minimization**: Only collect necessary data
- **Right to access**: Users can export their data
- **Right to be forgotten**: Account deletion with data purge
- **Consent management**: Explicit consent for data processing
- **Data portability**: Export in standard formats

#### Security Audits

- Annual penetration testing
- Quarterly vulnerability scans
- Monthly security reviews
- Real-time threat monitoring

---

## Performance Optimization

### Backend Performance

#### Caching Strategy

```python
# Multi-level caching implementation
CACHE_TIERS = {
    "l1": {  # In-memory
        "backend": "dict",
        "ttl": 60,
        "max_size": 10000
    },
    "l2": {  # Redis
        "backend": "redis",
        "ttl": 3600,
        "prefix": "suna:"
    }
}

async def get_cached_data(key: str) -> Optional[dict]:
    # Check L1 cache first
    if key in l1_cache:
        return l1_cache[key]
    
    # Check L2 cache
    cached = await redis.get(key)
    if cached:
        l1_cache[key] = cached  # Promote to L1
        return cached
    
    return None
```

#### Async Processing

- Agent execution via Dramatiq workers
- Background task queue with Redis broker
- Non-blocking I/O for all external calls
- Connection pooling for database and Redis

#### Database Optimization

- **Indexes**: Composite indexes for common queries
- **Query optimization**: EXPLAIN ANALYZE for slow queries
- **Connection pooling**: Supabase connection pooling
- **Batch operations**: Bulk inserts and updates

### Frontend Performance

#### Code Splitting

```typescript
// Dynamic imports for route-based splitting
const AgentChat = dynamic(
  () => import('./components/agents/AgentChat'),
  { 
    loading: () => <AgentChatSkeleton />,
    ssr: false  // Disable SSR for chat component
  }
);

// Component-level lazy loading
const FilePreview = lazy(() => import('./components/files/FilePreview'));
```

#### Asset Optimization

- **Images**: WebP format with fallbacks
- **Bundles**: Tree shaking and minification
- **Fonts**: Subsetted, preloaded, font-display: swap
- **Scripts**: Deferred loading for non-critical

#### Virtual Scrolling

```typescript
// For long thread message lists
import { useVirtualizer } from '@tanstack/react-virtual';

const VirtualMessageList = ({ messages }) => {
  const parentRef = useRef(null);
  
  const virtualizer = useVirtualizer({
    count: messages.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 80,
    overscan: 5,
  });
  
  return (
    <div ref={parentRef} className="h-full overflow-auto">
      <div style={{ height: `${virtualizer.getTotalSize()}px` }}>
        {virtualizer.getVirtualItems().map(virtualItem => (
          <Message key={virtualItem.key} index={virtualItem.index} />
        ))}
      </div>
    </div>
  );
};
```

### LLM Cost Optimization

#### Token Management

```python
# Token counting and budgeting
class TokenBudget:
    def __init__(self, max_tokens: int, model: str):
        self.max_tokens = max_tokens
        self.model = model
        self.used_tokens = 0
    
    async def check_and_use(self, prompt_tokens: int) -> bool:
        if self.used_tokens + prompt_tokens > self.max_tokens:
            raise TokenLimitExceeded()
        self.used_tokens += prompt_tokens
        return True
```

#### Model Selection Strategy

| Task Type | Recommended Model | Reasoning |
|-----------|-------------------|-----------|
| Simple Q&A | Claude Haiku | Fast, cost-effective |
| Standard tasks | Claude Sonnet 4 | Balanced performance |
| Complex reasoning | Claude Opus 4 | Highest quality |
| Code tasks | Claude Sonnet 4 | Good code understanding |

### Resource Management

#### Horizontal Scaling

```yaml
# Kubernetes HPA configuration
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: backend-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: backend
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

#### Auto-scaling Rules

- **Scale-up**: CPU > 70% for 2 minutes
- **Scale-down**: CPU < 30% for 10 minutes
- **Max pods**: 10 per service
- **Graceful shutdown**: 30 seconds

---

## Contributing Guidelines

### Issue Reporting

#### Bug Reports

When reporting bugs, please include:

1. **Clear title**: Short description of the issue
2. **Environment**: OS, Python/Node versions, browser
3. **Steps to reproduce**: Detailed reproduction steps
4. **Expected behavior**: What should happen
5. **Actual behavior**: What actually happens
6. **Screenshots**: If UI-related
7. **Logs**: Relevant error messages
8. **Code snippets**: Minimal reproduction case

#### Feature Requests

For new features:

1. **Use case**: Why is this feature needed?
2. **Proposed solution**: How should it work?
3. **Alternatives**: Considered alternatives
4. **Scope**: What's in and out of scope?
5. **Priority**: High/Medium/Low with justification

### Feature Requests

1. **Search existing issues**: Avoid duplicates
2. **Use issue templates**: Follow the provided format
3. **Provide context**: Explain the use case
4. **Consider alternatives**: Suggest workarounds
5. **Be patient**: Maintainers will review and respond

### Security Vulnerabilities

#### Responsible Disclosure

If you discover a security vulnerability:

1. **Do NOT** create a public issue
2. **Email** security@suna.so with details
3. **Include**:
   - Description of vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (optional)

#### Response Timeline

- **Initial response**: 24 hours
- **Assessment**: 48-72 hours
- **Fix deployment**: Based on severity
- **Public disclosure**: After fix is deployed

### Community Engagement

#### Getting Help

- **Documentation**: Check docs/ and wiki first
- **Issues**: Search existing issues
- **Discussions**: Use GitHub Discussions
- **Discord**: Join our community Discord

#### Contributing Code

1. **Fork the repository**
2. **Create a feature branch**
3. **Make your changes**
4. **Run tests and linting**
5. **Submit a pull request**
6. **Address review feedback**

#### Recognition

Contributors are recognized in:
- CONTRIBUTORS.md file
- Release notes
- Community highlights

---

## Additional Resources

- **Repository:** [https://github.com/kortix-ai/suna](https://github.com/kortix-ai/suna)
- **Website:** [https://www.suna.so](https://www.suna.so)
- **Documentation:** See `/doc` and `/docs` directories
- **Contributing:** See `CONTRIBUTING.md`
