"""
AgentCore Code Interpreter Adapter

Provides an adapter for AWS AgentCore Code Interpreter to replace Daytona.io sandbox functionality.
Supports secure code execution, file operations, and shell commands in isolated environments.
"""

import asyncio
import base64
import json
import tempfile
import uuid
from typing import Optional, Dict, Any, List, AsyncGenerator
from dataclasses import dataclass
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from core.utils.logger import logger
from core.utils.config import config


@dataclass
class CodeExecutionResult:
    """Result from code execution in AgentCore Code Interpreter."""
    output: str
    error: Optional[str] = None
    exit_code: Optional[int] = None
    files_created: List[str] = None
    execution_time: Optional[float] = None
    
    def __post_init__(self):
        if self.files_created is None:
            self.files_created = []


@dataclass
class SessionConfig:
    """Configuration for Code Interpreter sessions."""
    session_id: str
    timeout_minutes: int = 15
    memory_mb: int = 2048
    cpu_cores: int = 2
    enable_internet: bool = True


class AgentCoreCodeInterpreterAdapter:
    """
    Adapter for AWS AgentCore Code Interpreter service.
    
    Replaces Daytona.io sandbox functionality with AWS-native code execution.
    Provides secure, isolated execution environments for Python, TypeScript, and JavaScript.
    """
    
    def __init__(self):
        self.region_name = getattr(config, 'AWS_REGION', 'us-east-1')
        self.code_interpreter_tool_id = getattr(config, 'AGENTCORE_CODE_INTERPRETER_TOOL_ID', None)
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
            logger.info("AWS AgentCore clients initialized successfully")
        except NoCredentialsError:
            logger.error("AWS credentials not found. Please configure AWS credentials.")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize AWS clients: {e}")
            raise
        
        # Active sessions cache
        self._active_sessions: Dict[str, Dict[str, Any]] = {}
        
    async def create_session(
        self, 
        project_id: str,
        timeout_minutes: int = 15,
        memory_mb: int = 2048,
        enable_internet: bool = True
    ) -> str:
        """
        Create a new Code Interpreter session for a project.
        
        Args:
            project_id: Project identifier for isolation
            timeout_minutes: Session timeout in minutes
            memory_mb: Memory limit for the session
            enable_internet: Whether to allow internet access
            
        Returns:
            Session ID for the created session
        """
        if not self.code_interpreter_tool_id:
            raise ValueError("AGENTCORE_CODE_INTERPRETER_TOOL_ID not configured")
            
        try:
            session_id = f"{project_id}-{uuid.uuid4().hex[:8]}"
            
            # Create Code Interpreter session
            response = self.bedrock_agentcore_client.create_code_interpreter_session(
                codeInterpreterId=self.code_interpreter_tool_id,
                sessionId=session_id,
                timeoutInMinutes=timeout_minutes,
                enableInternet=enable_internet
            )
            
            # Cache session metadata
            self._active_sessions[session_id] = {
                'project_id': project_id,
                'created_at': asyncio.get_event_loop().time(),
                'timeout_minutes': timeout_minutes,
                'status': 'initializing'
            }
            
            logger.info(f"Created Code Interpreter session {session_id} for project {project_id}")
            return session_id
            
        except ClientError as e:
            logger.error(f"Failed to create Code Interpreter session: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating session: {e}")
            raise
    
    async def execute_code(
        self,
        session_id: str,
        code: str,
        language: str = "python",
        timeout: int = 30
    ) -> CodeExecutionResult:
        """
        Execute code in a Code Interpreter session.
        
        Args:
            session_id: ID of the active session
            code: Code to execute
            language: Programming language (python, typescript, javascript)
            timeout: Execution timeout in seconds
            
        Returns:
            CodeExecutionResult with output and metadata
        """
        if session_id not in self._active_sessions:
            raise ValueError(f"Session {session_id} not found or not initialized")
            
        try:
            start_time = asyncio.get_event_loop().time()
            
            # Prepare execution request
            execution_request = {
                'sessionId': session_id,
                'language': language.lower(),
                'code': code,
                'timeoutInSeconds': min(timeout, self._active_sessions[session_id]['timeout_minutes'] * 60)
            }
            
            # Execute code
            response = self.bedrock_agentcore_client.invoke_code_interpreter(
                **execution_request
            )
            
            execution_time = asyncio.get_event_loop().time() - start_time
            
            # Parse response
            result = CodeExecutionResult(
                output=response.get('output', ''),
                error=response.get('error'),
                exit_code=response.get('exitCode'),
                files_created=response.get('filesCreated', []),
                execution_time=execution_time
            )
            
            logger.debug(f"Code execution completed in {execution_time:.2f}s for session {session_id}")
            return result
            
        except self.bedrock_agentcore_client.exceptions.TimeoutException:
            logger.warning(f"Code execution timed out for session {session_id}")
            return CodeExecutionResult(
                output="",
                error=f"Execution timed out after {timeout} seconds",
                exit_code=124
            )
        except ClientError as e:
            logger.error(f"Failed to execute code in session {session_id}: {e}")
            return CodeExecutionResult(
                output="",
                error=f"AWS AgentCore error: {str(e)}",
                exit_code=1
            )
        except Exception as e:
            logger.error(f"Unexpected error during code execution: {e}")
            return CodeExecutionResult(
                output="",
                error=f"Unexpected error: {str(e)}",
                exit_code=1
            )
    
    async def execute_shell_command(
        self,
        session_id: str,
        command: str,
        working_dir: str = "/workspace",
        timeout: int = 30
    ) -> CodeExecutionResult:
        """
        Execute a shell command in the Code Interpreter session.
        
        Args:
            session_id: ID of the active session
            command: Shell command to execute
            working_dir: Working directory for command execution
            timeout: Execution timeout in seconds
            
        Returns:
            CodeExecutionResult with command output
        """
        # Convert shell command to Python code for execution
        python_code = f'''
import subprocess
import os
import sys

# Change to working directory
try:
    os.chdir("{working_dir}")
except OSError as e:
    print(f"Error changing directory: {{e}}")
    sys.exit(1)

# Execute the shell command
try:
    result = subprocess.run(
        ["{command}"],
        shell=True,
        capture_output=True,
        text=True,
        timeout={timeout}
    )
    
    print("STDOUT:")
    print(result.stdout)
    
    if result.stderr:
        print("STDERR:")
        print(result.stderr)
    
    sys.exit(result.returncode)
    
except subprocess.TimeoutExpired:
    print(f"Command timed out after {timeout} seconds")
    sys.exit(124)
except Exception as e:
    print(f"Error executing command: {{e}}")
    sys.exit(1)
'''
        
        return await self.execute_code(
            session_id=session_id,
            code=python_code,
            language="python",
            timeout=timeout
        )
    
    async def upload_file(
        self,
        session_id: str,
        file_path: str,
        content: bytes,
        destination_path: Optional[str] = None
    ) -> str:
        """
        Upload a file to the Code Interpreter session workspace.
        
        Args:
            session_id: ID of the active session
            file_path: Original file path
            content: File content as bytes
            destination_path: Destination path in workspace (optional)
            
        Returns:
            Path where file was uploaded
        """
        if session_id not in self._active_sessions:
            raise ValueError(f"Session {session_id} not found")
            
        try:
            # Determine destination path
            if not destination_path:
                import os
                destination_path = f"/workspace/{os.path.basename(file_path)}"
            
            # For now, use Python code to write the file
            # In a full implementation, we'd use AgentCore's file upload APIs
            import base64
            
            python_code = f'''
import base64
import os

# File content (base64 encoded)
content = base64.b64decode("{base64.b64encode(content).decode()}")

# Write file to workspace
try:
    os.makedirs(os.path.dirname("{destination_path}"), exist_ok=True)
    with open("{destination_path}", "wb") as f:
        f.write(content)
    print(f"File uploaded successfully to: {destination_path}")
except Exception as e:
    print(f"Error uploading file: {{e}}")
    exit(1)
'''
            
            result = await self.execute_code(
                session_id=session_id,
                code=python_code,
                language="python",
                timeout=30
            )
            
            if result.error:
                raise RuntimeError(f"Failed to upload file: {result.error}")
                
            logger.info(f"File uploaded to {destination_path} in session {session_id}")
            return destination_path
            
        except Exception as e:
            logger.error(f"Failed to upload file to session {session_id}: {e}")
            raise
    
    async def download_file(
        self,
        session_id: str,
        file_path: str
    ) -> bytes:
        """
        Download a file from the Code Interpreter session workspace.
        
        Args:
            session_id: ID of the active session
            file_path: Path to file in workspace
            
        Returns:
            File content as bytes
        """
        if session_id not in self._active_sessions:
            raise ValueError(f"Session {session_id} not found")
            
        try:
            # Use Python code to read and encode the file
            python_code = f'''
import base64
import os

file_path = "{file_path}"

try:
    if not os.path.exists(file_path):
        print(f"ERROR: File not found: {{file_path}}")
        exit(1)
        
    with open(file_path, "rb") as f:
        content = f.read()
    
    # Return base64 encoded content
    encoded = base64.b64encode(content).decode()
    print(f"FILE_CONTENT_BASE64:{{encoded}}")
    
except Exception as e:
    print(f"ERROR: {{e}}")
    exit(1)
'''
            
            result = await self.execute_code(
                session_id=session_id,
                code=python_code,
                language="python",
                timeout=30
            )
            
            if result.error:
                raise RuntimeError(f"Failed to download file: {result.error}")
            
            # Extract base64 content from output
            output_lines = result.output.strip().split('\n')
            file_content_b64 = None
            
            for line in output_lines:
                if line.startswith('FILE_CONTENT_BASE64:'):
                    file_content_b64 = line[len('FILE_CONTENT_BASE64:'):].strip()
                    break
            
            if not file_content_b64:
                raise RuntimeError("File content not found in execution output")
            
            file_content = base64.b64decode(file_content_b64)
            logger.info(f"Downloaded {len(file_content)} bytes from {file_path} in session {session_id}")
            
            return file_content
            
        except Exception as e:
            logger.error(f"Failed to download file from session {session_id}: {e}")
            raise
    
    async def list_files(
        self,
        session_id: str,
        directory: str = "/workspace",
        recursive: bool = False
    ) -> List[str]:
        """
        List files in a directory of the Code Interpreter session workspace.
        
        Args:
            session_id: ID of the active session
            directory: Directory path to list
            recursive: Whether to list files recursively
            
        Returns:
            List of file paths
        """
        if session_id not in self._active_sessions:
            raise ValueError(f"Session {session_id} not found")
            
        try:
            import json
            
            python_code = f'''
import os
import json

def list_files_recursive(directory):
    file_list = []
    try:
        for root, dirs, files in os.walk(directory):
            for file in files:
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, directory)
                file_list.append(relative_path)
    except Exception as e:
        print(f"ERROR: {{e}}")
        return []
    return file_list

def list_files_flat(directory):
    file_list = []
    try:
        for item in os.listdir(directory):
            item_path = os.path.join(directory, item)
            if os.path.isfile(item_path):
                file_list.append(item)
    except Exception as e:
        print(f"ERROR: {{e}}")
        return []
    return file_list

directory = "{directory}"
recursive = {str(recursive).lower()}

try:
    if recursive:
        files = list_files_recursive(directory)
    else:
        files = list_files_flat(directory)
    
    print(json.dumps(files))
except Exception as e:
    print(f"ERROR: {{e}}")
'''
            
            result = await self.execute_code(
                session_id=session_id,
                code=python_code,
                language="python",
                timeout=10
            )
            
            if result.error:
                raise RuntimeError(f"Failed to list files: {result.error}")
            
            # Parse JSON output
            try:
                files = json.loads(result.output.strip())
                logger.debug(f"Listed {len(files)} files in {directory} for session {session_id}")
                return files
            except json.JSONDecodeError:
                logger.error(f"Failed to parse file list output: {result.output}")
                return []
            
        except Exception as e:
            logger.error(f"Failed to list files in session {session_id}: {e}")
            return []
    
    async def terminate_session(self, session_id: str) -> bool:
        """
        Terminate a Code Interpreter session.
        
        Args:
            session_id: ID of the session to terminate
            
        Returns:
            True if session was terminated successfully
        """
        if session_id not in self._active_sessions:
            logger.warning(f"Session {session_id} not found in active sessions")
            return False
            
        try:
            # Terminate the session
            self.bedrock_agentcore_client.terminate_code_interpreter_session(
                codeInterpreterId=self.code_interpreter_tool_id,
                sessionId=session_id
            )
            
            # Remove from active sessions
            del self._active_sessions[session_id]
            
            logger.info(f"Terminated Code Interpreter session {session_id}")
            return True
            
        except ClientError as e:
            logger.error(f"Failed to terminate session {session_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error terminating session {session_id}: {e}")
            return False
    
    async def get_session_status(self, session_id: str) -> Dict[str, Any]:
        """
        Get status of a Code Interpreter session.
        
        Args:
            session_id: ID of the session
            
        Returns:
            Session status information
        """
        try:
            response = self.bedrock_agentcore_client.get_code_interpreter_session(
                codeInterpreterId=self.code_interpreter_tool_id,
                sessionId=session_id
            )
            
            status = {
                'session_id': session_id,
                'status': response.get('status', 'unknown'),
                'created_at': response.get('createdAt'),
                'expires_at': response.get('expiresAt'),
                'last_activity_at': response.get('lastActivityAt')
            }
            
            return status
            
        except ClientError as e:
            logger.error(f"Failed to get session status for {session_id}: {e}")
            return {'session_id': session_id, 'status': 'error', 'error': str(e)}
        except Exception as e:
            logger.error(f"Unexpected error getting session status: {e}")
            return {'session_id': session_id, 'status': 'error', 'error': str(e)}
    
    async def cleanup_expired_sessions(self):
        """Clean up expired sessions."""
        current_time = asyncio.get_event_loop().time()
        expired_sessions = []
        
        for session_id, session_info in self._active_sessions.items():
            timeout_seconds = session_info['timeout_minutes'] * 60
            age_seconds = current_time - session_info['created_at']
            
            if age_seconds > timeout_seconds:
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            logger.info(f"Cleaning up expired session {session_id}")
            await self.terminate_session(session_id)
