from typing import Optional, Union
import uuid
import asyncio

from core.agentpress.thread_manager import ThreadManager
from core.agentpress.tool import Tool
from daytona_sdk import AsyncSandbox
from core.sandbox.sandbox import get_or_start_sandbox, create_sandbox, delete_sandbox
from core.utils.logger import logger
from core.utils.files_utils import clean_path
from core.utils.config import config

# AgentCore imports - lazy loaded to avoid errors when not enabled
_agentcore_config = None
_agentcore_code_adapter = None
_agentcore_browser_adapter = None


def _get_agentcore_config():
    """Lazy load AgentCore configuration."""
    global _agentcore_config
    if _agentcore_config is None:
        try:
            from core.agentcore import get_config
            _agentcore_config = get_config()
        except ImportError:
            logger.debug("AgentCore module not available")
            _agentcore_config = False
    return _agentcore_config


def _get_agentcore_code_adapter():
    """Lazy load AgentCore Code Interpreter adapter."""
    global _agentcore_code_adapter
    if _agentcore_code_adapter is None:
        try:
            from core.agentcore import AgentCoreCodeInterpreterAdapter
            cfg = _get_agentcore_config()
            if cfg and cfg.code_interpreter_enabled:
                _agentcore_code_adapter = AgentCoreCodeInterpreterAdapter(config=cfg)
            else:
                _agentcore_code_adapter = False
        except ImportError:
            logger.debug("AgentCore Code Interpreter adapter not available")
            _agentcore_code_adapter = False
    return _agentcore_code_adapter


def _get_agentcore_browser_adapter():
    """Lazy load AgentCore Browser adapter."""
    global _agentcore_browser_adapter
    if _agentcore_browser_adapter is None:
        try:
            from core.agentcore import AgentCoreBrowserAdapter
            cfg = _get_agentcore_config()
            if cfg and cfg.browser_enabled:
                _agentcore_browser_adapter = AgentCoreBrowserAdapter(config=cfg)
            else:
                _agentcore_browser_adapter = False
        except ImportError:
            logger.debug("AgentCore Browser adapter not available")
            _agentcore_browser_adapter = False
    return _agentcore_browser_adapter

