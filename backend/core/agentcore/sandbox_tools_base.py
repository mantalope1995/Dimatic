"""
AgentCore Sandbox Tools Base

Provides AgentCore-enabled base class for all sandbox tools.
Replaces Daytona.io functionality with AWS AgentCore Code Interpreter and Browser.
"""

from typing import Optional, Dict, Any, List
import uuid
import asyncio
import json

from core.agentpress.thread_manager import ThreadManager
from core.agentpress.tool import Tool
from core.agentcore.code_interpreter_adapter import AgentCoreCodeInterpreterAdapter, SessionConfig
from core.agentcore.browser_adapter import AgentCoreBrowserAdapter
from core.utils.logger import logger
from core.utils.files_utils import clean_path
from core.utils.config import config


class AgentCoreSandboxToolsBase(Tool):
    """
    Base class for all sandbox tools using AWS AgentCore instead of Daytona.io.
    
    Provides secure, serverless code execution and browser automation capabilities
    with automatic session management and resource cleanup.
    """
    
    # Class variable to track if AgentCore sessions have been initialized
    _agentcore_initialized = False
    
    def __init__(self, project_id: str, thread_manager: Optional[ThreadManager] = None):
        super().__init__()
        self.project_id = project_id
        self.thread_manager = thread_manager
        self.workspace_path = "/workspace"
        
        # AgentCore adapters
        self._code_interpreter = None
        self._browser = None
        
        # Session management
        self._code_session_id = None
        self._browser_session_id = None
        
        # Metadata storage
        self._sessions_created = False
        
    async def _ensure_agentcore_initialized(self):
        """Ensure AgentCore adapters are initialized."""
        if not self._agentcore_initialized:
            try:
                self._code_interpreter = AgentCoreCodeInterpreterAdapter()
                self._browser = AgentCoreBrowserAdapter()
                self._agentcore_initialized = True
                logger.info("AgentCore adapters initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize AgentCore adapters: {e}")
                raise RuntimeError(f"AgentCore initialization failed: {e}")
    
    async def _ensure_sessions(self):
        """
        Ensure we have valid AgentCore sessions for the project.
        
        Creates or retrieves Code Interpreter and Browser sessions from project metadata.
        """
        if self._sessions_created:
            return
            
        await self._ensure_agentcore_initialized()
        
        try:
            # Get database client
            client = await self.thread_manager.db.client
            
            # Get project data
            project = await client.table('projects').select('*').eq('project_id', self.project_id).execute()
            if not project.data or len(project.data) == 0:
                raise ValueError(f"Project {self.project_id} not found")
            
            project_data = project.data[0]
            agentcore_sessions = project_data.get('agentcore_sessions') or {}
            
            # Check if we already have sessions
            if not agentcore_sessions.get('code_session_id'):
                logger.debug(f"No AgentCore sessions for project {self.project_id}; creating sessions")
                
                # Create Code Interpreter session
                self._code_session_id = await self._code_interpreter.create_session(
                    project_id=self.project_id,
                    timeout_minutes=15,
                    memory_mb=2048
                )
                
                # Create Browser session  
                self._browser_session_id = await self._browser.create_session(
                    project_id=self.project_id,
                    timeout_minutes=15,
                    headless=True
                )
                
                # Persist session metadata to project record
                session_metadata = {
                    'code_session_id': self._code_session_id,
                    'browser_session_id': self._browser_session_id,
                    'created_at': asyncio.get_event_loop().time(),
                    'expires_at': asyncio.get_event_loop().time() + (15 * 60)  # 15 minutes
                }
                
                update_result = await client.table('projects').update({
                    'agentcore_sessions': session_metadata
                }).eq('project_id', self.project_id).execute()
                
                if not update_result.data:
                    # Cleanup created sessions if DB update failed
                    try:
                        if self._code_session_id:
                            await self._code_interpreter.terminate_session(self._code_session_id)
                        if self._browser_session_id:
                            await self._browser.terminate_session(self._browser_session_id)
                    except Exception:
                        logger.error("Failed to cleanup AgentCore sessions after DB update failure")
                    raise Exception("Database update failed when storing AgentCore session metadata")
                
                logger.info(f"Created AgentCore sessions for project {self.project_id}")
                
            else:
                # Use existing sessions
                self._code_session_id = agentcore_sessions['code_session_id']
                self._browser_session_id = agentcore_sessions.get('browser_session_id')
                
                # Verify sessions are still valid
                if self._code_session_id:
                    code_status = await self._code_interpreter.get_session_status(self._code_session_id)
                    if code_status.get('status') == 'error':
                        logger.warning(f"Code session {self._code_session_id} invalid, creating new one")
                        self._code_session_id = await self._code_interpreter.create_session(
                            project_id=self.project_id,
                            timeout_minutes=15
                        )
                
                if self._browser_session_id:
                    browser_status = await self._browser.get_session_status(self._browser_session_id)
                    if browser_status.get('status') == 'error':
                        logger.warning(f"Browser session {self._browser_session_id} invalid, creating new one")
                        self._browser_session_id = await self._browser.create_session(
                            project_id=self.project_id,
                            timeout_minutes=15
                        )
            
            self._sessions_created = True
            logger.info(f"AgentCore sessions ready for project {self.project_id}")
            
        except Exception as e:
            logger.error(f"Error setting up AgentCore sessions for project {self.project_id}: {str(e)}")
            raise e
    
    @property
    async def code_interpreter(self):
        """Get the Code Interpreter adapter, ensuring sessions exist."""
        await self._ensure_sessions()
        return self._code_interpreter
    
    @property
    async def browser(self):
        """Get the Browser adapter, ensuring sessions exist.""" 
        await self._ensure_sessions()
        return self._browser
    
    @property
    def code_session_id(self) -> str:
        """Get the Code Interpreter session ID."""
        if not self._code_session_id:
            raise RuntimeError("Code session not initialized. Call _ensure_sessions() first.")
        return self._code_session_id
    
    @property
    def browser_session_id(self) -> str:
        """Get the Browser session ID."""
        if not self._browser_session_id:
            raise RuntimeError("Browser session not initialized. Call _ensure_sessions() first.") 
        return self._browser_session_id
    
    def clean_path(self, path: str) -> str:
        """Clean and normalize a path to be relative to /workspace."""
        cleaned_path = clean_path(path, self.workspace_path)
        logger.debug(f"Cleaned path: {path} -> {cleaned_path}")
        return cleaned_path
    
    async def execute_code(
        self, 
        code: str, 
        language: str = "python", 
        timeout: int = 30
    ) -> Dict[str, Any]:
        """
        Execute code in the AgentCore Code Interpreter session.
        
        Args:
            code: Code to execute
            language: Programming language (python, bash, etc.)
            timeout: Execution timeout in seconds
            
        Returns:
            Execution result with output, error, and metadata
        """
        await self._ensure_sessions()
        result = await self._code_interpreter.execute_code(
            session_id=self._code_session_id,
            code=code,
            language=language,
            timeout=timeout
        )
        
        return {
            'output': result.output,
            'error': result.error,
            'exit_code': result.exit_code,
            'execution_time': result.execution_time,
            'files_created': result.files_created
        }
    
    async def execute_shell_command(
        self, 
        command: str, 
        working_dir: str = "/workspace",
        timeout: int = 30
    ) -> Dict[str, Any]:
        """
        Execute a shell command in the Code Interpreter session.
        
        Args:
            command: Shell command to execute
            working_dir: Working directory for command execution
            timeout: Execution timeout in seconds
            
        Returns:
            Command execution result
        """
        await self._ensure_sessions()
        result = await self._code_interpreter.execute_shell_command(
            session_id=self._code_session_id,
            command=command,
            working_dir=working_dir,
            timeout=timeout
        )
        
        return {
            'output': result.output,
            'error': result.error,
            'exit_code': result.exit_code,
            'execution_time': result.execution_time
        }
    
    async def upload_file(self, file_path: str, content: bytes) -> str:
        """
        Upload a file to the Code Interpreter session workspace.
        
        Args:
            file_path: Path where file should be stored
            content: File content as bytes
            
        Returns:
            Path where file was uploaded
        """
        await self._ensure_sessions()
        return await self._code_interpreter.upload_file(
            session_id=self._code_session_id,
            file_path=file_path,
            content=content
        )
    
    async def download_file(self, file_path: str) -> bytes:
        """
        Download a file from the Code Interpreter session workspace.
        
        Args:
            file_path: Path of file to download
            
        Returns:
            File content as bytes
        """
        await self._ensure_sessions()
        return await self._code_interpreter.download_file(
            session_id=self._code_session_id,
            file_path=file_path
        )
    
    async def list_files(self, directory: str = "/workspace") -> List[str]:
        """
        List files in a directory of the workspace.
        
        Args:
            directory: Directory path to list
            
        Returns:
            List of file paths
        """
        await self._ensure_sessions()
        return await self._code_interpreter.list_files(
            session_id=self._code_session_id,
            directory=directory
        )
    
    async def navigate_browser(self, url: str, wait_for: Optional[str] = None) -> Dict[str, Any]:
        """
        Navigate to a URL in the Browser session.
        
        Args:
            url: URL to navigate to
            wait_for: CSS selector or condition to wait for
            
        Returns:
            Navigation result with page details
        """
        await self._ensure_sessions()
        result = await self._browser.navigate(
            session_id=self._browser_session_id,
            url=url,
            wait_for=wait_for
        )
        
        return {
            'url': result.url,
            'html': result.html,
            'screenshot': result.screenshot,
            'status_code': result.status_code,
            'title': result.title,
            'navigation_time': result.navigation_time
        }
    
    async def extract_browser_content(self, selectors: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Extract structured content from the current browser page.
        
        Args:
            selectors: CSS selectors to extract content from
            
        Returns:
            Extracted content with text, links, images, forms
        """
        await self._ensure_sessions()
        result = await self._browser.extract_content(
            session_id=self._browser_session_id,
            selectors=selectors
        )
        
        return {
            'text': result.text,
            'links': result.links,
            'images': result.images,
            'forms': result.forms,
            'structured_data': result.structured_data
        }
    
    async def cleanup_sessions(self):
        """Clean up AgentCore sessions."""
        if self._code_session_id and self._code_interpreter:
            try:
                await self._code_interpreter.terminate_session(self._code_session_id)
                logger.info(f"Cleaned up Code Interpreter session {self._code_session_id}")
            except Exception as e:
                logger.warning(f"Failed to cleanup code session: {e}")
        
        if self._browser_session_id and self._browser:
            try:
                await self._browser.terminate_session(self._browser_session_id)
                logger.info(f"Cleaned up Browser session {self._browser_session_id}")
            except Exception as e:
                logger.warning(f"Failed to cleanup browser session: {e}")
