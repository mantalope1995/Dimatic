"""
AgentCore Files Tool

Refactored files tool that uses AWS AgentCore Code Interpreter instead of Daytona.io.
Provides file operations (read, write, list, upload, download) in the secure workspace.
"""

import os
import mimetypes
import base64
from typing import Optional, Dict, Any, List
from core.agentpress.tool import ToolResult, openapi_schema, tool_metadata
from core.agentcore.sandbox_tools_base import AgentCoreSandboxToolsBase
from core.agentpress.thread_manager import ThreadManager
from core.utils.logger import logger
from core.utils.files_utils import clean_path


@tool_metadata(
    display_name="Files & Documents (AgentCore)",
    description="Read, write, and manage files in your secure AWS AgentCore workspace",
    icon="FileText",
    color="bg-green-100 dark:bg-green-800/50",
    is_core=True,
    weight=18,
    visible=True
)
class AgentCoreFilesTool(AgentCoreSandboxToolsBase):
    """
    File operations tool using AWS AgentCore Code Interpreter.
    
    Provides secure file management capabilities in isolated AWS environments.
    Supports reading, writing, listing, uploading, and downloading files.
    """

    def __init__(self, project_id: str, thread_manager: ThreadManager):
        super().__init__(project_id, thread_manager)

    @openapi_schema({
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file in the workspace. Supports text files, images, and binary files. For binary files, returns base64 encoded content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file relative to /workspace. Example: 'data/report.txt' or 'config.json'"
                    },
                    "encoding": {
                        "type": "string",
                        "description": "Text encoding for text files. Defaults to 'utf-8'. Ignored for binary files.",
                        "default": "utf-8"
                    },
                    "base64_decode": {
                        "type": "boolean",
                        "description": "Whether to base64 decode the content (for binary files). If False, returns raw bytes as base64 string.",
                        "default": False
                    }
                },
                "required": ["file_path"]
            }
        }
    })
    async def read_file(
        self,
        file_path: str,
        encoding: str = "utf-8",
        base64_decode: bool = False
    ) -> ToolResult:
        """Read file contents from the Code Interpreter workspace."""
        try:
            if not self.is_code_interpreter_available:
                return self.fail_response(
                    "Code Interpreter not available. Please configure AWS AgentCore Code Interpreter."
                )
            
            # Clean and validate path
            clean_file_path = self.clean_path(file_path)
            
            # Detect if file is binary
            is_binary = await self._is_binary_file(clean_file_path)
            
            if is_binary:
                # For binary files, download as base64
                file_content = await self.download_file(clean_file_path)
                
                if base64_decode:
                    # Return decoded binary content
                    try:
                        decoded_content = base64.b64decode(file_content).decode('utf-8', errors='replace')
                        return self.success_response({
                            "content": decoded_content,
                            "file_path": clean_file_path,
                            "size": len(file_content),
                            "encoding": "binary",
                            "decoded": True
                        })
                    except Exception as e:
                        return self.fail_response(f"Failed to decode binary file: {str(e)}")
                else:
                    # Return raw base64 content
                    b64_content = base64.b64encode(file_content).decode('utf-8')
                    return self.success_response({
                        "content": b64_content,
                        "file_path": clean_file_path,
                        "size": len(file_content),
                        "encoding": "binary",
                        "base64_encoded": True
                    })
            else:
                # For text files, read directly using Python
                python_code = f'''
import os
import sys

file_path = "{clean_file_path}"
encoding = "{encoding}"

try:
    if not os.path.exists(file_path):
        print(f"ERROR: File not found: {{file_path}}")
        sys.exit(1)
    
    # Check file size (limit to 10MB for safety)
    file_size = os.path.getsize(file_path)
    if file_size > 10 * 1024 * 1024:  # 10MB
        print(f"ERROR: File too large ({{file_size}} bytes). Maximum size is 10MB.")
        sys.exit(1)
    
    with open(file_path, 'r', encoding=encoding) as f:
        content = f.read()
    
    print(f"FILE_SIZE:{{file_size}}")
    print(f"FILE_ENCODING:{{encoding}}")
    print("---CONTENT_START---")
    print(content)
    print("---CONTENT_END---")
    
except Exception as e:
    print(f"ERROR: {{e}}")
    sys.exit(1)
'''
                
                result = await self.execute_code(python_code, language="python", timeout=30)
                
                if result.error:
                    return self.fail_response(f"Failed to read file: {result.error}")
                
                # Parse the output
                output_lines = result.output.split('\n')
                file_size = None
                file_encoding = None
                content_parts = []
                
                content_started = False
                for line in output_lines:
                    if line.startswith('FILE_SIZE:'):
                        file_size = int(line.split(':', 1)[1])
                    elif line.startswith('FILE_ENCODING:'):
                        file_encoding = line.split(':', 1)[1]
                    elif line == '---CONTENT_START---':
                        content_started = True
                    elif line == '---CONTENT_END---':
                        break
                    elif content_started:
                        content_parts.append(line)
                
                if file_size is None:
                    return self.fail_response("Failed to parse file information")
                
                content = '\n'.join(content_parts)
                
                return self.success_response({
                    "content": content,
                    "file_path": clean_file_path,
                    "size": file_size,
                    "encoding": file_encoding or encoding,
                    "binary": False
                })
                
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {str(e)}")
            return self.fail_response(f"Error reading file: {str(e)}")

    @openapi_schema({
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file in the workspace. Supports both text and binary content. For binary content, provide base64 encoded string.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path where to create the file relative to /workspace. Example: 'output/result.txt'"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file. Can be text or base64 encoded binary data."
                    },
                    "encoding": {
                        "type": "string",
                        "description": "Text encoding for text files. Defaults to 'utf-8'.",
                        "default": "utf-8"
                    },
                    "base64_encode": {
                        "type": "boolean",
                        "description": "Whether the content is base64 encoded binary data. If True, will decode before writing.",
                        "default": False
                    },
                    "create_directories": {
                        "type": "boolean",
                        "description": "Whether to create parent directories if they don't exist.",
                        "default": True
                    }
                },
                "required": ["file_path", "content"]
            }
        }
    })
    async def write_file(
        self,
        file_path: str,
        content: str,
        encoding: str = "utf-8",
        base64_encode: bool = False,
        create_directories: bool = True
    ) -> ToolResult:
        """Write content to a file in the Code Interpreter workspace."""
        try:
            if not self.is_code_interpreter_available:
                return self.fail_response(
                    "Code Interpreter not available. Please configure AWS AgentCore Code Interpreter."
                )
            
            # Clean and validate path
            clean_file_path = self.clean_path(file_path)
            
            # Prepare content
            if base64_encode:
                try:
                    file_content = base64.b64decode(content)
                except Exception as e:
                    return self.fail_response(f"Failed to decode base64 content: {str(e)}")
                
                # Upload binary content
                await self.upload_file(file_path, file_content, clean_file_path)
            else:
                # Write text content using Python
                python_code = f'''
import os
import sys

file_path = "{clean_file_path}"
content = """{content.replace('"""', '""""')}"""
encoding = "{encoding}"
create_dirs = {str(create_directories).lower()}

try:
    # Create parent directories if requested
    if create_dirs:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    # Write the file
    with open(file_path, 'w', encoding=encoding) as f:
        f.write(content)
    
    # Get file info
    file_size = os.path.getsize(file_path)
    print(f"SUCCESS: File written successfully")
    print(f"FILE_PATH:{{file_path}}")
    print(f"FILE_SIZE:{{file_size}}")
    print(f"ENCODING:{{encoding}}")
    
except Exception as e:
    print(f"ERROR: {{e}}")
    sys.exit(1)
'''
                
                result = await self.execute_code(python_code, language="python", timeout=30)
                
                if result.error:
                    return self.fail_response(f"Failed to write file: {result.error}")
                
                # Check for success
                if "SUCCESS:" not in result.output:
                    return self.fail_response("Failed to write file - unknown error")
            
            return self.success_response({
                "message": f"File written successfully to {clean_file_path}",
                "file_path": clean_file_path,
                "encoding": encoding,
                "binary": base64_encode
            })
                
        except Exception as e:
            logger.error(f"Error writing file {file_path}: {str(e)}")
            return self.fail_response(f"Error writing file: {str(e)}")

    @openapi_schema({
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories in the workspace. Supports recursive listing and filtering.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Directory path to list relative to /workspace. Use '.' for current directory.",
                        "default": "."
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "Whether to list files recursively in subdirectories.",
                        "default": False
                    },
                    "show_hidden": {
                        "type": "boolean",
                        "description": "Whether to show hidden files (starting with .).",
                        "default": False
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Optional glob pattern to filter files (e.g., '*.py', 'data/*.json').",
                        "default": None
                    }
                },
                "required": []
            }
        }
    })
    async def list_files(
        self,
        directory: str = ".",
        recursive: bool = False,
        show_hidden: bool = False,
        pattern: Optional[str] = None
    ) -> ToolResult:
        """List files in the Code Interpreter workspace."""
        try:
            if not self.is_code_interpreter_available:
                return self.fail_response(
                    "Code Interpreter not available. Please configure AWS AgentCore Code Interpreter."
                )
            
            # Clean and validate directory path
            clean_dir = self.clean_path(directory)
            
            # Build Python code for listing files
            import json
            
            python_code = f'''
import os
import json
import glob
import fnmatch

def list_files_directory(directory, recursive=False, show_hidden=False, pattern=None):
    file_list = []
    try:
        if recursive:
            for root, dirs, files in os.walk(directory):
                # Skip hidden directories if not showing hidden
                if not show_hidden:
                    dirs[:] = [d for d in dirs if not d.startswith('.')]
                
                for file in files:
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, directory)
                    
                    # Skip hidden files if not showing hidden
                    if not show_hidden and file.startswith('.'):
                        continue
                    
                    # Apply pattern filter if provided
                    if pattern and not fnmatch.fnmatch(relative_path, pattern):
                        continue
                    
                    # Get file info
                    try:
                        stat = os.stat(file_path)
                        is_dir = os.path.isdir(file_path)
                        file_info = {{
                            "name": file,
                            "path": relative_path,
                            "full_path": file_path,
                            "is_directory": is_dir,
                            "size": stat.st_size if not is_dir else 0,
                            "modified": stat.st_mtime,
                            "mime_type": "application/octet-stream" if is_dir else None
                        }}
                        file_list.append(file_info)
                    except OSError:
                        # Skip files we can't stat
                        continue
        else:
            # Non-recursive listing
            try:
                items = os.listdir(directory)
                for item in items:
                    # Skip hidden items if not showing hidden
                    if not show_hidden and item.startswith('.'):
                        continue
                    
                    # Apply pattern filter if provided
                    if pattern and not fnmatch.fnmatch(item, pattern):
                        continue
                    
                    item_path = os.path.join(directory, item)
                    relative_path = os.path.relpath(item_path, directory)
                    
                    # Get file info
                    try:
                        stat = os.stat(item_path)
                        is_dir = os.path.isdir(item_path)
                        file_info = {{
                            "name": item,
                            "path": relative_path,
                            "full_path": item_path,
                            "is_directory": is_dir,
                            "size": stat.st_size if not is_dir else 0,
                            "modified": stat.st_mtime,
                            "mime_type": "application/octet-stream" if is_dir else None
                        }}
                        file_list.append(file_info)
                    except OSError:
                        # Skip items we can't stat
                        continue
            except OSError as e:
                return {{"error": str(e)}}
        
        return file_list

directory = "{clean_dir}"
recursive = {str(recursive).lower()}
show_hidden = {str(show_hidden).lower()}
pattern = "{pattern or ''}"

try:
    files = list_files_directory(directory, recursive, show_hidden, pattern if pattern else None)
    print(json.dumps({{"success": True, "files": files}}))
except Exception as e:
    print(json.dumps({{"success": False, "error": str(e)}}))
'''
            
            result = await self.execute_code(python_code, language="python", timeout=15)
            
            if result.get('error'):
                return self.fail_response(f"Failed to list files: {result.get('error')}")
            
            # Parse JSON response
            try:
                output = result.get('output', '').strip()
                response_data = json.loads(output)
                
                if not response_data.get('success', False):
                    error_msg = response_data.get('error', 'Unknown error')
                    return self.fail_response(f"Failed to list files: {error_msg}")
                
                files = response_data.get('files', [])
                
                # Sort files: directories first, then files, both alphabetically
                files.sort(key=lambda x: (not x['is_directory'], x['name'].lower()))
                
                return self.success_response({
                    "directory": clean_dir,
                    "files": files,
                    "count": len(files),
                    "recursive": recursive,
                    "pattern": pattern
                })
                
            except json.JSONDecodeError:
                return self.fail_response("Failed to parse file listing response")
            
        except Exception as e:
            logger.error(f"Error listing files in {directory}: {str(e)}")
            return self.fail_response(f"Error listing files: {str(e)}")

    @openapi_schema({
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file or directory from the workspace. Use with caution - this operation cannot be undone.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file or directory to delete relative to /workspace."
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "Whether to delete directories recursively (required for non-empty directories).",
                        "default": False
                    }
                },
                "required": ["file_path"]
            }
        }
    })
    async def delete_file(
        self,
        file_path: str,
        recursive: bool = False
    ) -> ToolResult:
        """Delete a file or directory from the workspace."""
        try:
            if not self.is_code_interpreter_available:
                return self.fail_response(
                    "Code Interpreter not available. Please configure AWS AgentCore Code Interpreter."
                )
            
            # Clean and validate path
            clean_file_path = self.clean_path(file_path)
            
            python_code = f'''
import os
import sys
import shutil

file_path = "{clean_file_path}"
recursive = {str(recursive).lower()}

try:
    if not os.path.exists(file_path):
        print(f"ERROR: File or directory not found: {{file_path}}")
        sys.exit(1)
    
    if os.path.isfile(file_path):
        os.remove(file_path)
        print(f"SUCCESS: File deleted: {{file_path}}")
    elif os.path.isdir(file_path):
        if recursive:
            shutil.rmtree(file_path)
            print(f"SUCCESS: Directory deleted recursively: {{file_path}}")
        else:
            try:
                os.rmdir(file_path)
                print(f"SUCCESS: Empty directory deleted: {{file_path}}")
            except OSError as e:
                if "Directory not empty" in str(e):
                    print(f"ERROR: Directory not empty. Use recursive=True to delete non-empty directories.")
                else:
                    print(f"ERROR: {{e}}")
                sys.exit(1)
    else:
        print(f"ERROR: Path is neither file nor directory: {{file_path}}")
        sys.exit(1)
        
except Exception as e:
    print(f"ERROR: {{e}}")
    sys.exit(1)
'''
            
            result = await self.execute_code(python_code, language="python", timeout=15)
            
            if result.error:
                return self.fail_response(f"Failed to delete file: {result.error}")
            
            # Check for success
            if "SUCCESS:" in result.output:
                return self.success_response({
                    "message": f"Successfully deleted {clean_file_path}",
                    "file_path": clean_file_path,
                    "recursive": recursive
                })
            else:
                # Extract error message
                lines = result.output.split('\n')
                error_line = next((line for line in lines if line.startswith('ERROR:')), None)
                if error_line:
                    error_msg = error_line[6:]  # Remove 'ERROR:' prefix
                    return self.fail_response(error_msg)
                else:
                    return self.fail_response("Failed to delete file - unknown error")
                
        except Exception as e:
            logger.error(f"Error deleting file {file_path}: {str(e)}")
            return self.fail_response(f"Error deleting file: {str(e)}")

    async def _is_binary_file(self, file_path: str) -> bool:
        """Check if a file is binary by examining its content and extension."""
        try:
            # Check file extension first
            _, ext = os.path.splitext(file_path.lower())
            binary_extensions = {
                '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico', '.svg',
                '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
                '.zip', '.tar', '.gz', '.rar', '.7z',
                '.mp3', '.mp4', '.avi', '.mov', '.wav',
                '.exe', '.dll', '.so', '.dylib',
                '.bin', '.dat', '.db', '.sqlite'
            }
            
            if ext in binary_extensions:
                return True
            
            # Check MIME type
            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type and not mime_type.startswith('text/'):
                return True
            
            # For safety, assume it might be binary
            return False
            
        except Exception:
            return False

    @property
    def tool_info(self) -> Dict[str, Any]:
        """Get tool information including AgentCore status."""
        info = super().tool_info or {}
        
        info.update({
            'backend': 'AWS AgentCore',
            'code_interpreter_available': self.is_code_interpreter_available,
            'browser_available': self.is_browser_available,
            'workspace_path': self.workspace_path
        })
        
        return info
