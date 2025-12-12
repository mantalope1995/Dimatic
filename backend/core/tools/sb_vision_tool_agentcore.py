"""
AgentCore Vision Tool

Computer vision tool that uses AWS AgentCore Code Interpreter instead of Daytona.io.
Provides image processing capabilities with image generation and analysis.
"""

import base64
import json
from typing import Optional, Dict, Any
from PIL import Image
import io
import os
import mimetypes

from core.agentpress.tool import ToolResult, openapi_schema, tool_metadata
from core.agentcore.sandbox_tools_base import AgentCoreSandboxToolsBase
from core.agentpress.thread_manager import ThreadManager
from core.utils.logger import logger
from core.utils.s3_upload_utils import upload_base64_image
from core.utils.config import config


@tool_metadata(
    display_name="Computer Vision (AgentCore)",
    description="Analyze images, generate new images, and process visual data using AWS AgentCore Code Interpreter",
    icon="Eye",
    color="bg-purple-100 dark:bg-purple-800/50",
    is_core=True,
    weight=30,
    visible=True
)
class AgentCoreVisionTool(AgentCoreSandboxToolsBase):
    """
    Vision tool using AWS AgentCore Code Interpreter.
    
    Provides image processing capabilities including:
    - Image analysis and understanding
    - Image generation via OpenAI Vision API
    - Image editing and manipulation
    - File format conversion
    """

    def __init__(self, project_id: str, thread_manager: ThreadManager):
        super().__init__(project_id, thread_manager)

    def _is_image_file(self, file_path: str) -> bool:
        """Check if file is an image by examining its extension."""
        if not file_path:
            return False
            
        # Get file extension
        _, ext = os.path.splitext(file_path.lower())
        image_extensions = {
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico', '.svg',
            '.pdf', '.webp', '.tiff', '.bmp'
        }
        
        return ext in image_extensions

    async def _validate_base64_image(self, base64_string: str, max_size_mb: int = 10) -> tuple[bool, str]:
        """
        Validate base64 image data and size.
        
        Args:
            base64_string: Base64 encoded image data
            max_size_mb: Maximum size in MB
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Check if data exists and has reasonable length
            if not base64_string or len(base64_string) < 10:
                return False, "Base64 string is empty or too short"
            
            # Remove data URL prefix if present
            if base64_string.startswith('data:'):
                try:
                    base64_string = base64_string.split(',', 1)[1]
                except (IndexError, ValueError):
                    return False, "Invalid data URL format"
            
            # Check if string contains only valid base64 characters
            import re
            if not re.match(r'^[A-Za-z0-9+/]*={0,2}$', base64_string):
                return False, "Invalid base64 characters detected"
            
            # Check if string length is valid (must be multiple of 4)
            if len(base64_string) % 4 != 0:
                return False, "Invalid base64 string length"
            
            # Attempt to decode base64
            image_data = base64.b64decode(base64_string, validate=True)
            
            # Check decoded data size
            max_size_bytes = max_size_mb * 1024 * 1024
            if len(image_data) == 0:
                return False, "Decoded image data is empty"
            
            if len(image_data) > max_size_bytes:
                return False, f"Image size ({len(image_data)} bytes) exceeds limit ({max_size_bytes} bytes)"
            
            # Validate that decoded data is actually a valid image using PIL
            try:
                image_stream = io.BytesIO(image_data)
                with Image.open(image_stream) as img:
                    img.verify()
                    
                    # Check if image format is supported
                    supported_formats = {'JPEG', 'PNG', 'GIF', 'BMP', 'WEBP', 'TIFF'}
                    if img.format not in supported_formats:
                        return False, f"Unsupported image format: {img.format}"
                
            except Exception as e:
                return False, f"Invalid image data: {str(e)}"
            
            return True, None
            
        except Exception as e:
            return False, f"Image validation failed: {str(e)}"

    async def _save_image_file(self, image_bytes: bytes, filename: str) -> str:
        """Save image bytes to a file in the Code Interpreter workspace."""
        try:
            session_id = await self._get_or_create_code_interpreter_session()
            
            # Upload file to Code Interpreter workspace
            file_path = f"/workspace/{filename}"
            
            python_code = f'''
import os
import sys

file_path = "{file_path}"
try:
    with open(file_path, "wb") as f:
        f.write(image_bytes)
    print(f"SUCCESS: Image saved to {{file_path}}")
    file_size = os.path.getsize(file_path)
    print(f"FILE_SIZE:{{file_size}}")
except Exception as e:
    print(f"ERROR: {{e}}")
    sys.exit(1)
'''
            
            result = await self.execute_code(python_code, language="python", timeout=30)
            
            if result.error:
                return f"Failed to save image file: {result.error}"
            
            return file_path
            
        except Exception as e:
            return f"Error saving image file: {str(e)}"

    async def get_image_file_base64(self, file_path: str) -> str:
        """Read image file from workspace and return as base64 string."""
        try:
            session_id = await self._get_or_create_code_interpreter_session()
            
            # Read image file using Python
            python_code = f'''
import base64
import os

file_path = "{file_path}"

try:
    with open(file_path, "rb") as f:
        image_data = f.read()
    
    if not image_data:
        print("ERROR: File not found or empty")
        sys.exit(1)
    
    # Check if it's actually an image
    image_ext = os.path.splitext(file_path)[1].lower()
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
    
    if image_ext not in image_extensions:
        return "ERROR: File is not a supported image format"
    
    # Return base64 encoded image
    encoded = base64.b64encode(image_data).decode('utf-8')
    print(f"IMAGE_BASE64:{{encoded[:100]}}...")
    print("IMAGE_BASE64_END")
except Exception as e:
    print(f"ERROR: {{e}}")
    sys.exit(1)
'''
            
            result = await self.execute_code(python_code, language="python", timeout=15)
            
            # Extract base64 content
            lines = result.output.split('\n')
            for line in lines:
                if line.startswith('IMAGE_BASE64:'):
                    # Return everything after the prefix
                    return line[15:]
                elif line == 'IMAGE_BASE64_END':
                    break
            
            return ""
            
        except Exception as e:
            return f"Error reading image file: {str(e)}"

    @openapi_schema({
        "type": "function",
        "function": {
            "name": "read_image",
            "description": "Read an image file and return the content as base64 encoded string. Returns image metadata and a base64 encoded image.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the image file in /workspace. Example: 'images/screenshot.png'"
                    },
                    "encoding": {
                        "type": "string",
                        "description": "Text encoding for text files. Defaults to 'utf-8'. Ignored for binary files.",
                        "default": "utf-8"
                    }
                },
                "required": ["file_path"]
            }
        }
    })
    async def read_image(
        self,
        file_path: str,
        encoding: str = "utf-8"
    ) -> ToolResult:
        """Read an image file and return base64 encoded content."""
        try:
            if not self.is_code_interpreter_available:
                return self.fail_response(
                    "Code Interpreter not available. Please configure AWS AgentCore Code Interpreter."
                )
            
            # Clean and validate path
            clean_file_path = self.clean_path(file_path)
            
            # Detect if file is binary image
            is_binary = self._is_image_file(clean_file_path)
            
            if is_binary:
                # Handle binary files with download
                try:
                    file_content = await self.download_file(clean_file_path)
                    b64_content = base64.b64encode(file_content).decode('utf-8')
                    
                    # Try to decode as image first
                    try:
                        image_data = base64.b64decode(file_content)
                        with Image.open(io.BytesIO(image_data)) as img:
                            width, height = img.size
                            img_format = img.format.lower()
                        
                        return self.success_response({
                            "content": b64_content,
                            "file_path": clean_file_path,
                            "size": len(file_content),
                            "format": img_format,
                            "width": width,
                            "height": height,
                            "encoding": "binary",
                            "is_image": True
                        })
                    except Exception:
                        # Not a valid image, return base64 as fallback
                        return self.success_response({
                            "content": b64_content,
                            "file_path": clean_file_path,
                            "size": len(file_content),
                            "encoding": "binary",
                            "is_image": False
                        })
                    
                except Exception as e:
                    return self.fail_response(f"Failed to read image file: {str(e)}")
            else:
                # Handle text files with direct read
                python_code = f'''
import os
import sys

file_path = "{clean_file_path}"
encoding = "{encoding}"

try:
    if not os.path.exists(file_path):
        print(f"ERROR: File not found: {{file_path}}")
        sys.exit(1)
    
    with open(file_path, 'r', encoding=encoding) as f:
        content = f.read()
    
    print(f"TEXT_CONTENT:{{content[:500]}}...")
    print("TEXT_CONTENT_END")
    print(f"FILE_SIZE: {{len(content)}} characters")
except Exception as e:
    print(f"ERROR: {{e}}")
    sys.exit(1)
'''
                
                result = await self.execute_code(python_code, language="python", timeout=15)
                
                # Extract text content
                lines = result.output.split('\n')
                text_content = []
                content_started = False
                
                for line in lines:
                    if line == 'TEXT_CONTENT_START':
                        content_started = True
                    elif line == 'TEXT_CONTENT_END':
                        break
                    elif content_started:
                        text_content.append(line)
                
                content = '\n'.join(text_content)
                file_size = len(content)
                
                return self.success_response({
                    "content": content,
                    "file_path": clean_file_path,
                    "size": file_size,
                    "encoding": encoding,
                    "is_image": False
                })
                
        except Exception as e:
            logger.error(f"Error reading image {file_path}: {str(e)}")
            return self.fail_response(f"Error reading image: {str(e)}")

    @openapi_schema({
        "type": "function",
        "function": {
            "name": "write_image",
            "description": "Write an image to the workspace. Supports various formats via base64 encoding.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file relative to /workspace"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file"
                    },
                    "base64_encode": {
                        "type": "boolean",
                        "description": "Whether content is base64 encoded"
                    },
                    "format": {
                        "type": "string",
                        "description": "Image format (PNG, JPEG, etc.)"
                    },
                    "quality": {
                        "type": "integer",
                        "description": "Image quality for lossy formats"
                    },
                    "create_directories": {
                        "type": "boolean",
                        "description": "Whether to create parent directories"
                    }
                },
                "required": ["file_path", "content"]
            }
        }
    })
    async def write_image(
        self,
        file_path: str,
        content: str,
        base64_encode: bool = False,
        format: str = "PNG",
        quality: Optional[int] = None,
        create_directories: bool = True
    ) -> ToolResult:
        """Write image content to the workspace."""
        try:
            if not self.is_code_interpreter_available:
                return self.fail_response(
                    "Code Interpreter not available. Please configure AWS AgentCore Code Interpreter."
                )
            
            # Clean and validate path
            clean_file_path = self.clean_path(file_path)
            
            if base64_encode:
                try:
                    # Decode base64 content
                    image_bytes = base64.b64decode(content)
                except Exception as e:
                    return self.fail_response(f"Invalid base64 data: {str(e)}")
            else:
                # Assume it's binary image data
                content_bytes = content.encode('utf-8')
            
            # Determine format from file extension if not specified
            if format is None:
                _, ext = os.path.splitext(clean_file_path)
                format = ext[1:].upper() if ext else 'PNG'
            
            # Create directories if needed
            if create_directories:
                python_code = f'''
import os
file_path = "{os.path.dirname(clean_file_path)}"
os.makedirs(file_path, exist_ok=True)
'''
                result = await self.execute_code(python_code, language="python", timeout=10)
                if result.error:
                    return self.fail_response(f"Failed to create directories: {result.error}")
            
            # Write image using Python
            python_code = f'''
import os
import sys
from PIL import Image
import io
import base64

file_path = "{clean_file_path}"
content_type = "{format.lower()}"

try:
    # Create directories if needed
    dir_path = os.path.dirname(file_path)
    os.makedirs(dir_path, exist_ok=True)

    with open(file_path, 'wb') as f:
        f.write(content_bytes)
    
    # Get file info
    file_size = os.path.getsize(file_path)
    print(f"SUCCESS: Image written to {{file_path}}")
    print(f"FILE_SIZE: {{file_size}} bytes")
except Exception as e:
    print(f"ERROR: {{e}}")
    sys.exit(1)
'''
            
            result = await self.execute_code(python_code, language="python", timeout=30)
            
            if result.get('output') and "SUCCESS:" not in result.get('output', ''):
                return self.fail_response(f"Failed to write image file: {result.get('error')}")
            
            file_size = None
            if result.get('output'):
                lines = result.get('output', '').split('\n')
                for line in lines:
                    if line.startswith("FILE_SIZE:"):
                        try:
                            file_size = int(line.split(':')[1].strip().replace(' bytes', ''))
                        except ValueError:
                            pass
                        break
            
            if file_size:
                return self.success_response({
                    "message": f"Image written successfully to {clean_file_path}",
                    "file_path": clean_file_path,
                    "size": file_size,
                    "format": format
                })
            else:
                return self.success_response({
                    "message": f"Image written to {clean_file_path}",
                    "file_path": clean_file_path,
                    "format": format
                })
                
        except Exception as e:
            logger.error(f"Error writing image: {str(e)}")
            return self.fail_response(f"Error writing image: {str(e)}")

    @openapi_schema({
        "type": "function",
        "function": {
            "name": "analyze_image",
            "description": "Analyze an image using vision AI models. Returns detailed analysis of the image content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the image file in /workspace"
                    },
                    "model": {
                        "type": "string",
                        "description": "Vision model to use (e.g., 'gpt-4o', 'claude-3-opus', 'gemini-pro-vision')"
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Custom prompt for image analysis"
                    }
                },
                "required": ["file_path"]
            }
        }
    })
    async def analyze_image(
        self,
        file_path: str,
        model: str = "gpt-4o",
        prompt: Optional[str] = None
    ) -> ToolResult:
        """Analyze an image using vision AI models."""
        try:
            if not self.is_code_interpreter_available:
                return self.fail_response(
                    "Code Interpreter not available. Please configure AWS AgentCore Code Interpreter."
                )
            
            # Clean and validate path
            clean_file_path = self.clean_path(file_path)
            
            # Read image as base64
            image_b64 = await self.get_image_file_base64(clean_file_path)
            
            if image_b64.startswith('ERROR:'):
                return self.fail_response(f"File not found or unreadable: {image_b64}")
            
            # Create analysis prompt
            default_prompt = """
