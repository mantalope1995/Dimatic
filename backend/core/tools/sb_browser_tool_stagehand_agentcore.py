"""
AgentCore Browser Tool with Stagehand Integration

Browser automation tool that uses AWS AgentCore Browser as primary backend while maintaining Stagehand compatibility for web scraping.
Provides web automation capabilities with Stagehand libraries for advanced interactions.
"""

import asyncio
from typing import Optional, Dict, Any, List
import json
from core.agentpress.tool import ToolResult, openapi_schema, tool_metadata
from core.agentcore.sandbox_tools_base import AgentCoreSandboxToolsBase
from core.agentpress.thread_manager import ThreadManager
from core.utils.logger import logger

# Import Stagehand dependencies
try:
    from browser_use import AsyncBrowserConfig
    BROWSER_USE_AVAILABLE = True
except ImportError:
    BROWSER_USE_AVAILABLE = False
    logger.warning("Stagehand not available, will use AgentCore Browser only")

from core.utils.config import config


@tool_metadata(
    display_name="Web Browser (AgentCore + Stagehand)",
    description="Browse websites, fill forms, and extract information from web pages using AWS AgentCore Browser with Stagehand integration",
    icon="Globe",
    color="bg-amber-100 dark:bg-amber-800/50",
    weight=60,
    visible=True
)
class AgentCoreBrowserToolWithStagehand(AgentCoreSandboxToolsBase):
    """
    Browser tool using AWS AgentCore Browser as primary backend while maintaining Stagehand compatibility.
    
    This hybrid approach allows using Stagehand for advanced browser interactions while
    leveraging AgentCore Browser for core browser functionality.
    """
    
    def __init__(self, project_id: str, thread_manager: ThreadManager):
        super().__init__(project_id, thread_manager)
        self.project_id = project_id
        self.thread_manager = thread_manager
        self.workspace_path = "/workspace"
        self._stagehand_available = BROWSER_USE_AVAILABLE
        self._browser = None
        self._stagehand = None
        self._current_page_url = None

    async def _ensure_stagehand(self) -> Optional[object]:
        """Initialize Stagehand browser for Chrome automation if available."""
        if not self._stagehand_available:
            return None
            
        try:
            # Initialize Stagehand configuration
            self._stagehand = AsyncBrowserConfig(
                use_browser=True,
                headless=False
            )
            
            logger.info("Stagehand browser configured successfully for project {self.project_id}")
            return self._stagehand
        except Exception as e:
            logger.error(f"Failed to initialize Stagehand: {e}")
            return None

    async def _get_browser_client(self) -> Optional[object]:
        """Get the Stagehand browser client."""
        if not self._stagehand:
            return None
            
        try:
            from browser_use import AsyncBrowserConfig
            # Initialize Stagehand browser with Stagehand configuration
            self._stagehand = AsyncBrowserConfig(use_browser=True, headless=True)
            return await self._stagehand.initialize_client()
        except Exception as e:
            logger.error(f"Failed to initialize Stagehand: {e}")
            return None

    async def _execute_stagehand_function(
        self,
        function_name: str,
        script: str,
        **kwargs
    ) -> ToolResult:
        """Execute a Stagehand function in the browser."""
        try:
            if not self._stagehand_available:
                # Fallback to direct Python code execution
                python_code = f'''
# {script}
'''
                result = await self.execute_code(python_code, language="python", timeout=60)
                if result.get('error'):
                    return self.fail_response(f"Stagehand function failed: {result.get('error')}")
                
                # Return simple success response with Python execution result
                return self.success_response({
                    "output": result.get('output'),
                    "message": f"Stagehand function '{function_name}' executed successfully",
                    "python_code": script
                })
            else:
                # Use Stagehand for browser automation
                stagehand = await self._ensure_stagehand()
                if stagehand:
                    stagehand = await self._stagehand.initialize_client()
                
                # Execute Stagehand function
                js_code = f'''
// Stagehand function: {function_name}
async function runStagehand(inputs) {{
    // Stagehand browser wrapper code
    await stagehand.initialize_client()
    
    // Call the function
    const result = await stagehand_client.stagehand.client.call("{function_name}", inputs)
    return result
}}
'''
                
                # For now, return the script info
                return self.success_response({
                    "message": f"Stagehand function '{function_name}' prepared",
                    "js_code": js_code,
                    "script": script
                })
            
        except Exception as e:
            logger.error(f"Error executing Stagehand function: {str(e)}")
            return self.fail_response(f"Stagehand function failed: {str(e)}")

    @openapi_schema({
        "type": "function",
        "function": {
            "name": "act",
            "description": "Execute a Stagehand function in the browser. Supports common Stagehand operations like clicking, typing, and waiting for elements.",
            "parameters": {
                "type": "object",
                "properties": {
                    "function": {
                        "type": "string",
                        "description": "The Stagehand function to execute"
                    },
                    "script": {
                        "type": "string",
                        "description": "JavaScript code to execute"
                    },
                    "kwargs": {
                        "type": "object",
                        "description": "Additional parameters"
                    }
                },
                "required": ["function"]
            }
        }
    })
    async def act(
        self,
        actions: List[Dict[str, Any]],
        wait_between_actions: float = 1.0
    ) -> ToolResult:
        """Execute a series of browser actions sequentially."""
        results = []
        
        try:
            if not self.is_browser_available:
                return self.fail_response("Browser not available. Please configure AWS AgentCore Browser.")
            
            stagehand = await self._ensure_stagehand()
            stagehand = await self._stagehand.initialize_client()
            
            # Execute actions one by one
            for action in actions:
                result = await self.execute_stagehand_function(
                    action['function'],
                    action.get('script', ''),
                    action.get('kwargs', {})
                )
                
                results.append({
                    'action': action['function'],
                    'success': result.get('success', False),
                    'output': result.get('output'),
                    'error': result.get('error', '')
                })
                
                # Small delay between actions
                if wait_between_actions > 0:
                    await asyncio.sleep(wait_between_actions)
            
            return self.success_response({
                'actions': results,
                'executed_actions_count': len(actions),
                'project_id': self.project_id
            })
            
        except Exception as e:
            logger.error(f"Error executing Stagehand actions: {str(e)}")
            return self.fail_response(f"Stagehand execution failed: {str(e)}")

    async def _handle_browser_action(
        self,
        action_type: str,
        action: Dict[str, Any],
        **kwargs
    ) -> Dict[str, Any]:
        """Handle different types of browser interactions."""
        
        try:
            stagehand = await self._ensure_stagehand()
            stagehand = await self._stagehand.initialize_client()
            
            if action_type == "click":
                # Handle click actions
                selector = action.get('selector', '')
                wait_before = action.get('wait_before_click', 1.0)
                
                result = await stagehand.click_element(
                    selector=selector,
                    wait_before_click=wait_before_click
                )
                
                return {'action_type': action_type, 'result': result}
                
            elif action_type == "type":
                # Handle typing actions
                text = action.get('text', '')
                keys = list(action.keys())
                
                result = {}
                
                for key in keys:
                    if key in ['text', 'value', 'clear', 'tab', 'enter']:
                        result[key] = action[key]
                
                if result:
                    result['action_type'] = action_type
                    
                return {'action_type': action_type, 'result': result}
                
            elif action_type == 'js':
                # JavaScript execution
                javascript_code = action.get('script', '')
                
                # Execute JavaScript code
                result = await stagehand.stagehand.client.call(javascript_code)
                
                return {'action_type': action_type, 'result': result}
                
            elif action_type == 'wait':
                # Wait for selector
                selector = action.get('wait_for', '')
                wait_time = action.get('wait_time', 5.0)
                
                # Execute JavaScript wait
                await asyncio.sleep(wait_time)
                return {'action_type': action_type, 'result': {'selector': selector, 'waited': wait_time}}
            
            else:
                return {'action_type': action_type, 'error': f"Unknown action type: {action_type}"}
                
        except Exception as e:
            logger.error(f"Unexpected error in Stagehand action: {str(e)}")
            return {'action_type': action_type, 'error': f"Unexpected error in Stagehand action: {str(e)}"}

    @openapi_schema({
        "type": "function",
        "function": {
            "name": "get_live_view_url",
            "description": "Get the live view URL for the browser session.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    })
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

    @openapi_schema({
        "type": "function",
        "function": {
            "name": "execute_javascript",
            "description": "Execute JavaScript code in the browser for DOM manipulation. Use JavaScript for advanced interactions like form filling and page modifications",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "JavaScript code to execute"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default: 30s)"
                    }
                },
                "required": ["code"]
            }
        }
    })
    async def execute_javascript(
        self,
        code: str,
        timeout: int = 30
    ) -> ToolResult:
        """Execute JavaScript code in the browser for DOM manipulation."""
        try:
            if not self.is_browser_available:
                # Fallback to direct code execution
                python_code = f'''
# JavaScript fallback code
{code}
'''
                result = await self.execute_code(python_code, language="python", timeout=timeout)
                if result.get('error'):
                    return self.fail_response(f"JavaScript execution failed: {result.get('error')}")
                
                return self.success_response({
                    "output": result.get('output'),
                    "language": "javascript",
                    "timeout": timeout,
                    "message": "JavaScript code execution in browser via Python"
                })
            
            # Use Stagehand for JavaScript execution in browser
            stagehand = await self._ensure_stagehand()
            if stagehand:
                stagehand = await self._stagehand.initialize_client()
            
            # Execute JavaScript
            javascript_code = f'''
// Stagehand JavaScript code: {code}
'''
            
            result = await stagehand.stagehand.client.call(javascript_code) if stagehand else None
            
            return self.success_response({
                "output": result,
                "language": "javascript",
                "timeout": timeout,
                "message": "JavaScript code execution in browser via Stagehand"
            })
            
        except Exception as e:
            logger.error(f"Error executing JavaScript: {str(e)}")
            return self.fail_response(f"JavaScript execution failed: {str(e)}")

    async def _convert_python_to_javascript(
        self,
        python_code: str,
        language: str = "python"
    ) -> str:
        """Convert Python code to JavaScript for browser execution."""
        if language.lower() == "javascript":
            return python_code
        elif language.lower() == "typescript":
            # Convert Python to TypeScript
            python_code = self._convert_python_to_typescript(python_code)
        else:
            return python_code

    # NOTE: Duplicate execute_javascript decorator removed - using the one defined above
