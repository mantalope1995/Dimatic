"""
AgentCore Browser Tool

Browser automation tool that uses AWS AgentCore Browser instead of Stagehand.
Provides web navigation, content extraction, and interaction capabilities.
"""

import asyncio
import base64
import json
import uuid
from typing import Optional, Dict, Any, List
from PIL import Image
import io
import re

from core.agentpress.tool import ToolResult, openapi_schema, tool_metadata
from core.agentcore.sandbox_tools_base import AgentCoreSandboxToolsBase
from core.agentpress.thread_manager import ThreadManager
from core.utils.logger import logger
from core.utils.s3_upload_utils import upload_base64_image
from core.utils.config import config


@tool_metadata(
    display_name="Web Browser (AgentCore)",
    description="Browse websites, click buttons, fill forms, and extract information from web pages using AWS AgentCore Browser",
    icon="Globe",
    color="bg-blue-100 dark:bg-blue-800/50",
    weight=60,
    visible=True
)
class AgentCoreBrowserTool(AgentCoreSandboxToolsBase):
    """
    Browser Tool using AWS AgentCore Browser service.
    
    Provides secure, cloud-based browser automation capabilities
    without requiring local browser infrastructure.
    """

    def __init__(self, project_id: str, thread_manager: ThreadManager):
        super().__init__(project_id, thread_manager)
        self._browser_session_id = None

    async def _ensure_browser_session(self) -> str:
        """Ensure we have a valid AgentCore Browser session."""
        if self._browser_session_id is None:
            try:
                # Get or create browser session from project metadata
                if 'browser_session_id' in self._agentcore_metadata:
                    self._browser_session_id = self._agentcore_metadata['browser_session_id']
                    # Verify session is still active
                    browser = await self._ensure_browser()
                    status = await browser.get_session_status(self._browser_session_id)
                    
                    if status.get('status') in ['error', 'expired', 'terminated']:
                        logger.info(f"Browser session {self._browser_session_id} expired, creating new session")
                        self._browser_session_id = None
                else:
                    logger.debug(f"No existing browser session for project {self.project_id}")
                
                # Create new session if needed
                if self._browser_session_id is None:
                    browser = await self._ensure_browser()
                    self._browser_session_id = await browser.create_session(
                        project_id=self.project_id,
                        timeout_minutes=30,
                        headless=True,
                        enable_recording=True
                    )
                    
                    # Save session ID to project metadata
                    await self._save_agentcore_metadata({
                        'browser_session_id': self._browser_session_id,
                        'browser_created_at': asyncio.get_event_loop().time()
                    })
                    
                logger.info(f"Browser session ready: {self._browser_session_id}")
                    
            except Exception as e:
                logger.error(f"Failed to get/create browser session: {e}")
                raise RuntimeError(f"Browser session unavailable: {e}")
                
        return self._browser_session_id

    @openapi_schema({
        "type": "function",
        "function": {
            "name": "navigate_to",
            "description": "Navigate to a specified URL in the browser and wait for page to load",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to navigate to. Must be a valid HTTP/HTTPS URL."
                    },
                    "wait_for": {
                        "type": "string",
                        "description": "CSS selector or condition to wait for before returning. Examples: 'body', '#content', 'div.main'"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Maximum time to wait for the page to load in seconds. Default: 30",
                        "default": 30
                    }
                },
                "required": ["url"]
            }
        }
    })
    async def navigate_to(
        self,
        url: str,
        wait_for: Optional[str] = None,
        timeout: int = 30
    ) -> ToolResult:
        """Navigate to a URL and wait for page to load."""
        try:
            if not self.is_browser_available:
                return self.fail_response(
                    "Browser not available. Please configure AWS AgentCore Browser."
                )
            
            # Validate URL
            if not url.startswith(('http://', 'https://')):
                return self.fail_response("URL must start with http:// or https://")
            
            session_id = await self._ensure_browser_session()
            browser = await self._ensure_browser()
            
            # Navigate to URL
            result = await browser.navigate(
                session_id=session_id,
                url=url,
                wait_for=wait_for,
                timeout=timeout
            )
            
            if result.error:
                return self.fail_response(f"Navigation failed: {result.error}")
            
            return self.success_response({
                "url": result.url,
                "title": result.title,
                "status_code": result.status_code,
                "navigation_time": result.navigation_time,
                "screenshot": result.screenshot,
                "message": f"Successfully navigated to {url}"
            })
            
        except Exception as e:
            logger.error(f"Error navigating to {url}: {str(e)}")
            return self.fail_response(f"Error navigating to URL: {str(e)}")

    @openapi_schema({
        "type": "function",
        "function": {
            "name": "extract_content",
            "description": "Extract structured content from the current page including text, links, images, and form information",
            "parameters": {
                "type": "object",
                "properties": {
                    "selectors": {
                        "type": "array",
                        "description": "List of CSS selectors to extract specific elements. If empty, extracts all text content.",
                        "items": {
                            "type": "string"
                        }
                    },
                    "include_text": {
                        "type": "boolean",
                        "description": "Whether to extract text content (default: true)",
                        "default": True
                    },
                    "include_links": {
                        "type": "boolean", 
                        "description": "Whether to extract link URLs (default: true)",
                        "default": True
                    },
                    "include_images": {
                        "type": "boolean",
                        "description": "Whether to extract image URLs (default: true)",
                        "default": True
                    },
                    "include_forms": {
                        "type": "boolean",
                        "description": "Whether to extract form information (default: true)",
                        "default": True
                    }
                },
                "required": []
            }
        }
    })
    async def extract_content(
        self,
        selectors: Optional[List[str]] = None,
        include_text: bool = True,
        include_links: bool = True,
        include_images: bool = True,
        include_forms: bool = True
    ) -> ToolResult:
        """Extract structured content from the current browser page."""
        try:
            if not self.is_browser_available:
                return self.fail_response(
                    "Browser not available. Please configure AWS AgentCore Browser."
                )
            
            session_id = await self._ensure_browser_session()
            browser = await self._ensure_browser()
            
            result = await browser.extract_content(
                session_id=session_id,
                selectors=selectors,
                include_text=include_text,
                include_links=include_links,
                include_images=include_images,
                include_forms=include_forms
            )
            
            if result.error:
                return self.fail_response(f"Content extraction failed: {result.error}")
            
            return self.success_response({
                "text": result.text,
                "links": result.links,
                "images": result.images,
                "forms": result.forms,
                "structured_data": result.structured_data
            })
            
        except Exception as e:
            logger.error(f"Error extracting content: {str(e)}")
            return self.fail_response(f"Error extracting content: {str(e)}")

    @openapi_schema({
        "type": "function",
        "function": {
            "name": "fill_form",
            "description": "Fill and optionally submit form fields on the current page",
            "parameters": {
                "type": "object",
                "properties": {
                    "form_data": {
                        "type": "object",
                        "description": "Dictionary mapping form field names/locators to their values. Can use CSS selectors or name attributes.",
                        "example": {
                            "name": "John Doe",
                            "email": "john@example.com",
                            "submit": True
                        }
                    },
                    "form_selector": {
                        "type": "string", 
                        "description": "CSS selector for the form to target (optional)"
                    },
                    "submit": {
                        "type": "boolean",
                        "description": "Whether to submit the form after filling (default: true)",
                        "default": True
                    }
                },
                "required": ["form_data"]
            }
        }
    })
    async def fill_form(
        self,
        form_data: Dict[str, Any],
        form_selector: Optional[str] = None,
        submit: bool = True
    ) -> ToolResult:
        """Fill form fields and optionally submit."""
        try:
            if not self.is_browser_available:
                return self.fail_response(
                    "Browser not available. Please configure AWS AgentCore Browser."
                )
            
            session_id = await self._ensure_browser_session()
            browser = await self._ensure_browser()
            
            result = await browser.fill_form(
                session_id=session_id,
                form_data=form_data,
                form_selector=form_selector,
                submit=submit
            )
            
            if result.error:
                return self.fail_response(f"Form filling failed: {result.error}")
            
            return self.success_response({
                "success": result['success'],
                "response_url": result.get('response_url'),
                "screenshot": result.get('screenshot'),
                "errors": result.get('errors', [])
            })
            
        except Exception as e:
            logger.error(f"Error filling form: {str(e)}")
            return self.fail_response(f"Error filling form: {str(e)}")

    @openapi_schema({
        "type": "function",
        "function": {
            "name": "click_element",
            "description": "Click on an element on the current page using CSS selector",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS selector for the element to click"
                    },
                    "wait_before_click": {
                        "type": "number",
                        "description": "Time to wait before clicking in seconds (default: 1.0)",
                        "default": 1.0
                    }
                },
                "required": ["selector"]
            }
        }
    })
    async def click_element(
        self,
        selector: str,
        wait_before_click: float = 1.0
    ) -> ToolResult:
        """Click on an element using CSS selector."""
        try:
            if not self.is_browser_available:
                return self.fail_response(
                    "Browser not available. Please configure AWS AgentCore Browser."
                )
            
            session_id = await self._ensure_browser_session()
            browser = await self._ensure_browser()
            
            result = await browser.click_element(
                session_id=session_id,
                selector=selector,
                wait_before_click=wait_before_click
            )
            
            if result.error:
                return self.fail_response(f"Element click failed: {result.error}")
            
            return self.success_response({
                "success": result['success'],
                "screenshot": result.get('screenshot'),
                "navigation_url": result.get('navigation_url'),
                "errors": result.get('errors', [])
            })
            
        except Exception as e:
            logger.error(f"Error clicking element: {str(e)}")
            return self.fail_response(f"Error clicking element: {str(e)}")

    @openapi_schema({
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Take a screenshot of the current page. Returns base64 encoded image.",
            "parameters": {
                "type": "object",
                "properties": {
                    "full_page": {
                        "type": "boolean",
                        "description": "Whether to capture the entire page (true) or just the viewport (false).",
                        "default": False
                    },
                    "format": {
                        "type": "string",
                        "description": "Image format to use: 'png', 'jpeg', 'webp'",
                        "default": "png"
                    },
                    "quality": {
                        "type": "integer",
                        "description": "Image quality for JPEG format (1-100).",
                        "default": 90
                    }
                },
                "required": []
            }
        }
    })
    async def take_screenshot(
        self,
        full_page: bool = False,
        format: str = "png",
        quality: int = 90
    ) -> ToolResult:
        """Take a screenshot of the current page."""
        try:
            if not self.is_browser_available:
                return self.fail_response(
                    "Browser not available. Please configure AWS AgentCore Browser."
                )
            
            session_id = await self._ensure_browser_session()
            browser = await self._ensure_browser()
            
            screenshot = await browser.take_screenshot(
                session_id=session_id,
                full_page=full_page,
                format=format
            )
            
            if not screenshot:
                return self.fail_response("Failed to capture screenshot")
            
            return self.success_response({
                "screenshot": screenshot,
                "full_page": full_page,
                "format": format,
                "message": f"Screenshot captured successfully ({format} format)"
            })
            
        except Exception as e:
            logger.error(f"Error taking screenshot: {str(e)}")
            return self.fail_response(f"Error taking screenshot: {str(e)}")

    @openapi_schema({
        "type": "function",
        "function": {
            "name": "upload_screenshot",
            "description": "Upload the current browser screenshot to S3 and return the URL",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string", 
                        "description": "Optional filename for the uploaded image"
                    }
                },
                "required": []
            }
        }
    })
    async def upload_screenshot(
        self,
        filename: Optional[str] = None
    ) -> ToolResult:
        """Take and upload a screenshot to S3."""
        try:
            # Take screenshot first
            screenshot_result = await self.take_screenshot(full_page=True)
            
            if not screenshot_result.success:
                return screenshot_result
            
            # Convert base64 to PIL Image
            image_data = base64.b64decode(screenshot_result.data['screenshot'])
            image = Image.open(io.BytesIO(image_data))
            
            # Generate filename if not provided
            if not filename:
                timestamp = int(asyncio.get_event_loop().time())
                filename = f"browser_screenshot_{timestamp}.png"
            
            # Upload to S3 using existing utility
            s3_url = await upload_base64_image(
                screenshot_result.data['screenshot'],
                filename,
                self.project_id
            )
            
            return self.success_response({
                "screenshot_url": s3_url,
                "filename": filename,
                "message": f"Screenshot uploaded successfully to {s3_url}"
            })
            
        except Exception as e:
            logger.error(f"Error uploading screenshot: {str(e)}")
            return self.fail_response(f"Error uploading screenshot: {str(e)}")

    @openapi_schema({
        "type": "function",
        "function": {
            "name": "get_page_info",
            "description": "Get information about the current page including title, URL, and metadata",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    })
    async def get_page_info(self) -> ToolResult:
        """Get current page information."""
        try:
            if not self.is_browser_available:
                return self.fail_response(
                    "Browser not available. Please configure AWS AgentCore Browser."
                )
            
            session_id = await self._ensure_browser_session()
            browser = await self._ensure_browser()
            
            page_info = await browser.get_page_info(session_id=session_id)
            
            return self.success_response({
                "url": page_info.get('url'),
                "title": page_info.get('title'),
                "viewport": page_info.get('viewport', {}),
                "user_agent": page_info.get('user_agent', ''),
                "cookies": page_info.get('cookies', []),
                "local_storage": page_info.get('local_storage', {}),
                "session_storage": page_info.get('session_storage', {})
            })
            
        except Exception as e:
            logger.error(f"Error getting page info: {str(e)}")
            return self.fail_response(f"Error getting page info: {str(e)}")

    @openapi_schema({
        "type": "function", 
        "function": {
            "name": "get_session_info",
            "description": "Get information about the current AgentCore Browser session"
        }
    })
    async def get_session_info(self) -> ToolResult:
        """Get browser session information and capabilities."""
        try:
            session_status = await self.get_session_status()
            
            return self.success_response({
                "project_id": self.project_id,
                "use_agentcore": self.use_agentcore,
                "session_id": self._browser_session_id,
                "browser_available": self.is_browser_available,
                "code_interpreter_available": self.is_code_interpreter_available,
                "capabilities": {
                    "navigation": "✅",
                    "content_extraction": "✅", 
                    "form_interaction": "✅",
                    "screenshots": "✅",
                    "s3_upload": "✅"
                }
            })
            
        except Exception as e:
            logger.error(f"Error getting session info: {str(e)}")
            return self.fail_response(f"Error getting session info: {str(e)}")

    async def get_live_view_url(self) -> Optional[str]:
        """Get the live view URL for the browser session."""
        try:
            if not self.is_browser_available:
                return None
                
            session_id = await self._ensure_browser_session()
            browser = await self._ensure_browser()
            
            return await browser.get_live_view_url(session_id)
            
        except Exception as e:
            logger.error(f"Error getting live view URL: {str(e)}")
            return None

    async def cleanup(self):
        """Clean up browser session."""
        try:
            # Terminate browser session if it exists
            if self._browser_session_id and self._browser:
                await self._browser.terminate_session(self._browser_session_id)
                logger.debug(f"Terminated browser session {self._browser_session_id}")
                self._browser_session_id = None
            
            # Clear session metadata
            if self._browser_session_id:
                await self._save_agentcore_metadata({
                    'browser_session_id': None
                })
            
            # Call parent cleanup
            await super().cleanup()
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    @property
    def tool_info(self) -> Dict[str, Any]:
        """Get tool information including AgentCore status."""
        info = super().tool_info or {}
        
        info.update({
            'backend': 'AWS AgentCore',
            'browser_available': self.is_browser_available,
            'code_interpreter_available': self.is_code_interpreter_available,
            'session_id': self._browser_session_id,
            'workspace_path': self.workspace_path,
            'project_id': self.project_id
        })
        
        return info