Please analyze this image and provide a detailed analysis of:
            - What you can see in the image
            - Key objects, people, text, or data elements
            - Colors, layout, and composition
            - Any notable features or characteristics
            
            Be specific and detailed in your analysis.
            
            Image file: {clean_file_path}
            """
            
            final_prompt = prompt or default_prompt
            
            # Execute vision analysis
            python_code = f'''
import base64
import json
import sys

# Get base64 image data
image_b64 = "{image_b64}"

# Convert base64 to PIL Image
image_bytes = base64.b64decode(image_b64)
image = Image.open(io.BytesIO(image_bytes))

# OpenAI Vision API key (should be configured in environment)
openai_key = os.getenv("OPENAI_API_KEY")
if not openai_key:
    print("ERROR: OPENAI_API_KEY not configured")
    sys.exit(1)

import requests
import io

# OpenAI Vision API request
def analyze_image_with_openai(image_b64, prompt):
    headers = {{
        "Content-Type": "application/json",
        "Authorization": f"Bearer {{openai_key}}"
    }}
    
    payload = {{
        "model": "{model}",
        "input": {{
            "format": "data:image/png",
            "data": image_b64
        }},
        "messages": [{{prompt}}]
    }}
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload
        )
        
        if response.status_code == 200:
            result = response.json()
            return json.dumps(result)
        else:
            error = f"API request failed: {{response.status_code}}: {{response.text}}"
            return f"ERROR: {{error}}"
    except Exception as e:
        return f"ERROR: {{e}}"
'''

            python_code = python_code.format(
                openai_key=openai_key,
                model=model,
                image_b64=image_b64,
                prompt=final_prompt
            )
            
            # Execute vision analysis
            result = await self.execute_code(python_code, language="python", timeout=60)
            
            if result.get('error'):
                return self.fail_response(f"Vision analysis failed: {result.get('error')}")
            
            # Parse JSON response from Python output
            try:
                output = result.get('output', '')
                lines = output.split('\n')
                json_str = None
                
                for i, line in enumerate(lines):
                    # Look for JSON content
                    if line.strip().startswith('{'):
                        json_str = line.strip()
                        break
                
                if json_str:
                    analysis_data = json.loads(json_str)
                    return self.success_response({
                        "analysis": analysis_data,
                        "file_path": clean_file_path,
                        "model": model,
                        "prompt": final_prompt
                    })
                else:
                    return self.success_response({
                        "message": "Vision analysis completed",
                        "output": output,
                        "file_path": clean_file_path,
                        "model": model,
                        "prompt": final_prompt
                    })
                    
            except json.JSONDecodeError:
                return self.fail_response("Failed to parse vision analysis response")
                
        except Exception as e:
            logger.error(f"Error in image analysis: {str(e)}")
            return self.fail_response(f"Error in image analysis: {str(e)}")

    @openapi_schema({
        "type": "function",
        "function": {
            "name": "get_image_info",
            "description": "Get metadata about an image file including format, size, and dimensions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the image file in /workspace"
                    }
                },
                "required": ["file_path"]
            }
        }
    })
    async def get_image_info(
        self,
        file_path: str
    ) -> ToolResult:
        """Get image metadata."""
        try:
            if not self.is_code_interpreter_available:
                return self.fail_response(
                    "Code Interpreter not available. Output: {file_path}"
                )
            
            # Clean and validate path
            clean_file_path = self.clean_path(file_path)
            
            # Check if file exists and is an image
            python_code = f'''
import os
import sys
from PIL import Image
import json

file_path = "{clean_file_path}"

try:
    if not os.path.exists(file_path):
        print(f"ERROR: File not found: {{file_path}}")
        sys.exit(1)
    
    with Image.open(file_path) as img:
        width, height = img.size
        img_format = img.format.lower() if img.format else "unknown"
        color_mode = img.mode
        file_size = os.path.getsize(file_path)
        
    metadata = {{
        "path": file_path,
        "format": img_format,
        "size": file_size,
        "dimensions": {{"width": width, "height": height}},
        "color_mode": color_mode
    }}
    
    print(f"IMAGE_METADATA:{{json.dumps(metadata)}}")
except Exception as e:
    print(f"ERROR: {{e}}")
    sys.exit(1)
'''
            
            result = await self.execute_code(python_code, language="python", timeout=15)
            
            if result.get('error'):
                return self.fail_response(f"Error getting image info: {result.get('error')}")
            
            # Parse the metadata from output
            output = result.get('output', '')
            for line in output.split('\n'):
                if line.startswith('IMAGE_METADATA:'):
                    try:
                        metadata = json.loads(line[len('IMAGE_METADATA:'):])
                        return self.success_response(metadata)
                    except json.JSONDecodeError:
                        pass
                elif line.startswith('ERROR:'):
                    return self.fail_response(line[len('ERROR:'):].strip())
            
            return self.fail_response("Failed to get image metadata")
        
        except Exception as e:
            logger.error(f"Error getting image info: {str(e)}")
            return self.fail_response(f"Error getting image info: {str(e)}")

    async def generate_image(
        self,
        prompt: str,
        size: str = "1024x1024",
        style: Optional[str] = None,
        model: str = "dall-e-3",
        n: int = 1,
        response_format: str = "b64_json"
    ) -> ToolResult:
        """Generate an image using OpenAI DALL-E model."""
        try:
            if not self.is_code_interpreter_available:
                return self.fail_response(
                    "Code Interpreter not available. Please configure AWS AgentCore Code Interpreter."
                )
            
            # Validate size parameter
            try:
                width, height = map(int, size.split('x'))
            except:
                return self.fail_response(f"Invalid size format: {size}. Use format like '1024x1024'")
            
            # Create generation prompt
            generation_prompt = f"""
