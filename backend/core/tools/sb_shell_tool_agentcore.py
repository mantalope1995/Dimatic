"""
AgentCore Shell Tool

Refactored shell tool that uses AWS AgentCore Code Interpreter instead of Daytona.io.
Provides command execution capabilities with session management and tmux integration.
"""

import asyncio
from typing import Optional, Dict, Any
import time
from uuid import uuid4
from core.agentpress.tool import ToolResult, openapi_schema, tool_metadata
from core.agentcore.sandbox_tools_base import AgentCoreSandboxToolsBase
from core.agentpress.thread_manager import ThreadManager
from core.utils.logger import logger


@tool_metadata(
    display_name="Terminal & Commands (AgentCore)",
    description="Run commands, install packages, and execute scripts in your secure AWS AgentCore workspace",
    icon="Terminal",
    color="bg-blue-100 dark:bg-blue-800/50",
    is_core=True,
    weight=20,
    visible=True
)
class AgentCoreShellTool(AgentCoreSandboxToolsBase):
    """
    Shell command execution tool using AWS AgentCore Code Interpreter.
    
    Replaces Daytona sandbox execution with secure, isolated code execution
    in AWS-managed environments with automatic scaling.
    """

    def __init__(self, project_id: str, thread_manager: ThreadManager):
        super().__init__(project_id, thread_manager)
        self._tmux_sessions: Dict[str, str] = {}  # Maps session names to tmux session identifiers

    async def _ensure_tmux_session(self, session_name: str = "default") -> str:
        """Ensure a tmux session exists and return its identifier."""
        if session_name not in self._tmux_sessions:
            try:
                # Create a unique identifier for this tmux session
                tmux_id = f"agentcore-{self.project_id}-{session_name}-{uuid4().hex[:8]}"
                self._tmux_sessions[session_name] = tmux_id
                
                # Initialize tmux session in Code Interpreter
                init_command = f"tmux new-session -d -s {tmux_id} -c {self.workspace_path}"
                result = await self.execute_shell_command(init_command)
                
                if result.error:
                    raise RuntimeError(f"Failed to create tmux session: {result.error}")
                    
                logger.debug(f"Created tmux session {tmux_id} for {session_name}")
                
            except Exception as e:
                logger.error(f"Failed to create tmux session: {e}")
                raise RuntimeError(f"Failed to create tmux session: {str(e)}")
                
        return self._tmux_sessions[session_name]

    async def _cleanup_tmux_session(self, session_name: str):
        """Clean up a tmux session if it exists."""
        if session_name in self._tmux_sessions:
            try:
                tmux_id = self._tmux_sessions[session_name]
                kill_command = f"tmux kill-session -t {tmux_id} 2>/dev/null || true"
                await self.execute_shell_command(kill_command)
                del self._tmux_sessions[session_name]
                logger.debug(f"Cleaned up tmux session {tmux_id}")
            except Exception as e:
                logger.warning(f"Failed to cleanup tmux session {session_name}: {str(e)}")

    @openapi_schema({
        "type": "function",
        "function": {
            "name": "execute_command",
            "description": "Execute a shell command in the AWS AgentCore workspace. Commands can run in two modes: (1) BLOCKING (blocking=true): Command runs synchronously, waits for completion, returns full output, and automatically cleans up the session - NO need to call check_command_output afterwards. (2) NON-BLOCKING (blocking=false, default): Command runs in background tmux session - use check_command_output to monitor progress. Use blocking=true for quick commands (installs, file operations, builds). Use non-blocking for long-running processes (servers, watches).",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute. Use this for running CLI tools, installing packages, or system operations. Commands can be chained using &&, ||, and | operators."
                    },
                    "folder": {
                        "type": "string",
                        "description": "Optional relative path to a subdirectory of /workspace where the command should be executed. Example: 'data/pdfs'"
                    },
                    "session_name": {
                        "type": "string",
                        "description": "Optional name of the tmux session to use. Only relevant for NON-BLOCKING commands where you need to check output later. Ignored for blocking commands.",
                    },
                    "blocking": {
                        "type": "boolean",
                        "description": "If true, waits for command completion and returns output directly (session auto-cleaned, do NOT call check_command_output). If false (default), runs in background tmux session (use check_command_output to monitor).",
                        "default": False
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Optional timeout in seconds for blocking commands. Defaults to 60. Ignored for non-blocking commands.",
                        "default": 60
                    }
                },
                "required": ["command"]
            }
        }
    })
    async def execute_command(
        self, 
        command: str, 
        folder: Optional[str] = None,
        session_name: Optional[str] = None,
        blocking: bool = False,
        timeout: int = 60
    ) -> ToolResult:
        """Execute a shell command using AgentCore Code Interpreter."""
        try:
            if not self.is_code_interpreter_available:
                return self.fail_response(
                    "Code Interpreter not available. Please configure AWS AgentCore Code Interpreter."
                )
            
            # Set up working directory
            cwd = self.workspace_path
            if folder:
                folder = folder.strip('/')
                cwd = f"{self.workspace_path}/{folder}"
            
            # Generate a session name if not provided
            if not session_name:
                session_name = f"session_{str(uuid4())[:8]}"
            
            if blocking:
                # For blocking execution, run command directly and capture output
                full_command = f"cd {cwd} && {command}"
                result = await self.execute_shell_command(
                    command=full_command,
                    working_dir=cwd,
                    timeout=timeout
                )
                
                if result.error:
                    return self.fail_response(f"Command execution failed: {result.error}")
                
                return self.success_response({
                    "output": result.output,
                    "cwd": cwd,
                    "completed": True,
                    "execution_time": result.execution_time,
                    "exit_code": result.exit_code
                })
            else:
                # For non-blocking execution, use tmux session
                tmux_id = await self._ensure_tmux_session(session_name)
                
                # Prepare command for tmux
                full_command = f"cd {cwd} && {command}"
                tmux_command = f'tmux send-keys -t {tmux_id} "{full_command}" Enter'
                
                # Send command to tmux session
                result = await self.execute_shell_command(tmux_command)
                
                if result.error:
                    return self.fail_response(f"Failed to start command in tmux session: {result.error}")
                
                return self.success_response({
                    "session_name": session_name,
                    "tmux_id": tmux_id,
                    "cwd": cwd,
                    "message": f"Command sent to tmux session '{session_name}'. Use check_command_output to view results.",
                    "completed": False
                })
                
        except Exception as e:
            logger.error(f"Error executing command: {str(e)}")
            return self.fail_response(f"Error executing command: {str(e)}")

    @openapi_schema({
        "type": "function",
        "function": {
            "name": "check_command_output",
            "description": "Check the output of a NON-BLOCKING command running in a tmux session. IMPORTANT: Only use this for commands that were executed with blocking=false. Do NOT use this for blocking commands - they return output directly and clean up their session automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_name": {
                        "type": "string",
                        "description": "The name of the tmux session to check. This is returned by execute_command when blocking=false."
                    },
                    "kill_session": {
                        "type": "boolean",
                        "description": "Whether to terminate the tmux session after checking. Set to true when you're done with the command.",
                        "default": False
                    }
                },
                "required": ["session_name"]
            }
        }
    })
    async def check_command_output(
        self,
        session_name: str,
        kill_session: bool = False
    ) -> ToolResult:
        """Check the output of a non-blocking command running in a tmux session."""
        try:
            if not self.is_code_interpreter_available:
                return self.fail_response(
                    "Code Interpreter not available. Please configure AWS AgentCore Code Interpreter."
                )
            
            if session_name not in self._tmux_sessions:
                return self.fail_response(f"Tmux session '{session_name}' does not exist.")
            
            tmux_id = self._tmux_sessions[session_name]
            
            # Check if tmux session exists
            check_command = f"tmux has-session -t {tmux_id} 2>/dev/null || echo 'SESSION_NOT_FOUND'"
            result = await self.execute_shell_command(check_command)
            
            if "SESSION_NOT_FOUND" in result.output:
                # Clean up from our tracking
                del self._tmux_sessions[session_name]
                return self.fail_response(f"Tmux session '{session_name}' no longer exists.")
            
            # Get output from tmux pane
            capture_command = f"tmux capture-pane -t {tmux_id} -p -S - -E -"
            capture_result = await self.execute_shell_command(capture_command)
            
            if capture_result.error:
                return self.fail_response(f"Failed to capture tmux output: {capture_result.error}")
            
            output = capture_result.output
            
            # Kill session if requested
            termination_status = "Session still running."
            if kill_session:
                await self._cleanup_tmux_session(session_name)
                termination_status = "Session terminated."
            
            return self.success_response({
                "output": output,
                "session_name": session_name,
                "tmux_id": tmux_id,
                "status": termination_status
            })
                
        except Exception as e:
            logger.error(f"Error checking command output: {str(e)}")
            return self.fail_response(f"Error checking command output: {str(e)}")

    @openapi_schema({
        "type": "function",
        "function": {
            "name": "terminate_command",
            "description": "Terminate a running command by killing its tmux session.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_name": {
                        "type": "string",
                        "description": "The name of the tmux session to terminate."
                    }
                },
                "required": ["session_name"]
            }
        }
    })
    async def terminate_command(
        self,
        session_name: str
    ) -> ToolResult:
        """Terminate a running command by killing its tmux session."""
        try:
            if not self.is_code_interpreter_available:
                return self.fail_response(
                    "Code Interpreter not available. Please configure AWS AgentCore Code Interpreter."
                )
            
            if session_name not in self._tmux_sessions:
                return self.fail_response(f"Tmux session '{session_name}' does not exist.")
            
            await self._cleanup_tmux_session(session_name)
            
            return self.success_response({
                "message": f"Tmux session '{session_name}' terminated successfully."
            })
                
        except Exception as e:
            logger.error(f"Error terminating command: {str(e)}")
            return self.fail_response(f"Error terminating command: {str(e)}")

    @openapi_schema({
        "type": "function",
        "function": {
            "name": "list_commands",
            "description": "List all running tmux sessions and their status.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    })
    async def list_commands(self) -> ToolResult:
        """List all running tmux sessions."""
        try:
            if not self.is_code_interpreter_available:
                return self.fail_response(
                    "Code Interpreter not available. Please configure AWS AgentCore Code Interpreter."
                )
            
            # List all tmux sessions
            list_command = "tmux list-sessions 2>/dev/null || echo 'NO_SESSIONS'"
            result = await self.execute_shell_command(list_command)
            
            if result.error:
                return self.fail_response(f"Failed to list tmux sessions: {result.error}")
            
            if "NO_SESSIONS" in result.output or not result.output.strip():
                return self.success_response({
                    "message": "No active tmux sessions found.",
                    "sessions": []
                })
            
            # Parse session list and match with our tracking
            sessions = []
            lines = result.output.strip().split('\n')
            
            for line in lines:
                if line.strip():
                    parts = line.split(':')
                    if parts:
                        tmux_id = parts[0].strip()
                        
                        # Find corresponding session name
                        session_name = None
                        for name, tracked_tmux_id in self._tmux_sessions.items():
                            if tracked_tmux_id == tmux_id:
                                session_name = name
                                break
                        
                        sessions.append({
                            'session_name': session_name,
                            'tmux_id': tmux_id,
                            'full_line': line.strip()
                        })
            
            return self.success_response({
                "message": f"Found {len(sessions)} active sessions.",
                "sessions": sessions
            })
                
        except Exception as e:
            logger.error(f"Error listing commands: {str(e)}")
            return self.fail_response(f"Error listing commands: {str(e)}")

    async def cleanup(self):
        """Clean up all tmux sessions."""
        try:
            # Clean up all tracked tmux sessions
            for session_name in list(self._tmux_sessions.keys()):
                await self._cleanup_tmux_session(session_name)
            
            # Also call parent cleanup
            await super().cleanup()
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    @property
    def tool_info(self) -> Dict[str, Any]:
        """Get tool information including AgentCore status."""
        info = super().tool_info or {}
        
        info.update({
            'backend': 'AWS AgentCore',
            'code_interpreter_available': self.is_code_interpreter_available,
            'browser_available': self.is_browser_available,
            'active_tmux_sessions': len(self._tmux_sessions),
            'tmux_sessions': list(self._tmux_sessions.keys())
        })
        
        return info
