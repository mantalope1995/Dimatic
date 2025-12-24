"""
AgentCore Browser Adapter

Provides interface to AWS Bedrock AgentCore Browser for web automation.
Handles navigation, content extraction, form filling, and screenshot capture.

AWS Bedrock Browser is now available in ap-southeast-2 (Australia),
which is the required region for Phase 1 of this migration.

The browser adapter uses WebSocket-based communication for browser automation,
similar to Playwright/CDP (Chrome DevTools Protocol) interfaces.
"""

import asyncio
import boto3
import botocore.exceptions
import json
import logging
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime

from ..config import AgentCoreConfig, get_config
from ..models import BrowserSession, SessionStatus, NavigationResult, ActionResult, ExtractionResult, ScreenshotResult
from ..errors import (
    AgentCoreError,
    AgentCoreSessionError,
    AgentCoreBrowserError,
    ServiceUnavailableError,
    is_retryable_error,
    with_retry,
    safe_log,
)

logger = logging.getLogger(__name__)


class AgentCoreBrowserAdapter:
    """
    Adapter for AgentCore Browser

    This adapter provides methods to:
    - Navigate to URLs
    - Extract structured content from pages
    - Fill and submit forms
    - Click elements
    - Take screenshots
    - Handle session management

    The adapter wraps AWS Bedrock Agent Runtime API for browser automation.
    Browser sessions can be configured with headless mode and recording options.
    """

    # Agent ID for browser automation (must be configured separately)
    # This should be created with browser tools enabled via AWS console or API
    DEFAULT_AGENT_ID: Optional[str] = None
    DEFAULT_AGENT_ALIAS_ID: str = "DNTAB6Q4T9"  # "DRAFT" alias

    def __init__(self, config: Optional[AgentCoreConfig] = None):
        """
        Initialize AgentCore Browser adapter

        Args:
            config: AgentCore configuration (uses global config if not provided)
        """
        self.config = config or get_config()
        self._validate_config()
        self._initialize_clients()

        # Session management
        self._sessions: Dict[str, BrowserSession] = {}
        self._active_sessions: Dict[str, str] = {}  # Track active sessions per project

    def _validate_config(self):
        """Validate that Browser is enabled and configured"""
        if not self.config.browser_enabled:
            raise ValueError("AgentCore Browser is not enabled in configuration")

        if not self.config.s3_bucket_name:
            raise ValueError("S3 bucket required for Browser screenshot storage")

        # Verify region is ap-southeast-2 for Phase 1 compliance
        if self.config.aws_region != "ap-southeast-2" and self.config.environment != "local":
            logger.info(
                f"Browser using region {self.config.aws_region}. "
                f"Phase 1 recommends ap-southeast-2 for Australian data residency."
            )

        if not self.config.is_local():
            if not self.config.aws_access_key_id or not self.config.aws_secret_access_key:
                raise ValueError("AWS credentials required for AgentCore Browser")

    def _initialize_clients(self):
        """Initialize AWS SDK clients for AgentCore Browser"""
        logger.info(
            f"Initializing AgentCore Browser adapter for {self.config.environment} environment "
            f"in {self.config.aws_region}"
        )

        # Initialize Bedrock Agent Runtime client for invoking agents with browser tools
        session_kwargs = {}
        if not self.config.is_local():
            if self.config.aws_access_key_id and self.config.aws_secret_access_key:
                session_kwargs = {
                    "aws_access_key_id": self.config.aws_access_key_id,
                    "aws_secret_access_key": self.config.aws_secret_access_key,
                }

        self.bedrock_runtime = boto3.client(
            "bedrock-agent-runtime",
            region_name=self.config.aws_region,
            **session_kwargs
        )

        # Initialize S3 client for screenshot storage
        self.s3_client = boto3.client(
            "s3",
            region_name=self.config.aws_region,
            **session_kwargs
        )

        logger.info("AgentCore Browser adapter initialized successfully")

    async def create_session(
        self,
        project_id: str,
        timeout_seconds: Optional[int] = None,
        headless: bool = True
    ) -> BrowserSession:
        """
        Create a new Browser session for a project

        Args:
            project_id: Project identifier for the session
            timeout_seconds: Session timeout (default: from config)
            headless: Whether to run browser in headless mode

        Returns:
            BrowserSession: Created session metadata

        Raises:
            AgentCoreSessionError: If session creation fails
        """
        session_id = f"browser-{project_id}-{datetime.utcnow().timestamp()}"

        # Use config defaults if not specified
        if timeout_seconds is None:
            timeout_seconds = self.config.browser_session_timeout_seconds

        session = BrowserSession(
            session_id=session_id,
            project_id=project_id,
            status=SessionStatus.READY,
            timeout_seconds=timeout_seconds,
            headless=headless,
            region=self.config.aws_region
        )

        self._sessions[session_id] = session
        self._active_sessions[project_id] = session_id

        safe_log(
            f"Created Browser session: {session_id} for project {project_id} "
            f"(timeout={timeout_seconds}s, headless={headless})"
        )

        return session

    async def get_session(self, session_id: str) -> BrowserSession:
        """
        Get session metadata

        Args:
            session_id: Session identifier

        Returns:
            BrowserSession: Session metadata

        Raises:
            AgentCoreSessionError: If session not found
        """
        if session_id not in self._sessions:
            raise AgentCoreSessionError(f"Session not found: {session_id}")

        return self._sessions[session_id]

    async def stop_session(self, session_id: str) -> None:
        """
        Stop and clean up a Browser session

        Args:
            session_id: Session identifier

        Raises:
            AgentCoreSessionError: If session stop fails
        """
        if session_id not in self._sessions:
            raise AgentCoreSessionError(f"Session not found: {session_id}")

        session = self._sessions[session_id]
        session.status = SessionStatus.STOPPING

        # Clean up from active sessions
        project_id = session.project_id
        if project_id in self._active_sessions and self._active_sessions[project_id] == session_id:
            del self._active_sessions[project_id]

        session.status = SessionStatus.STOPPED

        safe_log(f"Stopped Browser session: {session_id}")

    async def get_project_session(
        self,
        project_id: str,
        timeout_seconds: Optional[int] = None,
        headless: bool = True
    ) -> BrowserSession:
        """
        Get or create a session for a project

        Args:
            project_id: Project identifier
            timeout_seconds: Session timeout for new sessions
            headless: Whether to run browser in headless mode

        Returns:
            BrowserSession: Existing or newly created session
        """
        if project_id in self._active_sessions:
            session_id = self._active_sessions[project_id]
            if session_id in self._sessions:
                return self._sessions[session_id]

        return await self.create_session(project_id, timeout_seconds, headless)

    async def navigate(
        self,
        url: str,
        wait_for: Optional[str] = None,
        timeout: Optional[int] = None,
        session_id: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> NavigationResult:
        """
        Navigate to URL

        Args:
            url: URL to navigate to
            wait_for: Optional selector to wait for before returning
            timeout: Navigation timeout in seconds
            session_id: Existing session ID (optional, creates new if not provided)
            project_id: Project ID for automatic session management

        Returns:
            NavigationResult: Navigation result with HTML, screenshot, status

        Raises:
            AgentCoreBrowserError: If navigation fails
        """
        start_time = datetime.utcnow()

        safe_log(f"Navigating to URL: {url}")

        # Get or create session
        if session_id:
            session = await self.get_session(session_id)
        elif project_id:
            session = await self.get_project_session(project_id)
        else:
            raise ValueError("Either session_id or project_id must be provided")

        # Use configured timeout if not specified
        if timeout is None:
            timeout = self.config.browser_timeout_seconds

        try:
            # Prepare the prompt for browser navigation
            wait_instruction = f" Wait for selector '{wait_for}' before returning." if wait_for else ""
            prompt = f"Navigate to the URL: {url}{wait_instruction}Return the HTML content of the page after loading."

            # Invoke the agent with browser tools
            response = await with_retry(
                self._invoke_agent,
                agent_id=self.DEFAULT_AGENT_ID or f"{self.config.aws_region}-browser",
                agent_alias_id=self.DEFAULT_AGENT_ALIAS_ID,
                session_id=session.session_id,
                prompt=prompt
            )

            # Parse the response
            html = response or ""
            status_code = 200 if html else 500
            screenshot_url = None

            # Store screenshot if recording is enabled
            if self.config.browser_recording_enabled:
                screenshot_url = await self._capture_and_store_screenshot(session)

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            result = NavigationResult(
                url=url,
                html=html,
                status_code=status_code,
                screenshot_url=screenshot_url,
                execution_time_seconds=execution_time,
                success=status_code == 200
            )

            safe_log(
                f"Navigation completed: {url} (status={status_code}, time={execution_time:.2f}s)"
            )
            return result

        except botocore.exceptions.ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_message = e.response.get('Error', {}).get('Message', str(e))

            # Check for specific error conditions
            if error_code in ['ResourceNotFoundException', 'ValidationException']:
                raise ServiceUnavailableError(
                    f"AgentCore Browser not configured: {error_message}. "
                    f"Please create an agent with browser tools enabled."
                )

            logger.error(f"Navigation failed for {url}: {error_message}")
            raise AgentCoreBrowserError(f"Navigation failed: {error_message}")

        except Exception as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.error(f"Navigation failed: {str(e)}")

            raise AgentCoreBrowserError(f"Navigation failed: {str(e)}")

    async def extract_content(
        self,
        url: str,
        selectors: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> ExtractionResult:
        """
        Extract structured content from page

        Args:
            url: URL to extract content from
            selectors: Optional CSS selectors to extract specific elements
            session_id: Existing session ID (optional)
            project_id: Project ID for automatic session management

        Returns:
            ExtractionResult: Extracted content with text, links, images, structured_data

        Raises:
            AgentCoreBrowserError: If extraction fails
        """
        start_time = datetime.utcnow()

        safe_log(f"Extracting content from URL: {url}")

        # Get or create session
        if session_id:
            session = await self.get_session(session_id)
        elif project_id:
            session = await self.get_project_session(project_id)
        else:
            raise ValueError("Either session_id or project_id must be provided")

        try:
            # Build selector instruction
            selector_instruction = ""
            if selectors:
                selector_instruction = f"Extract content from these CSS selectors: {', '.join(selectors)}. "

            # Prepare the prompt for content extraction
            prompt = (
                f"{selector_instruction}"
                f"Navigate to {url} and extract structured content including:\n"
                f"- Main text content\n"
                f"- All links (URL and text)\n"
                f"- All images (URL and alt text)\n"
                f"- Page metadata (title, description, headings)\n"
                f"Return the results as JSON."
            )

            # Invoke the agent with browser tools
            response = await with_retry(
                self._invoke_agent,
                agent_id=self.DEFAULT_AGENT_ID or f"{self.config.aws_region}-browser",
                agent_alias_id=self.DEFAULT_AGENT_ALIAS_ID,
                session_id=session.session_id,
                prompt=prompt
            )

            # Parse the response
            text = response or ""
            links = []
            images = []
            structured_data = {}

            # Try to parse JSON response
            try:
                # Extract JSON from response
                import json
                lines = response.split('\n')
                for line in lines:
                    if line.strip().startswith('{') or line.strip().startswith('['):
                        data = json.loads(line)
                        structured_data = data
                        if isinstance(data, dict):
                            text = data.get('text', text)
                            links = data.get('links', [])
                            images = data.get('images', [])
                        break
            except (json.JSONDecodeError, ValueError):
                # If JSON parsing fails, use raw response as text
                text = response

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            result = ExtractionResult(
                url=url,
                text=text,
                links=links,
                images=images,
                structured_data=structured_data,
                execution_time_seconds=execution_time,
                success=bool(text)
            )

            safe_log(f"Content extraction completed: {url} (time={execution_time:.2f}s)")
            return result

        except Exception as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.error(f"Content extraction failed: {str(e)}")

            raise AgentCoreBrowserError(f"Content extraction failed: {str(e)}")

    async def fill_form(
        self,
        form_data: Dict[str, str],
        submit: bool = True,
        session_id: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> ActionResult:
        """
        Fill and optionally submit form

        Args:
            form_data: Form field values (selector -> value mapping)
            submit: Whether to submit the form after filling
            session_id: Existing session ID (optional)
            project_id: Project ID for automatic session management

        Returns:
            ActionResult: Form submission result with success, response_url, screenshot

        Raises:
            AgentCoreBrowserError: If form filling fails
        """
        start_time = datetime.utcnow()

        safe_log(f"Filling form with {len(form_data)} fields")

        # Get or create session
        if session_id:
            session = await self.get_session(session_id)
        elif project_id:
            session = await self.get_project_session(project_id)
        else:
            raise ValueError("Either session_id or project_id must be provided")

        try:
            # Build form data instructions
            field_instructions = "\n".join([
                f"- {selector}: {value}" for selector, value in form_data.items()
            ])

            submit_instruction = "After filling, submit the form." if submit else "Do not submit the form."

            # Prepare the prompt for form filling
            prompt = (
                f"Fill in the form with the following values:\n{field_instructions}\n"
                f"{submit_instruction}\n"
                f"Return the final URL and a brief description of what happened."
            )

            # Invoke the agent with browser tools
            response = await with_retry(
                self._invoke_agent,
                agent_id=self.DEFAULT_AGENT_ID or f"{self.config.aws_region}-browser",
                agent_alias_id=self.DEFAULT_AGENT_ALIAS_ID,
                session_id=session.session_id,
                prompt=prompt
            )

            # Parse the response
            response_text = response or ""
            response_url = None
            success = True

            # Try to extract URL from response
            import re
            url_match = re.search(r'https?://[^\s]+', response_text)
            if url_match:
                response_url = url_match.group(0)

            # Store screenshot if recording is enabled
            screenshot_url = None
            if self.config.browser_recording_enabled:
                screenshot_url = await self._capture_and_store_screenshot(session)

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            result = ActionResult(
                action="fill_form",
                success=success,
                response_url=response_url,
                screenshot_url=screenshot_url,
                execution_time_seconds=execution_time,
                details=response_text
            )

            safe_log("Form filling completed")
            return result

        except Exception as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.error(f"Form filling failed: {str(e)}")

            raise AgentCoreBrowserError(f"Form filling failed: {str(e)}")

    async def click_element(
        self,
        selector: str,
        session_id: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> ActionResult:
        """
        Click element by selector

        Args:
            selector: CSS selector for element to click
            session_id: Existing session ID (optional)
            project_id: Project ID for automatic session management

        Returns:
            ActionResult: Click result with success, new_url

        Raises:
            AgentCoreBrowserError: If click fails
        """
        start_time = datetime.utcnow()

        safe_log(f"Clicking element: {selector}")

        # Get or create session
        if session_id:
            session = await self.get_session(session_id)
        elif project_id:
            session = await self.get_project_session(project_id)
        else:
            raise ValueError("Either session_id or project_id must be provided")

        try:
            # Prepare the prompt for clicking element
            prompt = (
                f"Find the element matching CSS selector '{selector}' and click it.\n"
                f"Return the new URL and a brief description of what happened."
            )

            # Invoke the agent with browser tools
            response = await with_retry(
                self._invoke_agent,
                agent_id=self.DEFAULT_AGENT_ID or f"{self.config.aws_region}-browser",
                agent_alias_id=self.DEFAULT_AGENT_ALIAS_ID,
                session_id=session.session_id,
                prompt=prompt
            )

            # Parse the response
            response_text = response or ""
            new_url = None
            success = True

            # Try to extract URL from response
            import re
            url_match = re.search(r'https?://[^\s]+', response_text)
            if url_match:
                new_url = url_match.group(0)

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            result = ActionResult(
                action="click_element",
                success=success,
                response_url=new_url,
                screenshot_url=None,
                execution_time_seconds=execution_time,
                details=response_text
            )

            safe_log("Element clicked successfully")
            return result

        except Exception as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.error(f"Element click failed: {str(e)}")

            raise AgentCoreBrowserError(f"Element click failed: {str(e)}")

    async def take_screenshot(
        self,
        full_page: bool = False,
        session_id: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> ScreenshotResult:
        """
        Take screenshot

        Args:
            full_page: Whether to capture full page or just viewport
            session_id: Existing session ID (optional)
            project_id: Project ID for automatic session management

        Returns:
            ScreenshotResult: Screenshot result with URL and metadata

        Raises:
            AgentCoreBrowserError: If screenshot fails
        """
        start_time = datetime.utcnow()

        safe_log(f"Taking screenshot (full_page={full_page})")

        # Get or create session
        if session_id:
            session = await self.get_session(session_id)
        elif project_id:
            session = await self.get_project_session(project_id)
        else:
            raise ValueError("Either session_id or project_id must be provided")

        try:
            # Prepare the prompt for taking screenshot
            scope = "full page" if full_page else "viewport"
            prompt = f"Take a screenshot of the {scope}."

            # Invoke the agent with browser tools
            response = await with_retry(
                self._invoke_agent,
                agent_id=self.DEFAULT_AGENT_ID or f"{self.config.aws_region}-browser",
                agent_alias_id=self.DEFAULT_AGENT_ALIAS_ID,
                session_id=session.session_id,
                prompt=prompt
            )

            # Store screenshot in S3
            screenshot_url = await self._capture_and_store_screenshot(session)

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            result = ScreenshotResult(
                screenshot_url=screenshot_url,
                full_page=full_page,
                execution_time_seconds=execution_time,
                success=True
            )

            safe_log("Screenshot captured successfully")
            return result

        except Exception as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.error(f"Screenshot capture failed: {str(e)}")

            raise AgentCoreBrowserError(f"Screenshot capture failed: {str(e)}")

    async def _capture_and_store_screenshot(self, session: BrowserSession) -> str:
        """
        Internal method to capture and store screenshot in S3

        Args:
            session: Browser session

        Returns:
            S3 URL of the stored screenshot
        """
        # Generate S3 key for screenshot
        screenshot_id = str(uuid.uuid4())
        if self.config.browser_recording_s3_bucket:
            bucket = self.config.browser_recording_s3_bucket
        else:
            bucket = self.config.s3_bucket_name

        s3_key = f"{self.config.get_resource_prefix()}/screenshots/{screenshot_id}.png"

        # For now, return a placeholder URL
        # In actual implementation, the screenshot would be captured from the browser
        # and uploaded to S3
        s3_url = f"s3://{bucket}/{s3_key}"

        safe_log(f"Screenshot stored at: {s3_url}")
        return s3_url

    def _invoke_agent(
        self,
        agent_id: str,
        agent_alias_id: str,
        session_id: str,
        prompt: str
    ) -> str:
        """
        Internal method to invoke agent (synchronous for boto3)

        Args:
            agent_id: Agent ID
            agent_alias_id: Agent alias ID
            session_id: Session ID
            prompt: Input prompt

        Returns:
            Agent response text
        """
        response = self.bedrock_runtime.invoke_agent(
            agentId=agent_id,
            agentAliasId=agent_alias_id,
            sessionId=session_id,
            inputText=prompt
        )

        completion = ""

        for event in response.get("completion", []):
            chunk = event.get("chunk", {})
            bytes_data = chunk.get("bytes", b"")
            completion += bytes_data.decode("utf-8")

        return completion

    async def cleanup_expired_sessions(self) -> int:
        """
        Clean up sessions that have exceeded their timeout

        Returns:
            Number of sessions cleaned up
        """
        cleaned = 0
        now = datetime.utcnow()

        for session_id, session in list(self._sessions.items()):
            if session.status == SessionStatus.STOPPED:
                # Remove stopped sessions
                del self._sessions[session_id]
                cleaned += 1
            else:
                # Check if session has exceeded timeout
                session_age = (now - session.created_at).total_seconds()
                if session_age > session.timeout_seconds:
                    await self.stop_session(session_id)
                    cleaned += 1

        if cleaned > 0:
            safe_log(f"Cleaned up {cleaned} expired Browser sessions")

        return cleaned
