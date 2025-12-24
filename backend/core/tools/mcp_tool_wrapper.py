from typing import Any, Dict, List, Optional
from core.agentpress.tool import Tool, ToolResult, ToolSchema, SchemaType, tool_metadata
from core.mcp_module import mcp_service
from core.utils.logger import logger
import inspect
import asyncio
import time
import hashlib
import json
from core.tools.utils.mcp_connection_manager import MCPConnectionManager
from core.tools.utils.custom_mcp_handler import CustomMCPHandler
from core.tools.utils.dynamic_tool_builder import DynamicToolBuilder
from core.tools.utils.mcp_tool_executor import MCPToolExecutor
from core.services import redis as redis_service

# AgentCore Gateway Integration
try:
    from core.agentcore import (
        AgentCoreGatewayAdapter,
        GatewayError,
        MCPServerNotFoundError,
        MCPToolInvocationError,
        ValidationError as AgentCoreValidationError,
        get_config,
    )
    GATEWAY_AVAILABLE = True
except ImportError:
    GATEWAY_AVAILABLE = False
    logger.debug("AgentCore Gateway not available - using direct MCP only")


class MCPSchemaRedisCache:
    def __init__(self, ttl_seconds: int = 3600, key_prefix: str = "mcp_schema:"):
        self._ttl = ttl_seconds
        self._key_prefix = key_prefix
        self._redis_client = None
    
    async def _ensure_redis(self):
        if not self._redis_client:
            try:
                self._redis_client = await redis_service.get_client()
            except Exception as e:
                logger.warning(f"Redis not available for MCP cache: {e}")
                return False
        return True
    
    def _get_cache_key(self, config: Dict[str, Any]) -> str:
        config_str = json.dumps(config, sort_keys=True)
        config_hash = hashlib.md5(config_str.encode()).hexdigest()
        return f"{self._key_prefix}{config_hash}"
    
    async def get(self, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not await self._ensure_redis():
            return None
            
        try:
            key = self._get_cache_key(config)
            cached_data = await self._redis_client.get(key)
            
            if cached_data:
                logger.debug(f"⚡ Redis cache hit for MCP: {config.get('name', config.get('qualifiedName', 'Unknown'))}")
                return json.loads(cached_data)
            else:
                logger.debug(f"Redis cache miss for MCP: {config.get('name', config.get('qualifiedName', 'Unknown'))}")
                return None
                
        except Exception as e:
            logger.warning(f"Error reading from Redis cache: {e}")
            return None
    
    async def set(self, config: Dict[str, Any], data: Dict[str, Any]):
        if not await self._ensure_redis():
            return
            
        try:
            key = self._get_cache_key(config)
            serialized_data = json.dumps(data)
            
            await self._redis_client.setex(key, self._ttl, serialized_data)
            logger.debug(f"✅ Cached MCP schema in Redis for {config.get('name', config.get('qualifiedName', 'Unknown'))} (TTL: {self._ttl}s)")
            
        except Exception as e:
            logger.warning(f"Error writing to Redis cache: {e}")
    
    async def clear_pattern(self, pattern: Optional[str] = None):
        if not await self._ensure_redis():
            return
        try:
            if pattern:
                search_pattern = f"{self._key_prefix}{pattern}*"
            else:
                search_pattern = f"{self._key_prefix}*"
            
            keys = []
            async for key in self._redis_client.scan_iter(match=search_pattern):
                keys.append(key)
            
            if keys:
                await self._redis_client.delete(*keys)
                logger.debug(f"Cleared {len(keys)} MCP schema cache entries from Redis")
            
        except Exception as e:
            logger.warning(f"Error clearing Redis cache: {e}")
    
    async def get_stats(self) -> Dict[str, Any]:
        if not await self._ensure_redis():
            return {"available": False}
        try:
            count = 0
            async for _ in self._redis_client.scan_iter(match=f"{self._key_prefix}*"):
                count += 1
            
            return {
                "available": True,
                "cached_schemas": count,
                "ttl_seconds": self._ttl,
                "key_prefix": self._key_prefix
            }
        except Exception as e:
            logger.warning(f"Error getting cache stats: {e}")
            return {"available": False, "error": str(e)}


_redis_cache = MCPSchemaRedisCache(ttl_seconds=3600)

@tool_metadata(
    display_name="MCP Tool Wrapper",
    description="Internal wrapper for MCP external tool integration",
    icon="Package",
    color="bg-gray-100 dark:bg-gray-800/50",
    weight=1000,
    visible=False
)
class MCPToolWrapper(Tool):
    def __init__(
        self,
        mcp_configs: Optional[List[Dict[str, Any]]] = None,
        use_cache: bool = True,
        use_gateway: bool = False,
        account_id: Optional[str] = None,
        fallback_to_direct_mcp: bool = True
    ):
        """
        Initialize MCP Tool Wrapper with optional Gateway integration.

        Args:
            mcp_configs: List of MCP server configurations
            use_cache: Enable Redis caching for MCP schemas
            use_gateway: Enable AgentCore Gateway for MCP deployment
            account_id: Account ID for tenant isolation (required for Gateway)
            fallback_to_direct_mcp: Fall back to direct MCP if Gateway fails
        """
        self.mcp_manager = mcp_service
        self.mcp_configs = mcp_configs or []
        self._initialized = False
        self._schemas: Dict[str, List[ToolSchema]] = {}
        self._dynamic_tools = {}
        self._custom_tools = {}
        self.use_cache = use_cache

        # Gateway integration
        self.use_gateway = use_gateway and GATEWAY_AVAILABLE
        self.account_id = account_id
        self.fallback_to_direct_mcp = fallback_to_direct_mcp
        self._gateway_adapter: Optional[AgentCoreGatewayAdapter] = None
        self._gateway_deployments: Dict[str, str] = {}  # service_name -> deployment_id
        self._gateway_enabled_for_service: Dict[str, bool] = {}

        self.connection_manager = MCPConnectionManager()
        self.custom_handler = CustomMCPHandler(self.connection_manager)
        self.tool_builder = DynamicToolBuilder()
        self.tool_executor = None

        # Initialize Gateway adapter if enabled
        if self.use_gateway:
            self._initialize_gateway_adapter()

        super().__init__()

    def _initialize_gateway_adapter(self) -> None:
        """Initialize AgentCore Gateway adapter if available and configured"""
        if not GATEWAY_AVAILABLE:
            logger.warning("Gateway requested but AgentCore not available - will use direct MCP")
            self.use_gateway = False
            return

        try:
            config = get_config()
            if not config.gateway_enabled:
                logger.debug("Gateway disabled in AgentCore config - will use direct MCP")
                self.use_gateway = False
                return

            if not self.account_id:
                logger.warning("account_id required for Gateway - will use direct MCP")
                self.use_gateway = False
                return

            self._gateway_adapter = AgentCoreGatewayAdapter(config=config)
            logger.info(f"✓ AgentCore Gateway adapter initialized for account {self.account_id}")

        except Exception as e:
            logger.warning(f"Failed to initialize Gateway adapter: {e} - will use direct MCP")
            self.use_gateway = False

    async def _ensure_initialized(self):
        if not self._initialized:
            try:
                await self._initialize_servers()
            except Exception as e:
                logger.error(f"Error during MCP server initialization: {e} (continuing with available servers)")
            
            try:
                await self._create_dynamic_tools()
            except Exception as e:
                logger.error(f"Error creating dynamic MCP tools: {e} (continuing with available tools)")
            
            # Mark as initialized even if some servers failed - allows execution to continue
            self._initialized = True
    
    async def _initialize_servers(self):
        start_time = time.time()

        standard_configs = [cfg for cfg in self.mcp_configs if not cfg.get('isCustom', False)]
        custom_configs = [cfg for cfg in self.mcp_configs if cfg.get('isCustom', False)]

        cached_configs = []
        cached_tools_data = []

        initialization_tasks = []

        # Deploy standard MCP servers to Gateway (if enabled)
        if self.use_gateway and self._gateway_adapter and standard_configs:
            await self._deploy_servers_to_gateway(standard_configs)

        if standard_configs:
            for config in standard_configs:
                if self.use_cache:
                    cached_data = await _redis_cache.get(config)
                    if cached_data:
                        cached_configs.append(config.get('qualifiedName', 'Unknown'))
                        cached_tools_data.append(cached_data)
                        continue

                task = self._initialize_single_standard_server(config)
                initialization_tasks.append(('standard', config, task))

        if custom_configs:
            for config in custom_configs:
                if self.use_cache:
                    cached_data = await _redis_cache.get(config)
                    if cached_data:
                        cached_configs.append(config.get('name', 'Unknown'))
                        cached_tools_data.append(cached_data)
                        continue

                task = self._initialize_single_custom_mcp(config)
                initialization_tasks.append(('custom', config, task))

        if cached_tools_data:
            logger.debug(f"⚡ Loaded {len(cached_configs)} MCP schemas from Redis cache: {', '.join(cached_configs)}")
            for cached_data in cached_tools_data:
                try:
                    if cached_data.get('type') == 'standard':
                        logger.debug("Standard MCP tools found in cache but require connection to restore")
                    elif cached_data.get('type') == 'custom':
                        custom_tools = cached_data.get('tools', {})
                        if custom_tools:
                            self.custom_handler.custom_tools.update(custom_tools)
                            logger.debug(f"Restored {len(custom_tools)} custom tools from cache")
                except Exception as e:
                    logger.warning(f"Failed to restore cached tools: {e}")

        if initialization_tasks:
            logger.debug(f"🚀 Initializing {len(initialization_tasks)} MCP servers in parallel (cache enabled: {self.use_cache})...")

            tasks = [task for _, _, task in initialization_tasks]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            successful = 0
            failed = 0

            for i, result in enumerate(results):
                task_type, config, _ = initialization_tasks[i]
                if isinstance(result, Exception):
                    # This shouldn't happen anymore since we return error dicts, but handle it just in case
                    failed += 1
                    config_name = config.get('name', config.get('qualifiedName', 'Unknown'))
                    logger.error(f"Failed to initialize MCP server '{config_name}': {result}")
                elif isinstance(result, dict):
                    if result.get('success', False):
                        successful += 1
                        if self.use_cache and result:
                            await _redis_cache.set(config, result)
                    else:
                        failed += 1
                        error_msg = result.get('error', 'Unknown error')
                        config_name = result.get('config_name', config.get('name', config.get('qualifiedName', 'Unknown')))
                        logger.warning(f"MCP server '{config_name}' failed to initialize: {error_msg} (continuing with other servers)")
                else:
                    # Unexpected result type, but don't fail
                    logger.warning(f"Unexpected result type from MCP initialization: {type(result)}")
                    failed += 1

            elapsed_time = time.time() - start_time
            logger.debug(f"⚡ MCP initialization completed in {elapsed_time:.2f}s - {successful} successful, {failed} failed, {len(cached_configs)} from cache")
        else:
            if cached_configs:
                elapsed_time = time.time() - start_time
                logger.debug(f"⚡ All {len(cached_configs)} MCP schemas loaded from Redis cache in {elapsed_time:.2f}s - instant startup!")
            else:
                logger.debug("No MCP servers to initialize")

    async def _deploy_servers_to_gateway(self, standard_configs: List[Dict[str, Any]]) -> None:
        """
        Deploy standard MCP servers to AgentCore Gateway.

        Args:
            standard_configs: List of standard MCP configurations
        """
        if not self._gateway_adapter or not self.account_id:
            return

        logger.info(f"🚀 Deploying {len(standard_configs)} MCP servers to Gateway...")

        for config in standard_configs:
            service_name = config.get('qualifiedName', config.get('name', 'unknown'))

            # Check if Gateway is enabled for this service
            # Can be controlled via config metadata: config.get('gateway_enabled', True)
            gateway_enabled = config.get('gateway_enabled', True)
            self._gateway_enabled_for_service[service_name] = gateway_enabled

            if not gateway_enabled:
                logger.debug(f"Gateway disabled for {service_name} - using direct MCP")
                continue

            try:
                # Convert MCP config to Gateway format
                mcp_config = self._convert_config_to_gateway_format(config)

                # Deploy to Gateway
                deployment_id = await self._gateway_adapter.deploy_mcp_server(
                    mcp_config=mcp_config,
                    account_id=self.account_id
                )

                self._gateway_deployments[service_name] = deployment_id
                logger.info(f"✓ Deployed {service_name} to Gateway: {deployment_id}")

            except (AgentCoreValidationError, GatewayError) as e:
                logger.warning(f"Gateway deployment failed for {service_name}: {e} - will use direct MCP")
                self._gateway_enabled_for_service[service_name] = False
            except Exception as e:
                logger.error(f"Unexpected error deploying {service_name} to Gateway: {e} - will use direct MCP")
                self._gateway_enabled_for_service[service_name] = False

    def _convert_config_to_gateway_format(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert MCP configuration to Gateway format.

        Args:
            config: Original MCP configuration

        Returns:
            Gateway-compatible configuration
        """
        service_name = config.get('qualifiedName', config.get('name', 'unknown'))

        # Determine auth type
        transport = config.get('transport', 'sse')
        env = config.get('env', {})

        auth_type = 'none'
        oauth_config = None

        if env.get('GITHUB_TOKEN') or env.get('access_token'):
            auth_type = 'oauth2'
            oauth_config = {
                'authorization_url': 'https://github.com/login/oauth/authorize',
                'token_url': 'https://github.com/login/oauth/access_token',
                'callback_path': '/api/mcp/callback'
            }
        elif env.get('API_KEY'):
            auth_type = 'api_key'

        return {
            'name': service_name.split('/')[0] if '/' in service_name else service_name,
            'display_name': service_name,
            'description': f"MCP service for {service_name}",
            'category': 'third_party',
            'auth_type': auth_type,
            'oauth_config': oauth_config,
            'mcp_server_config': {
                'transport': transport,
                'url': config.get('url'),
                'command': config.get('command'),
                'args': config.get('args', []),
            },
            'features': [],
            'requires_callback': auth_type == 'oauth2'
        }
    
    async def _initialize_single_standard_server(self, config: Dict[str, Any]):
        try:
            logger.debug(f"Connecting to standard MCP server: {config['qualifiedName']}")
            await self.mcp_manager.connect_server(config)
            logger.debug(f"✓ Connected to MCP server: {config['qualifiedName']}")
            
            tools_info = self.mcp_manager.get_all_tools_openapi()
            return {'tools': tools_info, 'type': 'standard', 'timestamp': time.time(), 'success': True}
        except Exception as e:
            config_name = config.get('qualifiedName', config.get('name', 'Unknown'))
            logger.error(f"✗ Failed to connect to MCP server {config_name}: {e}")
            # Return error info instead of raising - allows execution to continue
            return {'tools': [], 'type': 'standard', 'timestamp': time.time(), 'success': False, 'error': str(e), 'config_name': config_name}
    
    async def _initialize_single_custom_mcp(self, config: Dict[str, Any]):
        try:
            logger.debug(f"Initializing custom MCP: {config.get('name', 'Unknown')}")
            await self.custom_handler._initialize_single_custom_mcp(config)
            logger.debug(f"✓ Initialized custom MCP: {config.get('name', 'Unknown')}")
            
            custom_tools = self.custom_handler.get_custom_tools()
            return {'tools': custom_tools, 'type': 'custom', 'timestamp': time.time(), 'success': True}
        except Exception as e:
            config_name = config.get('name', 'Unknown')
            logger.error(f"✗ Failed to initialize custom MCP {config_name}: {e}")
            # Return error info instead of raising - allows execution to continue
            return {'tools': {}, 'type': 'custom', 'timestamp': time.time(), 'success': False, 'error': str(e), 'config_name': config_name}
            
    async def _initialize_standard_servers(self, standard_configs: List[Dict[str, Any]]):
        pass
    
    async def _create_dynamic_tools(self):
        try:
            available_tools = self.mcp_manager.get_all_tools_openapi()
            custom_tools = self.custom_handler.get_custom_tools()
            
            logger.debug(f"MCPManager returned {len(available_tools)} standard tools, Custom handler returned {len(custom_tools)} custom tools")
            
            self._custom_tools = custom_tools
            
            self.tool_executor = MCPToolExecutor(custom_tools, self)
            
            dynamic_methods = self.tool_builder.create_dynamic_methods(
                available_tools, 
                custom_tools, 
                self._execute_mcp_tool
            )
            
            self._dynamic_tools = self.tool_builder.get_dynamic_tools()
            
            # Set methods on the instance - Python will automatically bind them when accessed
            for method_name, method in dynamic_methods.items():
                # Set the method directly - it will be bound when accessed via getattr
                setattr(self, method_name, method)
                # Verify the method has tool_schemas attribute
                if not hasattr(method, 'tool_schemas'):
                    logger.warning(f"Dynamic method {method_name} missing tool_schemas attribute")
            
            # Get schemas from the builder and merge them
            builder_schemas = self.tool_builder.get_schemas()
            self._schemas.update(builder_schemas)
            
            # Also ensure schemas are registered from the methods themselves
            self._register_schemas()
            
            logger.debug(f"Created {len(self._dynamic_tools)} dynamic MCP tool methods with {len(self._schemas)} OpenAPI schemas")
            
        except Exception as e:
            logger.error(f"Error creating dynamic MCP tools: {e}", exc_info=True)
    
    def _register_schemas(self):
        """Register schemas from all methods, including dynamically created MCP tools."""
        # First, register schemas from any decorated methods (standard Tool base class behavior)
        for name, method in inspect.getmembers(self, predicate=inspect.ismethod):
            if hasattr(method, 'tool_schemas'):
                if name not in self._schemas:
                    self._schemas[name] = []
                # Merge schemas if method has multiple
                if isinstance(method.tool_schemas, list):
                    self._schemas[name].extend(method.tool_schemas)
                else:
                    self._schemas[name].append(method.tool_schemas)
        
        # Then, ensure all dynamic MCP tools have their schemas registered
        if hasattr(self, '_dynamic_tools') and self._dynamic_tools:
            for tool_name, tool_data in self._dynamic_tools.items():
                method_name = tool_data.get('method_name')
                if not method_name:
                    continue
                
                # Get schema from tool_data or from the method itself
                schema = tool_data.get('schema')
                method = tool_data.get('method')
                
                # Prefer schema from tool_data, fallback to method's tool_schemas
                if schema:
                    if method_name not in self._schemas:
                        self._schemas[method_name] = []
                    # Only add if not already present
                    if schema not in self._schemas[method_name]:
                        self._schemas[method_name].append(schema)
                elif method and hasattr(method, 'tool_schemas'):
                    if method_name not in self._schemas:
                        self._schemas[method_name] = []
                    if isinstance(method.tool_schemas, list):
                        for s in method.tool_schemas:
                            if s not in self._schemas[method_name]:
                                self._schemas[method_name].append(s)
                    else:
                        if method.tool_schemas not in self._schemas[method_name]:
                            self._schemas[method_name].append(method.tool_schemas)
        
        # Also check builder schemas as a fallback
        if hasattr(self, 'tool_builder') and self.tool_builder:
            builder_schemas = self.tool_builder.get_schemas()
            for method_name, schema_list in builder_schemas.items():
                if method_name not in self._schemas:
                    self._schemas[method_name] = []
                for schema in schema_list:
                    if schema not in self._schemas[method_name]:
                        self._schemas[method_name].append(schema)
        
        logger.debug(f"Registration complete for MCPToolWrapper - total schemas: {len(self._schemas)}")
    
    def get_schemas(self) -> Dict[str, List[ToolSchema]]:
        # logger.debug(f"get_schemas called - returning {len(self._schemas)} schemas")
        # for method_name in self._schemas:
        #     # logger.debug(f"  - Schema available for: {method_name}")
        return self._schemas
    
    def __getattr__(self, name: str):
        """Get dynamically created MCP tool methods.
        
        This allows accessing MCP tools as methods on the wrapper instance.
        The method name may differ from the original tool name due to parsing.
        """
        # First check if it's a direct attribute (shouldn't happen, but safety check)
        if hasattr(self, name):
            return getattr(self, name)
        
        # Try to find via tool_builder
        if hasattr(self, 'tool_builder') and self.tool_builder:
            method = self.tool_builder.find_method_by_name(name)
            if method:
                # Bind the method to this instance if it's not already bound
                if callable(method):
                    return method
        
        # Try to find in dynamic_tools by method_name
        if hasattr(self, '_dynamic_tools') and self._dynamic_tools:
            for tool_data in self._dynamic_tools.values():
                if tool_data.get('method_name') == name:
                    method = tool_data.get('method')
                    if method:
                        return method
            
            # Try with hyphens instead of underscores
            name_with_hyphens = name.replace('_', '-')
            for tool_name, tool_data in self._dynamic_tools.items():
                if tool_data.get('method_name') == name or tool_name == name_with_hyphens:
                    method = tool_data.get('method')
                    if method:
                        return method
        
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'. Available MCP tools: {list(self._schemas.keys()) if hasattr(self, '_schemas') else 'not initialized'}")
    
    def get_original_tool_name(self, method_name: str) -> Optional[str]:
        """Get the original MCP tool name from a method name.
        
        Args:
            method_name: The method name (e.g., 'search')
            
        Returns:
            The original tool name (e.g., 'youtube_search') or None if not found
        """
        if hasattr(self, '_dynamic_tools') and self._dynamic_tools:
            for tool_name, tool_data in self._dynamic_tools.items():
                if tool_data.get('method_name') == method_name:
                    return tool_data.get('original_tool_name', tool_name)
        return None
    
    async def initialize_and_register_tools(self, tool_registry=None):
        await self._ensure_initialized()
        if tool_registry and self._dynamic_tools:
            logger.debug(f"Updating tool registry with {len(self._dynamic_tools)} MCP tools")
            
    async def get_available_tools(self) -> List[Dict[str, Any]]:
        """Get list of available MCP tools in OpenAPI format."""
        await self._ensure_initialized()
        return self.mcp_manager.get_all_tools_openapi()
    
    async def _execute_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
        """Execute an MCP tool by its original tool name.

        Args:
            tool_name: The original MCP tool name (e.g., 'youtube_search' or 'custom_server_tool_name')
            arguments: The arguments to pass to the tool

        Returns:
            ToolResult with the execution result
        """
        await self._ensure_initialized()

        if not self.tool_executor:
            logger.error("Tool executor not initialized")
            return ToolResult(success=False, output="MCP tool executor not initialized")

        # Try Gateway first if enabled and available
        if self.use_gateway and self._gateway_adapter:
            try:
                result = await self._execute_via_gateway(tool_name, arguments)
                if result.success:
                    return result
                # If Gateway returned failure but no exception, fall through to direct MCP
                logger.debug(f"Gateway execution failed for {tool_name}, falling back to direct MCP")
            except Exception as e:
                logger.debug(f"Gateway execution error for {tool_name}: {e}, falling back to direct MCP")

        # Fallback to direct MCP
        return await self.tool_executor.execute_tool(tool_name, arguments)

    async def _execute_via_gateway(self, tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
        """
        Execute MCP tool via AgentCore Gateway.

        Args:
            tool_name: The original MCP tool name
            arguments: The arguments to pass to the tool

        Returns:
            ToolResult with the execution result

        Raises:
            GatewayError: If Gateway execution fails
        """
        # Determine which service the tool belongs to
        # Tool names are typically in format: service_name/tool_name
        service_name = self._get_service_name_for_tool(tool_name)

        if not service_name:
            logger.debug(f"Could not determine service for tool {tool_name}, using direct MCP")
            return ToolResult(success=False, output=f"Service not found for tool: {tool_name}")

        # Check if service is deployed to Gateway
        if service_name not in self._gateway_deployments:
            logger.debug(f"Service {service_name} not deployed to Gateway, using direct MCP")
            return ToolResult(success=False, output=f"Service not deployed to Gateway: {service_name}")

        # Check if Gateway is enabled for this service
        if not self._gateway_enabled_for_service.get(service_name, True):
            logger.debug(f"Gateway disabled for {service_name}, using direct MCP")
            return ToolResult(success=False, output=f"Gateway disabled for service: {service_name}")

        deployment_id = self._gateway_deployments[service_name]

        # Get credentials if available (from config env)
        credentials = None
        for config in self.mcp_configs:
            if config.get('qualifiedName', config.get('name')) == service_name:
                env = config.get('env', {})
                if env.get('access_token'):
                    credentials = {'access_token': env.get('access_token')}
                elif env.get('api_key'):
                    credentials = {'api_key': env.get('api_key')}
                break

        try:
            # Invoke tool via Gateway
            gateway_result = await self._gateway_adapter.invoke_mcp_tool(
                gateway_deployment_id=deployment_id,
                tool_name=tool_name,
                parameters=arguments,
                credentials=credentials
            )

            # Convert Gateway result to ToolResult
            return ToolResult(
                success=gateway_result.success,
                content=gateway_result.output if gateway_result.success else gateway_result.error,
                metadata={
                    'gateway_deployment_id': deployment_id,
                    'service_name': service_name,
                    'execution_time_seconds': gateway_result.execution_time_seconds,
                    'is_cached': gateway_result.is_cached,
                }
            )

        except (MCPServerNotFoundError, MCPToolInvocationError) as e:
            logger.warning(f"Gateway invocation failed for {tool_name}: {e}")
            return ToolResult(success=False, output=f"Gateway invocation failed: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected Gateway error for {tool_name}: {e}")
            raise

    def _get_service_name_for_tool(self, tool_name: str) -> Optional[str]:
        """
        Determine the service name for a given tool name.

        Args:
            tool_name: The tool name (e.g., 'github_search_issues' or 'search')

        Returns:
            Service name (e.g., 'github') or None if not found
        """
        # Try to extract from tool name (common patterns)
        # e.g., 'github_search_issues' -> 'github'
        parts = tool_name.split('_')
        if len(parts) > 1:
            potential_service = parts[0]
            # Check if this service exists in our configs
            for config in self.mcp_configs:
                service_name = config.get('qualifiedName', config.get('name', ''))
                if service_name.startswith(potential_service):
                    return potential_service

        # Check custom tools
        if hasattr(self, '_custom_tools'):
            for custom_tool_name, tool_data in self._custom_tools.items():
                if tool_name == custom_tool_name:
                    # Found in custom tools, return the service name from config
                    for config in self.mcp_configs:
                        if config.get('isCustom') and config.get('name') == custom_tool_name:
                            return config.get('name')

        return None
    
    def validate_tool_registration(self) -> Dict[str, Any]:
        """Validate that all MCP tools are properly registered with schemas.
        
        Returns:
            Dict with validation results including counts and any issues
        """
        validation_result = {
            'total_schemas': len(self._schemas),
            'total_dynamic_tools': len(self._dynamic_tools) if hasattr(self, '_dynamic_tools') else 0,
            'schemas_with_openapi': 0,
            'missing_schemas': [],
            'valid': True
        }
        
        # Check that all dynamic tools have schemas
        if hasattr(self, '_dynamic_tools') and self._dynamic_tools:
            for tool_name, tool_data in self._dynamic_tools.items():
                method_name = tool_data.get('method_name')
                if method_name:
                    if method_name in self._schemas:
                        schema_list = self._schemas[method_name]
                        # Check if any schema is OpenAPI
                        has_openapi = any(
                            s.schema_type == SchemaType.OPENAPI 
                            for s in schema_list
                        )
                        if has_openapi:
                            validation_result['schemas_with_openapi'] += 1
                        else:
                            validation_result['missing_schemas'].append({
                                'method_name': method_name,
                                'tool_name': tool_name,
                                'issue': 'No OpenAPI schema found'
                            })
                            validation_result['valid'] = False
                    else:
                        validation_result['missing_schemas'].append({
                            'method_name': method_name,
                            'tool_name': tool_name,
                            'issue': 'No schema registered'
                        })
                        validation_result['valid'] = False
        
        return validation_result
    
    async def cleanup(self):
        """Clean up MCP connections and release memory."""
        if self._initialized:
            try:
                await self.mcp_manager.disconnect_all()
            except Exception as e:
                logger.error(f"Error during MCP cleanup: {str(e)}")
            finally:
                self._initialized = False
        
        # Clear local caches to help garbage collection
        self._schemas.clear()
        self._dynamic_tools.clear()
        self._custom_tools.clear()
        
        # Clean up connection manager
        if hasattr(self, 'connection_manager'):
            self.connection_manager.cleanup()
        
        # Clean up custom handler
        if hasattr(self, 'custom_handler') and hasattr(self.custom_handler, 'custom_tools'):
            self.custom_handler.custom_tools.clear() 