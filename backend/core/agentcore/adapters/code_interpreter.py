"""
AgentCore Code Interpreter Adapter

Provides interface to AWS Bedrock AgentCore Code Interpreter for secure code execution.
Handles code execution, shell commands, and file operations in isolated sandboxes.

AWS Bedrock code interpretation is now available in ap-southeast-2 (Australia),
which is the required region for Phase 1 of this migration.
"""

import asyncio
import boto3
import botocore.exceptions
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from ..config import AgentCoreConfig, get_config, Environment
from ..models import CodeInterpreterSession, SessionStatus, CodeExecutionResult, ShellCommandResult
from ..errors import (
    AgentCoreError,
    AgentCoreSessionError,
    AgentCoreExecutionError,
    ServiceUnavailableError,
    is_retryable_error,
    with_retry,
    safe_log,
)

logger = logging.getLogger(__name__)


class AgentCoreCodeInterpreterAdapter:
    """
    Adapter for AgentCore Code Interpreter

    This adapter provides methods to:
    - Execute code in isolated environments
    - Execute shell commands
    - Upload/download files
    - List files in the execution environment
    - Manage Code Interpreter sessions
    - Handle timeouts and resource limits

    The adapter wraps AWS Bedrock Agents Runtime API with code interpretation enabled.
    """

    # Agent ID for code interpretation (must be configured separately)
    # This should be created with code interpretation enabled via AWS console or API
    DEFAULT_AGENT_ID: Optional[str] = None
    DEFAULT_AGENT_ALIAS_ID: str = "DNTAB6Q4T9"  # "DRAFT" alias

    def __init__(self, config: Optional[AgentCoreConfig] = None):
        """
        Initialize AgentCore Code Interpreter adapter

        Args:
            config: AgentCore configuration (uses global config if not provided)
        """
        self.config = config or get_config()
        self._validate_config()
        self._initialize_clients()

        # Session management
        self._sessions: Dict[str, CodeInterpreterSession] = {}
        self._active_sessions: Dict[str, Any] = {}  # Track active sessions per project

    def _validate_config(self):
        """Validate that Code Interpreter is enabled and configured"""
        if not self.config.code_interpreter_enabled:
            raise ValueError("AgentCore Code Interpreter is not enabled in configuration")

        if not self.config.s3_bucket_name:
            raise ValueError("S3 bucket required for Code Interpreter file operations")

        # Verify region is ap-southeast-2 for Phase 1 compliance
        if self.config.aws_region != "ap-southeast-2" and self.config.environment != Environment.LOCAL:
            logger.info(
                f"Code Interpreter using region {self.config.aws_region}. "
                f"Phase 1 recommends ap-southeast-2 for Australian data residency."
            )

    def _initialize_clients(self):
        """Initialize AWS SDK clients for AgentCore Code Interpreter"""
        logger.info(
            f"Initializing AgentCore Code Interpreter adapter for {self.config.environment} environment "
            f"in {self.config.aws_region}"
        )

        # Initialize Bedrock Agent Runtime client for invoking agents with code interpretation
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

        # Initialize S3 client for file operations
        self.s3_client = boto3.client(
            "s3",
            region_name=self.config.aws_region,
            **session_kwargs
        )

        logger.info("AgentCore Code Interpreter adapter initialized successfully")

    async def create_session(
        self,
        project_id: str,
        timeout_seconds: Optional[int] = None,
        memory_limit_mb: Optional[int] = None
    ) -> CodeInterpreterSession:
        """
        Create a new Code Interpreter session for a project

        Args:
            project_id: Project identifier for the session
            timeout_seconds: Session timeout (default: from config)
            memory_limit_mb: Memory limit in MB (default: from config)

        Returns:
            CodeInterpreterSession: Created session metadata

        Raises:
            AgentCoreSessionError: If session creation fails
        """
        from ..models import serialize_session

        session_id = f"ci-{project_id}-{datetime.utcnow().timestamp()}"

        # Use config defaults if not specified
        if timeout_seconds is None:
            timeout_seconds = self.config.code_interpreter_session_timeout_seconds
        if memory_limit_mb is None:
            memory_limit_mb = self.config.code_interpreter_memory_limit_mb

        session = CodeInterpreterSession(
            session_id=session_id,
            project_id=project_id,
            status=SessionStatus.READY,
            timeout_seconds=timeout_seconds,
            memory_limit_mb=memory_limit_mb,
            region=self.config.aws_region
        )

        self._sessions[session_id] = session
        self._active_sessions[project_id] = session_id

        safe_log(
            f"Created Code Interpreter session: {session_id} for project {project_id} "
            f"(timeout={timeout_seconds}s, memory={memory_limit_mb}MB)"
        )

        return session

    async def get_session(self, session_id: str) -> CodeInterpreterSession:
        """
        Get session metadata

        Args:
            session_id: Session identifier

        Returns:
            CodeInterpreterSession: Session metadata

        Raises:
            AgentCoreSessionError: If session not found
        """
        if session_id not in self._sessions:
            raise AgentCoreSessionError(f"Session not found: {session_id}")

        return self._sessions[session_id]

    async def stop_session(self, session_id: str) -> None:
        """
        Stop and clean up a Code Interpreter session

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

        safe_log(f"Stopped Code Interpreter session: {session_id}")

    async def get_project_session(
        self,
        project_id: str,
        timeout_seconds: Optional[int] = None,
        memory_limit_mb: Optional[int] = None
    ) -> CodeInterpreterSession:
        """
        Get or create a session for a project

        Args:
            project_id: Project identifier
            timeout_seconds: Session timeout for new sessions
            memory_limit_mb: Memory limit for new sessions

        Returns:
            CodeInterpreterSession: Existing or newly created session
        """
        if project_id in self._active_sessions:
            session_id = self._active_sessions[project_id]
            if session_id in self._sessions:
                return self._sessions[session_id]

        return await self.create_session(project_id, timeout_seconds, memory_limit_mb)

    async def execute_code(
        self,
        code: str,
        language: str = "python",
        files: Optional[List[str]] = None,
        timeout: Optional[int] = None,
        session_id: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> CodeExecutionResult:
        """
        Execute code in isolated environment

        Args:
            code: Code to execute
            language: Programming language (python, javascript, etc.)
            files: Optional list of file paths to make available
            timeout: Execution timeout in seconds
            session_id: Existing session ID (optional, creates new if not provided)
            project_id: Project ID for automatic session management

        Returns:
            CodeExecutionResult: Execution result with output, error, exit code

        Raises:
            AgentCoreExecutionError: If execution fails
        """
        start_time = datetime.utcnow()

        safe_log(f"Executing {language} code ({len(code)} chars)")

        # Get or create session
        if session_id:
            session = await self.get_session(session_id)
        elif project_id:
            session = await self.get_project_session(project_id, timeout)
        else:
            raise ValueError("Either session_id or project_id must be provided")

        # Use configured timeout if not specified
        if timeout is None:
            timeout = self.config.code_interpreter_timeout_seconds

        try:
            # Check if agent ID is configured
            agent_id = self.DEFAULT_AGENT_ID or self.config.aws_region + "-code-interpreter"
            agent_alias_id = self.DEFAULT_AGENT_ALIAS_ID

            # Prepare the prompt for code execution
            prompt = f"Execute the following {language} code:\n\n```\n{code}\n```\n\nReturn only the output of the code execution."

            # Invoke the agent with code interpretation
            response = await with_retry(
                self._invoke_agent,
                agent_id=agent_id,
                agent_alias_id=agent_alias_id,
                session_id=session.session_id,
                prompt=prompt
            )

            # Parse the response
            output = response or ""
            error = None
            exit_code = 0
            files_created = []

            # Check for errors in the response
            if "error" in output.lower() or "exception" in output.lower():
                error = output
                exit_code = 1

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            result = CodeExecutionResult(
                output=output,
                error=error,
                exit_code=exit_code,
                execution_time_seconds=execution_time,
                files_created=files_created
            )

            safe_log(f"Code execution completed (exit_code={exit_code}, time={execution_time:.2f}s)")
            return result

        except botocore.exceptions.ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_message = e.response.get('Error', {}).get('Message', str(e))

            # Check for specific error conditions
            if error_code in ['ResourceNotFoundException', 'ValidationException']:
                raise ServiceUnavailableError(
                    f"AgentCore Code Interpreter not configured: {error_message}. "
                    f"Please create an agent with code interpretation enabled."
                )

            logger.error(f"Code execution failed: {error_message}")
            raise AgentCoreExecutionError(f"Code execution failed: {error_message}")

        except Exception as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.error(f"Code execution failed: {str(e)}")

            raise AgentCoreExecutionError(f"Code execution failed: {str(e)}")

    async def execute_shell_command(
        self,
        command: str,
        working_dir: str = "/workspace",
        timeout: Optional[int] = None,
        session_id: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> ShellCommandResult:
        """
        Execute shell command

        Args:
            command: Shell command to execute
            working_dir: Working directory for command execution
            timeout: Execution timeout in seconds
            session_id: Existing session ID (optional)
            project_id: Project ID for automatic session management

        Returns:
            ShellCommandResult: Command result with stdout, stderr, exit code

        Raises:
            AgentCoreExecutionError: If execution fails
        """
        start_time = datetime.utcnow()

        safe_log(f"Executing shell command: {command}")

        # Get or create session
        if session_id:
            session = await self.get_session(session_id)
        elif project_id:
            session = await self.get_project_session(project_id, timeout)
        else:
            raise ValueError("Either session_id or project_id must be provided")

        # Use configured timeout if not specified
        if timeout is None:
            timeout = self.config.code_interpreter_timeout_seconds

        try:
            # Prepare the prompt for shell command execution
            # Use subprocess to execute the command
            python_code = f'''
import subprocess
import json
import os

os.chdir("{working_dir}")
result = subprocess.run(
    "{command}",
    shell=True,
    capture_output=True,
    text=True,
    timeout={timeout}
)

output = json.dumps({{
    "stdout": result.stdout,
    "stderr": result.stderr,
    "exit_code": result.returncode
}})
print(output)
'''

            # Execute the Python code that runs the shell command
            code_result = await self.execute_code(
                code=python_code,
                language="python",
                session_id=session.session_id,
                timeout=timeout
            )

            # Parse the JSON output
            import json

            if code_result.exit_code == 0 and code_result.output:
                try:
                    # Extract JSON from the output (might have extra text)
                    output_lines = code_result.output.split('\n')
                    for line in output_lines:
                        if line.strip().startswith('{'):
                            command_result = json.loads(line)
                            break
                    else:
                        # No JSON found, treat entire output as stdout
                        command_result = {
                            "stdout": code_result.output,
                            "stderr": code_result.error or "",
                            "exit_code": code_result.exit_code
                        }
                except json.JSONDecodeError:
                    command_result = {
                        "stdout": code_result.output,
                        "stderr": code_result.error or "Failed to parse output",
                        "exit_code": code_result.exit_code
                    }
            else:
                command_result = {
                    "stdout": "",
                    "stderr": code_result.error or "Command execution failed",
                    "exit_code": code_result.exit_code
                }

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            result = ShellCommandResult(
                stdout=command_result.get("stdout", ""),
                stderr=command_result.get("stderr", ""),
                exit_code=command_result.get("exit_code", 1),
                execution_time_seconds=execution_time
            )

            safe_log(
                f"Shell command completed (exit_code={result.exit_code}, time={execution_time:.2f}s)"
            )
            return result

        except AgentCoreExecutionError:
            raise
        except Exception as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            logger.error(f"Shell command execution failed: {str(e)}")

            raise AgentCoreExecutionError(f"Shell command execution failed: {str(e)}")

    async def upload_file(
        self,
        file_path: str,
        content: bytes,
        session_id: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> str:
        """
        Upload file to Code Interpreter environment

        Args:
            file_path: Destination file path in the environment
            content: File content as bytes
            session_id: Existing session ID (optional)
            project_id: Project ID for automatic session management

        Returns:
            file_path: Path to uploaded file

        Raises:
            AgentCoreExecutionError: If upload fails
        """
        safe_log(f"Uploading file: {file_path} ({len(content)} bytes)")

        try:
            # Upload to S3 with AgentCore-compatible path
            s3_key = f"{self.config.get_resource_prefix()}/files/{file_path}"

            await asyncio.to_thread(
                self.s3_client.put_object,
                Bucket=self.config.s3_bucket_name,
                Key=s3_key,
                Body=content
            )

            safe_log(f"File uploaded successfully: {file_path}")
            return file_path

        except botocore.exceptions.ClientError as e:
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"File upload failed: {error_message}")
            raise AgentCoreExecutionError(f"File upload failed: {error_message}")

        except Exception as e:
            logger.error(f"File upload failed: {str(e)}")
            raise AgentCoreExecutionError(f"File upload failed: {str(e)}")

    async def download_file(self, file_path: str) -> bytes:
        """
        Download file from Code Interpreter environment

        Args:
            file_path: File path in the environment

        Returns:
            File content as bytes

        Raises:
            AgentCoreExecutionError: If download fails
        """
        safe_log(f"Downloading file: {file_path}")

        try:
            # Download from S3
            s3_key = f"{self.config.get_resource_prefix()}/files/{file_path}"

            response = await asyncio.to_thread(
                self.s3_client.get_object,
                Bucket=self.config.s3_bucket_name,
                Key=s3_key
            )

            content = response['Body'].read()

            safe_log(f"File downloaded successfully: {file_path} ({len(content)} bytes)")
            return content

        except botocore.exceptions.ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_message = e.response.get('Error', {}).get('Message', str(e))

            if error_code == 'NoSuchKey':
                raise AgentCoreExecutionError(f"File not found: {file_path}")

            logger.error(f"File download failed: {error_message}")
            raise AgentCoreExecutionError(f"File download failed: {error_message}")

        except Exception as e:
            logger.error(f"File download failed: {str(e)}")
            raise AgentCoreExecutionError(f"File download failed: {str(e)}")

    async def list_files(self, directory: str = "/workspace") -> List[str]:
        """
        List files in directory

        Args:
            directory: Directory path to list

        Returns:
            List of file paths

        Raises:
            AgentCoreExecutionError: If listing fails
        """
        safe_log(f"Listing files in directory: {directory}")

        try:
            # Prepare code to list files
            python_code = f'''
import os
import json

files = []
if os.path.exists("{directory}"):
    for item in os.listdir("{directory}"):
        path = os.path.join("{directory}", item)
        if os.path.isfile(path):
            files.append(path)
        elif os.path.isdir(path):
            for root, dirs, filenames in os.walk(path):
                for filename in filenames:
                    files.append(os.path.join(root, filename))

print(json.dumps(files))
'''

            # Execute code to list files
            result = await self.execute_code(
                code=python_code,
                language="python"
            )

            if result.exit_code == 0:
                import json
                try:
                    # Extract JSON from output
                    output_lines = result.output.split('\n')
                    for line in output_lines:
                        if line.strip().startswith('['):
                            files = json.loads(line)
                            safe_log(f"Found {len(files)} files")
                            return files
                except json.JSONDecodeError:
                    pass

            # Fallback: empty list
            files = []
            safe_log(f"Found {len(files)} files")
            return files

        except AgentCoreExecutionError:
            raise
        except Exception as e:
            logger.error(f"File listing failed: {str(e)}")
            raise AgentCoreExecutionError(f"File listing failed: {str(e)}")

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
            safe_log(f"Cleaned up {cleaned} expired Code Interpreter sessions")

        return cleaned
