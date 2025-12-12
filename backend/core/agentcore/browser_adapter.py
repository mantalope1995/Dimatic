"""
AgentCore Browser Adapter

Provides an adapter for AWS AgentCore Browser to replace Daytona.io browser functionality.
Supports secure browser automation, web scraping, and form filling in cloud-based browser environments.
"""

import asyncio
import base64
import json
import uuid
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from core.utils.logger import logger
from core.utils.config import config


@dataclass
class BrowserNavigationResult:
    """Result from browser navigation."""
    url: str
    html: Optional[str] = None
    screenshot: Optional[str] = None
    status_code: Optional[int] = None
    title: Optional[str] = None
    navigation_time: Optional[float] = None


@dataclass
class BrowserContentResult:
    """Result from content extraction."""
    text: str
    links: List[str] = None
    images: List[str] = None
    forms: List[Dict[str, Any]] = None
    structured_data: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.links is None:
            self.links = []
        if self.images is None:
            self.images = []
        if self.forms is None:
            self.forms = []


@dataclass
class BrowserSessionInfo:
    """Information about a browser session."""
    session_id: str
    automation_endpoint: str
    live_view_endpoint: str
    status: str = "initializing"
    created_at: Optional[float] = None
    expires_at: Optional[float] = None


class AgentCoreBrowserAdapter:
    """
    Adapter for AWS AgentCore Browser service.
    
    Replaces Daytona.io browser functionality with AWS-native browser automation.
    Provides secure, isolated browser environments for web automation and scraping.
    """
    
    def __init__(self):
        self.region_name = getattr(config, 'AWS_REGION', 'us-east-1')
        self.browser_tool_id = getattr(config, 'AGENTCORE_BROWSER_TOOL_ID', None)
        self.execution_role_arn = getattr(config, 'AGENTCORE_EXECUTION_ROLE_ARN', None)
        
        # Initialize AWS clients
        try:
            self.bedrock_agentcore_client = boto3.client(
                'bedrock-agentcore',
                region_name=self.region_name
            )
            self.s3_client = boto3.client(
                's3',
                region_name=self.region_name
            )
            logger.info("AWS AgentCore Browser clients initialized successfully")
        except NoCredentialsError:
            logger.error("AWS credentials not found. Please configure AWS credentials.")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize AWS clients: {e}")
            raise
        
        # Active browser sessions cache
        self._active_sessions: Dict[str, BrowserSessionInfo] = {}
        
    async def create_session(
        self,
        project_id: str,
        timeout_minutes: int = 15,
        headless: bool = True,
        enable_recording: bool = False
    ) -> str:
        """
        Create a new browser session for a project.
        
        Args:
            project_id: Project identifier for isolation
            timeout_minutes: Session timeout in minutes
            headless: Whether to run browser in headless mode
            enable_recording: Whether to enable session recording
            
        Returns:
            Session ID for the created browser session
        """
        if not self.browser_tool_id:
            raise ValueError("AGENTCORE_BROWSER_TOOL_ID not configured")
            
        try:
            session_id = f"{project_id}-browser-{uuid.uuid4().hex[:8]}"
            
            # Create browser session
            response = self.bedrock_agentcore_client.create_browser_session(
                browserToolId=self.browser_tool_id,
                sessionId=session_id,
                timeoutInMinutes=timeout_minutes,
                enableRecording=enable_recording
            )
            
            # Extract session endpoints
            session_info = BrowserSessionInfo(
                session_id=session_id,
                automation_endpoint=response.get('automationEndpoint', ''),
                live_view_endpoint=response.get('liveViewEndpoint', ''),
                status='initializing',
                created_at=asyncio.get_event_loop().time()
            )
            
            # Cache session info
            self._active_sessions[session_id] = session_info
            
            logger.info(f"Created browser session {session_id} for project {project_id}")
            return session_id
            
        except ClientError as e:
            logger.error(f"Failed to create browser session: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating browser session: {e}")
            raise
    
    async def navigate(
        self,
        session_id: str,
        url: str,
        wait_for: Optional[str] = None,
        timeout: int = 30
    ) -> BrowserNavigationResult:
        """
        Navigate to a URL in the browser session.
        
        Args:
            session_id: ID of the active browser session
            url: URL to navigate to
            wait_for: CSS selector or condition to wait for
            timeout: Navigation timeout in seconds
            
        Returns:
            BrowserNavigationResult with navigation details
        """
        if session_id not in self._active_sessions:
            raise ValueError(f"Browser session {session_id} not found")
            
        try:
            start_time = asyncio.get_event_loop().time()
            
            # Prepare navigation request
            navigation_request = {
                'sessionId': session_id,
                'url': url,
                'timeoutInSeconds': timeout
            }
            
            # Add wait condition if specified
            if wait_for:
                navigation_request['waitFor'] = wait_for
            
            # Execute navigation
            response = self.bedrock_agentcore_client.navigate_browser(
                **navigation_request
            )
            
            navigation_time = asyncio.get_event_loop().time() - start_time
            
            # Parse response
            result = BrowserNavigationResult(
                url=url,
                html=response.get('html'),
                screenshot=response.get('screenshot'),
                status_code=response.get('statusCode'),
                title=response.get('title'),
                navigation_time=navigation_time
            )
            
            logger.debug(f"Browser navigation completed in {navigation_time:.2f}s for session {session_id}")
            return result
            
        except self.bedrock_agentcore_client.exceptions.TimeoutException:
            logger.warning(f"Browser navigation timed out for session {session_id}")
            return BrowserNavigationResult(
                url=url,
                status_code=408,
                navigation_time=timeout
            )
        except ClientError as e:
            logger.error(f"Failed to navigate browser in session {session_id}: {e}")
            return BrowserNavigationResult(
                url=url,
                status_code=500
            )
        except Exception as e:
            logger.error(f"Unexpected error during browser navigation: {e}")
            return BrowserNavigationResult(
                url=url,
                status_code=500
            )
    
    async def extract_content(
        self,
        session_id: str,
        selectors: Optional[List[str]] = None,
        include_text: bool = True,
        include_links: bool = True,
        include_images: bool = True,
        include_forms: bool = True
    ) -> BrowserContentResult:
        """
        Extract structured content from the current page.
        
        Args:
            session_id: ID of the active browser session
            selectors: CSS selectors to extract content from
            include_text: Whether to include text content
            include_links: Whether to include links
            include_images: Whether to include images
            include_forms: Whether to include forms
            
        Returns:
            BrowserContentResult with extracted content
        """
        if session_id not in self._active_sessions:
            raise ValueError(f"Browser session {session_id} not found")
            
        try:
            # Prepare content extraction request
            extraction_request = {
                'sessionId': session_id,
                'includeText': include_text,
                'includeLinks': include_links,
                'includeImages': include_images,
                'includeForms': include_forms
            }
            
            if selectors:
                extraction_request['selectors'] = selectors
            
            # Execute content extraction
            response = self.bedrock_agentcore_client.extract_browser_content(
                **extraction_request
            )
            
            # Parse response
            result = BrowserContentResult(
                text=response.get('text', ''),
                links=response.get('links', []),
                images=response.get('images', []),
                forms=response.get('forms', []),
                structured_data=response.get('structuredData')
            )
            
            logger.debug(f"Content extraction completed for session {session_id}")
            return result
            
        except ClientError as e:
            logger.error(f"Failed to extract content in session {session_id}: {e}")
            return BrowserContentResult(text="")
        except Exception as e:
            logger.error(f"Unexpected error during content extraction: {e}")
            return BrowserContentResult(text="")
    
    async def fill_form(
        self,
        session_id: str,
        form_data: Dict[str, Any],
        submit: bool = True,
        form_selector: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Fill and optionally submit a form on the current page.
        
        Args:
            session_id: ID of the active browser session
            form_data: Dictionary of field names/ selectors to values
            submit: Whether to submit the form after filling
            form_selector: CSS selector for the form (optional)
            
        Returns:
            Dictionary with form filling results
        """
        if session_id not in self._active_sessions:
            raise ValueError(f"Browser session {session_id} not found")
            
        try:
            # Prepare form filling request
            form_request = {
                'sessionId': session_id,
                'formData': form_data,
                'submit': submit
            }
            
            if form_selector:
                form_request['formSelector'] = form_selector
            
            # Execute form filling
            response = self.bedrock_agentcore_client.fill_browser_form(
                **form_request
            )
            
            result = {
                'success': response.get('success', False),
                'response_url': response.get('responseUrl'),
                'screenshot': response.get('screenshot'),
                'errors': response.get('errors', [])
            }
            
            logger.debug(f"Form filling completed for session {session_id}")
            return result
            
        except ClientError as e:
            logger.error(f"Failed to fill form in session {session_id}: {e}")
            return {
                'success': False,
                'errors': [f"AWS AgentCore error: {str(e)}"]
            }
        except Exception as e:
            logger.error(f"Unexpected error during form filling: {e}")
            return {
                'success': False,
                'errors': [f"Unexpected error: {str(e)}"]
            }
    
    async def click_element(
        self,
        session_id: str,
        selector: str,
        wait_before_click: float = 0.0
    ) -> Dict[str, Any]:
        """
        Click an element on the current page.
        
        Args:
            session_id: ID of the active browser session
            selector: CSS selector for the element to click
            wait_before_click: Time to wait before clicking (seconds)
            
        Returns:
            Dictionary with click results
        """
        if session_id not in self._active_sessions:
            raise ValueError(f"Browser session {session_id} not found")
            
        try:
            # Prepare click request
            click_request = {
                'sessionId': session_id,
                'selector': selector,
                'waitBeforeClickSeconds': wait_before_click
            }
            
            # Execute click
            response = self.bedrock_agentcore_client.click_browser_element(
                **click_request
            )
            
            result = {
                'success': response.get('success', False),
                'screenshot': response.get('screenshot'),
                'navigation_url': response.get('navigationUrl'),
                'errors': response.get('errors', [])
            }
            
            logger.debug(f"Element click completed for session {session_id}")
            return result
            
        except ClientError as e:
            logger.error(f"Failed to click element in session {session_id}: {e}")
            return {
                'success': False,
                'errors': [f"AWS AgentCore error: {str(e)}"]
            }
        except Exception as e:
            logger.error(f"Unexpected error during element click: {e}")
            return {
                'success': False,
                'errors': [f"Unexpected error: {str(e)}"]
            }
    
    async def take_screenshot(
        self,
        session_id: str,
        full_page: bool = False,
        format: str = "png"
    ) -> str:
        """
        Take a screenshot of the current page.
        
        Args:
            session_id: ID of the active browser session
            full_page: Whether to capture the full page
            format: Image format (png, jpeg)
            
        Returns:
            Base64 encoded screenshot
        """
        if session_id not in self._active_sessions:
            raise ValueError(f"Browser session {session_id} not found")
            
        try:
            # Prepare screenshot request
            screenshot_request = {
                'sessionId': session_id,
                'fullPage': full_page,
                'format': format
            }
            
            # Execute screenshot
            response = self.bedrock_agentcore_client.take_browser_screenshot(
                **screenshot_request
            )
            
            screenshot = response.get('screenshot', '')
            
            logger.debug(f"Screenshot taken for session {session_id}")
            return screenshot
            
        except ClientError as e:
            logger.error(f"Failed to take screenshot in session {session_id}: {e}")
            return ""
        except Exception as e:
            logger.error(f"Unexpected error during screenshot: {e}")
            return ""
    
    async def execute_script(
        self,
        session_id: str,
        javascript: str
    ) -> Any:
        """
        Execute JavaScript in the browser session.
        
        Args:
            session_id: ID of the active browser session
            javascript: JavaScript code to execute
            
        Returns:
            Script execution result
        """
        if session_id not in self._active_sessions:
            raise ValueError(f"Browser session {session_id} not found")
            
        try:
            # Prepare script execution request
            script_request = {
                'sessionId': session_id,
                'javascript': javascript
            }
            
            # Execute script
            response = self.bedrock_agentcore_client.execute_browser_script(
                **script_request
            )
            
            result = response.get('result')
            
            logger.debug(f"Script execution completed for session {session_id}")
            return result
            
        except ClientError as e:
            logger.error(f"Failed to execute script in session {session_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during script execution: {e}")
            return None
    
    async def get_page_info(
        self,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Get information about the current page.
        
        Args:
            session_id: ID of the active browser session
            
        Returns:
            Dictionary with page information
        """
        if session_id not in self._active_sessions:
            raise ValueError(f"Browser session {session_id} not found")
            
        try:
            # Get page information
            response = self.bedrock_agentcore_client.get_browser_page_info(
                sessionId=session_id
            )
            
            page_info = {
                'url': response.get('url', ''),
                'title': response.get('title', ''),
                'viewport': response.get('viewport', {}),
                'cookies': response.get('cookies', []),
                'local_storage': response.get('localStorage', {}),
                'session_storage': response.get('sessionStorage', {})
            }
            
            logger.debug(f"Page info retrieved for session {session_id}")
            return page_info
            
        except ClientError as e:
            logger.error(f"Failed to get page info in session {session_id}: {e}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error getting page info: {e}")
            return {}
    
    async def terminate_session(self, session_id: str) -> bool:
        """
        Terminate a browser session.
        
        Args:
            session_id: ID of the session to terminate
            
        Returns:
            True if session was terminated successfully
        """
        if session_id not in self._active_sessions:
            logger.warning(f"Browser session {session_id} not found in active sessions")
            return False
            
        try:
            # Terminate the session
            self.bedrock_agentcore_client.terminate_browser_session(
                browserToolId=self.browser_tool_id,
                sessionId=session_id
            )
            
            # Remove from active sessions
            del self._active_sessions[session_id]
            
            logger.info(f"Terminated browser session {session_id}")
            return True
            
        except ClientError as e:
            logger.error(f"Failed to terminate browser session {session_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error terminating browser session {session_id}: {e}")
            return False
    
    async def get_session_status(self, session_id: str) -> Dict[str, Any]:
        """
        Get status of a browser session.
        
        Args:
            session_id: ID of the session
            
        Returns:
            Session status information
        """
        try:
            response = self.bedrock_agentcore_client.get_browser_session(
                browserToolId=self.browser_tool_id,
                sessionId=session_id
            )
            
            status = {
                'session_id': session_id,
                'status': response.get('status', 'unknown'),
                'created_at': response.get('createdAt'),
                'expires_at': response.get('expiresAt'),
                'last_activity_at': response.get('lastActivityAt'),
                'automation_endpoint': response.get('automationEndpoint'),
                'live_view_endpoint': response.get('liveViewEndpoint')
            }
            
            return status
            
        except ClientError as e:
            logger.error(f"Failed to get browser session status for {session_id}: {e}")
            return {'session_id': session_id, 'status': 'error', 'error': str(e)}
        except Exception as e:
            logger.error(f"Unexpected error getting browser session status: {e}")
            return {'session_id': session_id, 'status': 'error', 'error': str(e)}
    
    async def get_live_view_url(self, session_id: str) -> Optional[str]:
        """
        Get the live view URL for a browser session.
        
        Args:
            session_id: ID of the session
            
        Returns:
            Live view URL if available
        """
        if session_id not in self._active_sessions:
            return None
            
        session_info = self._active_sessions[session_id]
        return session_info.live_view_endpoint
    
    async def cleanup_expired_sessions(self):
        """Clean up expired browser sessions."""
        current_time = asyncio.get_event_loop().time()
        expired_sessions = []
        
        for session_id, session_info in self._active_sessions.items():
            # Assume 15 minute default timeout if not specified
            timeout_seconds = 15 * 60
            if session_info.created_at:
                age_seconds = current_time - session_info.created_at
                
                if age_seconds > timeout_seconds:
                    expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            logger.info(f"Cleaning up expired browser session {session_id}")
            await self.terminate_session(session_id)
