"""
Vision Message Handler for Qwen3-VL native multimodal support.

This module handles processing of messages containing images and formats them
for Qwen3-VL's native vision capabilities, replacing the separate vision tool
approach with direct multimodal message content.
"""

import base64
import mimetypes
import os
from typing import List, Dict, Any, Union, Tuple, Optional
from pathlib import Path
from urllib.parse import urlparse
from PIL import Image
from io import BytesIO
import requests
import tempfile
from core.utils.logger import logger
from core.utils.config import config

# Add common image MIME types if mimetypes module is limited
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/jpeg", ".jpg")
mimetypes.add_type("image/jpeg", ".jpeg")
mimetypes.add_type("image/png", ".png")
mimetypes.add_type("image/gif", ".gif")

# Supported image formats for Qwen3-VL
SUPPORTED_MIME_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']

# Maximum file size in bytes (10MB)
MAX_IMAGE_SIZE = 10 * 1024 * 1024

# Compression settings for local files
DEFAULT_MAX_WIDTH = 1920
DEFAULT_MAX_HEIGHT = 1080
DEFAULT_JPEG_QUALITY = 85


class VisionMessageHandler:
    """
    Handles vision processing for Qwen3-VL native multimodal capabilities.
    
    This class is responsible for:
    1. Converting image URLs to base64 data URLs when needed
    2. Processing local file paths and encoding images
    3. Formatting messages in OpenAI vision format for Qwen3-VL
    4. Validating image formats and sizes
    """
    
    def __init__(self):
        """Initialize the vision message handler."""
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; Suna-Vision-Handler/1.0)"
        })
    
    def format_message_with_images(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format a message to include images in Qwen3-VL native vision format.
        
        Args:
            message: Message dict with 'role' and 'content' fields
            
        Returns:
            Formatted message dict with images properly encoded for Qwen3-VL
            
        Example:
            Input: {"role": "user", "content": "Look at this image: /workspace/image.jpg"}
            Output: {
                "role": "user", 
                "content": [
                    {"type": "text", "text": "Look at this image: "},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
                ]
            }
        """
        try:
            if not isinstance(message, dict):
                logger.warning(f"Invalid message format: {type(message)}")
                return message
                
            if 'content' not in message:
                return message
                
            content = message['content']
            
            # Handle string content (most common case)
            if isinstance(content, str):
                formatted_content = self._process_text_content(content)
                if formatted_content != content:  # Only update if images were found
                    message['content'] = formatted_content
                    logger.debug(f"Formatted message with images: {len(formatted_content)} content items")
                    
            # Handle list content (already structured)
            elif isinstance(content, list):
                formatted_content = self._process_list_content(content)
                if formatted_content != content:  # Only update if changes were made
                    message['content'] = formatted_content
                    
            return message
            
        except Exception as e:
            logger.error(f"Error formatting message with images: {str(e)}")
            # Return original message on error to avoid breaking the flow
            return message
    
    def _process_text_content(self, content: str) -> Union[str, List[Dict[str, Any]]]:
        """
        Process text content to extract and format image references.
        
        Args:
            content: String content that may contain image references
            
        Returns:
            Either original string (no images) or list with text and image content
        """
        # Look for image references in common patterns
        # This handles cases where users reference images by path or URL
        image_references = self._extract_image_references(content)
        
        if not image_references:
            return content
        
        # Build content list with text and images
        content_items = []
        remaining_text = content
        
        # Sort by position to process in order
        image_refs_sorted = sorted(image_references.items(), key=lambda x: x[1]['start'])
        
        last_pos = 0
        for img_ref, img_info in image_refs_sorted:
            # Add text before the image reference
            if img_info['start'] > last_pos:
                text_segment = remaining_text[last_pos:img_info['start']]
                if text_segment.strip():
                    content_items.append({"type": "text", "text": text_segment.strip()})
            
            # Process the image
            image_path = img_info['path']
            try:
                image_url = self._process_image_reference(image_path)
                content_items.append({
                    "type": "image_url", 
                    "image_url": {"url": image_url}
                })
                logger.debug(f"Added image to message: {image_path}")
            except Exception as e:
                logger.warning(f"Failed to process image {image_path}: {str(e)}")
                # Add the original text as fallback
                content_items.append({"type": "text", "text": img_ref})
            
            last_pos = img_info['end']
        
        # Add remaining text
        if last_pos < len(remaining_text):
            remaining_content = remaining_text[last_pos:].strip()
            if remaining_content:
                content_items.append({"type": "text", "text": remaining_content})
        
        return content_items
    
    def _process_list_content(self, content: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process list content to handle any image references.
        
        Args:
            content: List of content items
            
        Returns:
            Updated list with images properly formatted
        """
        formatted_content = []
        
        for item in content:
            if not isinstance(item, dict):
                continue
                
            # Handle text items that might contain image references
            if item.get('type') == 'text' and isinstance(item.get('text'), str):
                text_content = item['text']
                image_refs = self._extract_image_references(text_content)
                
                if not image_refs:
                    # No images found, keep original item
                    formatted_content.append(item)
                else:
                    # Process text with images
                    processed_content = self._process_text_content(text_content)
                    if isinstance(processed_content, list):
                        # Merge the processed content
                        formatted_content.extend(processed_content)
                    else:
                        # No processing needed
                        formatted_content.append(item)
            
            # Handle existing image_url items to ensure they're properly formatted
            elif item.get('type') == 'image_url':
                image_info = item.get('image_url', {})
                url = image_info.get('url', '')
                
                if url:
                    # Process the image URL to ensure it's in the right format
                    try:
                        processed_url = self._process_image_reference(url)
                        formatted_content.append({
                            "type": "image_url",
                            "image_url": {"url": processed_url}
                        })
                    except Exception as e:
                        logger.warning(f"Failed to process existing image URL {url}: {str(e)}")
                        # Keep original if processing fails
                        formatted_content.append(item)
                else:
                    formatted_content.append(item)
            
            else:
                # Keep other content types as-is
                formatted_content.append(item)
        
        return formatted_content
    
    def _extract_image_references(self, text: str) -> Dict[str, Dict[str, Any]]:
        """
        Extract image references from text content.
        
        Args:
            text: Text content to scan for image references
            
        Returns:
            Dict mapping image reference to position info
        """
        import re
        
        image_refs = {}
        
        # Pattern 1: URLs (check first to get full URLs)
        url_pattern = r'(https?://[^\s]+\.(jpg|jpeg|png|gif|webp|svg))'
        for match in re.finditer(url_pattern, text, re.IGNORECASE):
            ref = match.group(1)
            image_refs[ref] = {
                'path': ref,
                'start': match.start(),
                'end': match.end()
            }
        
        # Pattern 2: Local file paths (absolute or relative)
        # Match paths starting with / or filenames without protocols
        path_pattern = r'(?:(?<=\s)|^)([/\w\-._]*\.(jpg|jpeg|png|gif|webp|svg))(?=\s|$)'
        for match in re.finditer(path_pattern, text, re.IGNORECASE):
            ref = match.group(1)
            # Only include if it's a local path (starts with /) or a simple filename
            # and it's not already found as a URL
            if (ref not in image_refs and 
                (ref.startswith('/') or not '://' in ref) and
                not ref.startswith('//')):  # Exclude protocol-relative URLs
                image_refs[ref] = {
                    'path': ref,
                    'start': match.start(),
                    'end': match.end()
                }
        
        return image_refs
    
    def _process_image_reference(self, image_ref: str) -> str:
        """
        Process an image reference and return it as a base64 data URL.
        
        Args:
            image_ref: Path or URL to the image
            
        Returns:
            Base64 data URL for the image
            
        Raises:
            Exception: If image processing fails
        """
        try:
            # Check if it's already a data URL
            if image_ref.startswith('data:'):
                return image_ref
            
            # Check if it's a URL
            if self._is_url(image_ref):
                return self._process_image_url(image_ref)
            
            # Check if it's a local file path
            if os.path.exists(image_ref):
                return self._process_local_file(image_ref)
            
            # If we get here, we couldn't resolve the image
            raise Exception(f"Image not found: {image_ref}")
            
        except Exception as e:
            logger.error(f"Failed to process image reference '{image_ref}': {str(e)}")
            raise
    
    def _is_url(self, path: str) -> bool:
        """Check if a path is a URL."""
        parsed = urlparse(path)
        return parsed.scheme in ('http', 'https')
    
    def _process_image_url(self, url: str) -> str:
        """
        Process an image URL and return it as a base64 data URL.
        
        Args:
            url: URL of the image
            
        Returns:
            Base64 data URL
        """
        try:
            # Download the image
            response = self.session.get(url, timeout=30, stream=True)
            response.raise_for_status()
            
            # Check content type
            content_type = response.headers.get('content-type', '')
            if not content_type.startswith('image/'):
                raise Exception(f"URL does not point to an image: {url} (Content-Type: {content_type})")
            
            # Check size
            content_length = int(response.headers.get('content-length', 0))
            if content_length > MAX_IMAGE_SIZE:
                raise Exception(f"Image too large: {content_length / 1024 / 1024:.1f}MB")
            
            # Download and encode
            image_bytes = response.content
            if len(image_bytes) > MAX_IMAGE_SIZE:
                raise Exception(f"Downloaded image too large: {len(image_bytes) / 1024 / 1024:.1f}MB")
            
            return self._encode_image_as_base64(image_bytes, content_type)
            
        except Exception as e:
            logger.error(f"Failed to process image URL '{url}': {str(e)}")
            raise
    
    def _process_local_file(self, file_path: str) -> str:
        """
        Process a local image file and return it as a base64 data URL.
        
        Args:
            file_path: Local path to the image
            
        Returns:
            Base64 data URL
        """
        try:
            # Determine MIME type
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type or not mime_type.startswith('image/'):
                # Fallback based on extension
                ext = os.path.splitext(file_path)[1].lower()
                if ext == '.jpg' or ext == '.jpeg':
                    mime_type = 'image/jpeg'
                elif ext == '.png':
                    mime_type = 'image/png'
                elif ext == '.gif':
                    mime_type = 'image/gif'
                elif ext == '.webp':
                    mime_type = 'image/webp'
                elif ext == '.svg':
                    mime_type = 'image/svg+xml'
                else:
                    raise Exception(f"Unsupported image format: {file_path}")
            
            # Check file size
            file_size = os.path.getsize(file_path)
            if file_size > MAX_IMAGE_SIZE:
                raise Exception(f"Image file too large: {file_size / 1024 / 1024:.1f}MB")
            
            # Read and process the image
            with open(file_path, 'rb') as f:
                image_bytes = f.read()
            
            # Compress if needed
            if len(image_bytes) > MAX_IMAGE_SIZE * 0.8:  # Compress if over 80% of limit
                image_bytes, mime_type = self._compress_image(image_bytes, mime_type, file_path)
            
            return self._encode_image_as_base64(image_bytes, mime_type)
            
        except Exception as e:
            logger.error(f"Failed to process local image file '{file_path}': {str(e)}")
            raise
    
    def _compress_image(self, image_bytes: bytes, mime_type: str, file_path: str) -> Tuple[bytes, str]:
        """
        Compress an image to reduce its size.
        
        Args:
            image_bytes: Original image bytes
            mime_type: MIME type of the image
            file_path: Original file path (for logging)
            
        Returns:
            Tuple of (compressed_bytes, new_mime_type)
        """
        try:
            # Open image from bytes
            img = Image.open(BytesIO(image_bytes))
            
            # Convert RGBA to RGB if necessary (for JPEG)
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            
            # Calculate new dimensions while maintaining aspect ratio
            width, height = img.size
            if width > DEFAULT_MAX_WIDTH or height > DEFAULT_MAX_HEIGHT:
                ratio = min(DEFAULT_MAX_WIDTH / width, DEFAULT_MAX_HEIGHT / height)
                new_width = int(width * ratio)
                new_height = int(height * ratio)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                logger.debug(f"Resized image from {width}x{height} to {new_width}x{new_height}")
            
            # Save to bytes with compression
            output = BytesIO()
            
            # Determine output format
            if mime_type == 'image/gif':
                img.save(output, format='GIF', optimize=True)
                output_mime = 'image/gif'
            elif mime_type == 'image/png':
                img.save(output, format='PNG', optimize=True, compress_level=6)
                output_mime = 'image/png'
            else:
                # Convert to JPEG for better compression
                img.save(output, format='JPEG', quality=DEFAULT_JPEG_QUALITY, optimize=True)
                output_mime = 'image/jpeg'
            
            compressed_bytes = output.getvalue()
            
            # Log compression results
            original_size = len(image_bytes)
            compressed_size = len(compressed_bytes)
            compression_ratio = (1 - compressed_size / original_size) * 100
            logger.debug(f"Compressed '{file_path}' from {original_size / 1024:.1f}KB to {compressed_size / 1024:.1f}KB ({compression_ratio:.1f}% reduction)")
            
            return compressed_bytes, output_mime
            
        except Exception as e:
            logger.warning(f"Failed to compress image '{file_path}': {str(e)}. Using original.")
            # Return original if compression fails
            return image_bytes, mime_type
    
    def _encode_image_as_base64(self, image_bytes: bytes, mime_type: str) -> str:
        """
        Encode image bytes as a base64 data URL.
        
        Args:
            image_bytes: Image data to encode
            mime_type: MIME type of the image
            
        Returns:
            Base64 data URL string
        """
        # Validate MIME type
        if mime_type not in SUPPORTED_MIME_TYPES:
            logger.warning(f"Image format '{mime_type}' may not be supported by Qwen3-VL")
        
        # Encode to base64
        base64_data = base64.b64encode(image_bytes).decode('utf-8')
        
        # Create data URL
        data_url = f"data:{mime_type};base64,{base64_data}"
        
        return data_url