class SandboxToolsBase(Tool):
    """
    Base class for all sandbox tools that provides project-based sandbox access.

    Supports two backends:
    1. AgentCode (AWS Bedrock AgentCore): Serverless code execution and browser automation
    2. Daytona (Legacy): Container-based sandbox environment

    Backend selection is based on AgentCore configuration and feature flags.
    Falls back to Daytona when AgentCore is unavailable or disabled.
    """

    # Class variable to track if sandbox URLs have been printed
    _urls_printed = False

    # AgentCore session storage (shared across all instances)
    _agentcore_sessions: dict = {}

    def __init__(self, project_id: str, thread_manager: Optional[ThreadManager] = None):
        super().__init__()
        self.project_id = project_id
        self.thread_manager = thread_manager
        self.workspace_path = "/workspace"
        self._sandbox = None
        self._sandbox_id = None
        self._sandbox_pass = None
        self._sandbox_url = None
        self._backend_type = None  # 'agentcore' or 'daytona'
        self._agentcore_session_id = None

    def _use_agentcore(self) -> bool:
        """
    Determine if AgentCore should be used as the backend.

    Checks:
    - AgentCore module is available
    - At least one AgentCore feature is enabled (Code Interpreter or Browser)
    - Not in LOCAL environment (unless explicitly enabled)

    Returns:
        True if AgentCore should be used, False for Daytona

    Requirements: 8.1, 8.2, 8.3, 9.1, 9.2
    """
        cfg = _get_agentcore_config()
        if not cfg:
            return False

        # Check if AgentCore features are enabled
        if not (cfg.code_interpreter_enabled or cfg.browser_enabled):
            return False

        # In LOCAL environment, AgentCore is disabled by default
        # unless explicitly enabled via environment variable
        if cfg.environment == "local":
            return False

        return True

    async def _ensure_agentcore_session(self, session_type: str = "code") -> str:
        """
        Ensure we have a valid AgentCore session for the project.

        Args:
            session_type: Type of session - 'code' for Code Interpreter, 'browser' for Browser

        Returns:
            The session ID

        Requirements: 10.1, 10.2, 10.3
        """
        session_key = f"{self.project_id}:{session_type}"

        # Check if we already have a cached session
        if session_key in self._agentcore_sessions:
            session_data = self._agentcore_sessions[session_key]

            # Verify session is still valid (check expiry)
            from datetime import datetime, timedelta
            created_at = session_data.get('created_at')
            if created_at:
                session_age = (datetime.utcnow() - created_at).total_seconds()
                cfg = _get_agentcore_config()
                timeout = (
                    cfg.code_interpreter_session_timeout_seconds if session_type == 'code'
                    else cfg.browser_session_timeout_seconds
                )
                # Use 90% of timeout as session reuse threshold
                if session_age < (timeout * 0.9):
                    logger.debug(f"Reusing existing AgentCore {session_type} session: {session_data['session_id']}")
                    return session_data['session_id']

        # Create new session
        from core.agentcore import CodeInterpreterSession, BrowserSession
        from datetime import datetime

        try:
            if session_type == "code":
                adapter = _get_agentcore_code_adapter()
                if not adapter:
                    raise ValueError("Code Interpreter adapter not available")

                # Start session via adapter
                session_id = await adapter.start_session(
                    project_id=self.project_id,
                    timeout_seconds=900,  # Default 15 minutes
                    memory_limit_mb=1024
                )

                # Store session metadata
                self._agentcore_sessions[session_key] = {
                    'session_id': session_id,
                    'created_at': datetime.utcnow(),
                    'session_type': 'code'
                }

                logger.info(f"Created new AgentCore Code Interpreter session: {session_id}")
                return session_id

            elif session_type == "browser":
                adapter = _get_agentcore_browser_adapter()
                if not adapter:
                    raise ValueError("Browser adapter not available")

                # Start session via adapter
                session_id = await adapter.start_session(
                    project_id=self.project_id,
                    timeout_seconds=900,  # Default 15 minutes
                    viewport={"width": 1920, "height": 1080}
                )

                # Store session metadata
                self._agentcore_sessions[session_key] = {
                    'session_id': session_id,
                    'created_at': datetime.utcnow(),
                    'session_type': 'browser'
                }

                logger.info(f"Created new AgentCore Browser session: {session_id}")
                return session_id

            else:
                raise ValueError(f"Unknown session type: {session_type}")

        except Exception as e:
            logger.error(f"Error creating AgentCore {session_type} session: {str(e)}")
            raise e

    async def _ensure_sandbox(self) -> Union[AsyncSandbox, str]:
        """
        Ensure we have a valid sandbox instance, selecting the appropriate backend.

        Backend Selection:
        1. Try AgentCore if enabled and available
        2. Fall back to Daytona if AgentCore fails or is disabled
        3. Raise exception if both backends fail

        Returns:
            AsyncSandbox for Daytona backend, or session_id for AgentCore backend

        Requirements: 8.1, 8.2, 8.3, 9.1, 9.2, 9.3
        """
        if self._sandbox is None:
            # Determine which backend to use
            use_agentcore = self._use_agentcore()

            if use_agentcore:
                try:
                    logger.debug(f"Using AgentCore backend for project {self.project_id}")
                    self._backend_type = 'agentcore'

                    # Create/reuse AgentCore session
                    session_id = await self._ensure_agentcore_session("code")
                    self._agentcore_session_id = session_id

                    # For AgentCore, we store the session ID instead of AsyncSandbox
                    self._sandbox_id = session_id

                    # Check if fallback is enabled
                    cfg = _get_agentcore_config()
                    if cfg and cfg.fallback_to_legacy_sandbox:
                        logger.warning("Fallback to legacy sandbox is enabled, but AgentCore is available")

                except Exception as agentcore_error:
                    # Check if we should fall back to Daytona
                    cfg = _get_agentcore_config()
                    if cfg and cfg.fallback_to_legacy_sandbox:
                        logger.warning(
                            f"AgentCore backend failed, falling back to Daytona: {str(agentcore_error)}"
                        )
                        self._backend_type = 'daytona'
                        await self._ensure_daytona_sandbox()
                    else:
                        # Re-raise the error if fallback is disabled
                        logger.error(f"AgentCore backend failed and fallback is disabled: {str(agentcore_error)}")
                        raise agentcore_error
            else:
                # Use Daytona backend
                logger.debug(f"Using Daytona backend for project {self.project_id}")
                self._backend_type = 'daytona'
                await self._ensure_daytona_sandbox()

        return self._sandbox

    async def _ensure_daytona_sandbox(self) -> AsyncSandbox:
        """Ensure we have a valid Daytona sandbox instance.

        If the project does not yet have a sandbox, create it lazily and persist
        the metadata to the `projects` table so subsequent calls can reuse it.
        """
        if self._sandbox is None:
            try:
                # Get database client
                client = await self.thread_manager.db.client

                # Get project data
                project = await client.table('projects').select('*').eq('project_id', self.project_id).execute()
                if not project.data or len(project.data) == 0:
                    raise ValueError(f"Project {self.project_id} not found")

                project_data = project.data[0]
                sandbox_info = project_data.get('sandbox') or {}

                # If there is no sandbox recorded for this project, create one lazily
                if not sandbox_info.get('id'):
                    logger.debug(f"No sandbox recorded for project {self.project_id}; creating lazily")
                    sandbox_pass = str(uuid.uuid4())
                    sandbox_obj = await create_sandbox(sandbox_pass, self.project_id)
                    sandbox_id = sandbox_obj.id

                    logger.info(f"Waiting 2 seconds for sandbox {sandbox_id} services to initialize...")
                    await asyncio.sleep(2)

                    # Gather preview links and token (best-effort parsing)
                    try:
                        vnc_link = await sandbox_obj.get_preview_link(6080)
                        website_link = await sandbox_obj.get_preview_link(8080)
                        vnc_url = vnc_link.url if hasattr(vnc_link, 'url') else str(vnc_link).split("url='")[1].split("'")[0]
                        website_url = website_link.url if hasattr(website_link, 'url') else str(website_link).split("url='")[1].split("'")[0]
                        token = vnc_link.token if hasattr(vnc_link, 'token') else (str(vnc_link).split("token='")[1].split("'")[0] if "token='" in str(vnc_link) else None)
                    except Exception:
                        # If preview link extraction fails, still proceed but leave fields None
                        logger.warning(f"Failed to extract preview links for sandbox {sandbox_id}", exc_info=False)
                        vnc_url = None
                        website_url = None
                        token = None

                    # Persist sandbox metadata to project record
                    update_result = await client.table('projects').update({
                        'sandbox': {
                            'id': sandbox_id,
                            'pass': sandbox_pass,
                            'vnc_preview': vnc_url,
                            'sandbox_url': website_url,
                            'token': token
                        }
                    }).eq('project_id', self.project_id).execute()

                    if not update_result.data:
                        # Cleanup created sandbox if DB update failed
                        try:
                            await delete_sandbox(sandbox_id)
                        except Exception:
                            logger.error(f"Failed to delete sandbox {sandbox_id} after DB update failure", exc_info=False)
                        raise Exception("Database update failed when storing sandbox metadata")

                    # Update project metadata cache with sandbox data (instead of invalidate)
                    try:
                        from core.runtime_cache import set_cached_project_metadata
                        sandbox_cache_data = {
                            'id': sandbox_id,
                            'pass': sandbox_pass,
                            'vnc_preview': vnc_url,
                            'sandbox_url': website_url,
                            'token': token
                        }
                        await set_cached_project_metadata(self.project_id, sandbox_cache_data)
                        logger.debug(f"✅ Updated project cache with sandbox data: {self.project_id}")
                    except Exception as cache_error:
                        logger.warning(f"Failed to update project cache: {cache_error}")

                    # Store local metadata and ensure sandbox is ready
                    self._sandbox_id = sandbox_id
                    self._sandbox_pass = sandbox_pass
                    self._sandbox_url = website_url
                    self._sandbox = await get_or_start_sandbox(self._sandbox_id)
                else:
                    # Use existing sandbox metadata
                    self._sandbox_id = sandbox_info['id']
                    self._sandbox_pass = sandbox_info.get('pass')
                    self._sandbox_url = sandbox_info.get('sandbox_url')
                    self._sandbox = await get_or_start_sandbox(self._sandbox_id)

            except Exception as e:
                logger.error(f"Error retrieving/creating Daytona sandbox for project {self.project_id}: {str(e)}")
                raise e

        return self._sandbox

    @property
    def sandbox(self) -> AsyncSandbox:
        """Get the sandbox instance, ensuring it exists.

        Note: For AgentCore backend, this will raise RuntimeError.
        Use agentcore_session_id instead.
        """
        if self._sandbox is None:
            raise RuntimeError("Sandbox not initialized. Call _ensure_sandbox() first.")
        return self._sandbox

    @property
    def sandbox_id(self) -> str:
        """Get the sandbox ID or AgentCore session ID, ensuring it exists."""
        if self._sandbox_id is None:
            raise RuntimeError("Sandbox ID not initialized. Call _ensure_sandbox() first.")
        return self._sandbox_id

    @property
    def agentcore_session_id(self) -> str:
        """Get the AgentCore session ID.

        Raises RuntimeError if backend is not AgentCore.
        """
        if self._backend_type != 'agentcore':
            raise RuntimeError(f"AgentCore session ID not available. Current backend: {self._backend_type}")
        if self._agentcore_session_id is None:
            raise RuntimeError("AgentCore session ID not initialized. Call _ensure_sandbox() first.")
        return self._agentcore_session_id

    @property
    def backend_type(self) -> str:
        """Get the current backend type ('agentcore' or 'daytona')."""
        if self._backend_type is None:
            raise RuntimeError("Backend type not initialized. Call _ensure_sandbox() first.")
        return self._backend_type

    @property
    def sandbox_url(self) -> str:
        """Get the sandbox URL, ensuring it exists.

        Note: For AgentCore backend, this may not be available.
        """
        if self._sandbox_url is None:
            raise RuntimeError("Sandbox URL not initialized. Call _ensure_sandbox() first.")
        return self._sandbox_url

    def clean_path(self, path: str) -> str:
        """Clean and normalize a path to be relative to /workspace."""
        cleaned_path = clean_path(path, self.workspace_path)
        logger.debug(f"Cleaned path: {path} -> {cleaned_path}")
        return cleaned_path