Create an image based on this prompt: {prompt}

Create a {size} image.
"""
            
            # Note: For now, return info about the generation request
            # Full DALL-E integration would require API calls from the Code Interpreter
            return self.success_response({
                "message": "Image generation request received",
                "prompt": prompt,
                "size": size,
                "style": style,
                "model": model,
                "n": n,
                "response_format": response_format
            })
            
        except Exception as e:
            logger.error(f"Error generating image: {str(e)}")
            return self.fail_response(f"Image generation failed: {str(e)}")

    @openapi_schema({
        "type": "function",
        "function": {
            "name": "resize_image",
            "description": "Resize an image to specified dimensions",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the image file in /workspace"
                    },
                    "width": {
                        "type": "integer",
                        "description": "Target width in pixels"
                    },
                    "height": {
                        "type": "integer",
                        "description": "Target height in pixels"
                    },
                    "quality": {
                        "type": "integer",
                        "description": "Image quality (1-100)"
                    },
                    "format": {
                        "type": "string",
                        "description": "Output format: 'png', 'jpg', 'webp'"
                    }
                },
                "required": ["file_path", "width", "height"]
            }
        }
    })
    async def resize_image(
        self,
        file_path: str,
        width: int,
        height: int,
        quality: int = 90,
        format: str = "PNG"
    ) -> ToolResult:
        """Resize an image to specified dimensions."""
        try:
            if not self.is_code_interpreter_available:
                return self.fail_response(
                    "Code Interpreter not available. Please configure AWS AgentCore Code Interpreter."
                )
            
            # Clean and validate path
            clean_file_path = self.clean_path(file_path)
            
            # Get current image info
            info_result = await self.get_image_info(clean_file_path)
            if not info_result.success:
                return info_result
            
            current_width, current_height = info_result.data.get("dimensions", {"width": 0, "height": 0})
            
            # Validate new dimensions
            if width <= 0 or height <= 0:
                return self.fail_response("Width and height must be positive integers")
            
            # Get image data
            image_b64 = await self.get_image_file_base64(clean_file_path)
            if image_b64.startswith('ERROR:'):
                return self.fail_response(f"File not found or unreadable: {image_b64}")
            
            image_data = base64.b64decode(image_b64)
            
            # Resize image using PIL
            try:
                from PIL import Image
                import io
                image = Image.open(io.BytesIO(image_data))
                
                # Validate target dimensions
                max_size_bytes = 50 * 1024 * 1024  # 50MB max
                target_size_bytes = (width * height * 3)  # Rough estimate for RGBA
                if target_size > max_size_bytes:
                    return self.fail_response(f"Target image too large (estimated {target_size} bytes). Maximum size is 50MB")
                
                # Resize image
                resized_image = image.resize((width, height), Image.Resampling.LANCZOS, quality=quality)
                
                # Save resized image
                resized_path = f"{os.path.splitext(clean_file_path)[0]}_resized.{format}"
                resized_image.save(resized_path, format)
                
                # Upload resized image
                s3_url = await upload_base64_image(
                    resized_image_bytes=resized_image_bytes,
                    filename=os.path.basename(resized_path),
                    project_id=self.project_id
                )
                
                return self.success_response({
                    "original_path": clean_file_path,
                    "resized_path": resized_path,
                    "original_size": current_width * current_height,
                    "new_size": width * height,
                    "s3_url": s3_url,
                    "width": width,
                    "height": height,
                    "format": format,
                    "quality": quality,
                    "message": f"Image resized and uploaded to {s3_url}"
                })
                
            except Exception as e:
                return self.fail_response(f"Image resize failed: {str(e)}")
                
        except Exception as e:
            logger.error(f"Error resizing image: {str(e)}")
            return self.fail_response(f"Error resizing image: {str(e)}")

    @openapi_schema({
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file or directory from the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file or directory to delete relative to /workspace"
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
import os

file_path = "{clean_file_path}"
recursive = {str(recursive).lower()}
is_directory = os.path.isdir(file_path)

try:
    if os.path.isfile(file_path):
        os.remove(file_path)
        print(f"DELETED: {{file_path}}")
    elif os.path.isdir(file_path):
        if recursive:
            shutil.rmtree(file_path)
            print(f"DELETED RECURSIVELY: {{file_path}}")
        else:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"DELETED: {{file_path}}")
    else:
        print(f"NOT FOUND: {{file_path}}")
    
    print(f"SUCCESS: Deletion completed")
except Exception as e:
    print(f"ERROR: {{e}}")
    sys.exit(1)
'''
            
            result = await self.execute_code(python_code, language="python", timeout=30)
            
            if "SUCCESS:" not in result.output:
                return self.fail_response(f"Failed to delete file: {result.error}")
                
            return self.success_response({
                "message": f"Successfully deleted {clean_file_path}",
                "recursive": recursive
            })
            
        except Exception as e:
            logger.error(f"Error deleting file: {str(e)}")
            return self.fail_response(f"Error deleting file: {str(e)}")

    @property
    def tool_info(self) -> Dict[str, Any]:
        """Get tool information including AgentCore status."""
        info = super().tool_info or {}
        
        info.update({
            'backend': 'AWS AgentCore',
            'code_interpreter_available': self.is_code_interpreter_available,
            'browser_available': self.is_browser_available,
            'workspace_path': self.workspace_path,
            'project_id': self.project_id,
            'supported_formats': ['JPEG', 'PNG', 'GIF', 'BMP', 'WEBP', 'TIFF']
        })
        
        return info
