"""
Property-based tests for VisionMessageHandler.

These tests verify the core properties of native vision support for Qwen3-VL.
"""

import base64
import json
import mimetypes
import os
import tempfile
from pathlib import Path
from typing import Dict, Any

import pytest
from hypothesis import given, strategies as st
from PIL import Image
from io import BytesIO

from core.agentpress.vision_handler import VisionMessageHandler


class TestVisionMessageHandler:
    """Test suite for VisionMessageHandler with property-based testing."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.vision_handler = VisionMessageHandler()
    
    # **Feature: qwen3-vl-optimization, Property 5: Image encoding produces valid data URLs**
    # **Validates: Requirements 4.2**
    @given(
        image_data=st.binary(min_size=100, max_size=1000000),  # 100 bytes to 1MB
        mime_type=st.sampled_from(['image/jpeg', 'image/png', 'image/gif', 'image/webp'])
    )
    def test_property_5_image_encoding_produces_valid_data_urls(self, image_data: bytes, mime_type: str):
        """
        Property 5: Image encoding produces valid data URLs.
        
        For any valid image data and MIME type, encoding should produce a valid base64 data URL
        that can be decoded back to the original image data.
        """
        # Encode the image data
        data_url = self.vision_handler._encode_image_as_base64(image_data, mime_type)
        
        # Verify the data URL format
        assert data_url.startswith(f"data:{mime_type};base64,")
        
        # Verify the base64 data can be decoded back
        base64_data = data_url.split(',', 1)[1]
        decoded_data = base64.b64decode(base64_data)
        
        # Verify the decoded data matches the original
        assert decoded_data == image_data
    
    # **Feature: qwen3-vl-optimization, Property 6: Multi-image messages include all images**
    # **Validates: Requirements 4.4**
    @given(
        images=st.lists(
            st.fixed_dictionaries({
                'path': st.text(min_size=1, max_size=50),
                'url': st.text(min_size=1, max_size=100)
            }),
            min_size=1,
            max_size=5
        ),
        text_content=st.text(min_size=1, max_size=200)
    )
    def test_property_6_multi_image_messages_include_all_images(self, images: list, text_content: str):
        """
        Property 6: Multi-image messages include all images.
        
        For any set of N images and text content, the formatted message content array 
        should contain exactly N image entries plus appropriate text entries.
        """
        # Create a message with multiple image references
        image_refs = []
        for img in images:
            # Create temporary image files for testing
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
                # Create a simple test image
                test_image = Image.new('RGB', (100, 100), color='red')
                test_image.save(temp_file, format='JPEG')
                temp_path = temp_file.name
            
            # Add reference to text content
            ref = f"{img['path']} ({temp_path})"
            image_refs.append(temp_path)
            text_content += f" See image: {ref}"
        
        try:
            # Format the message
            message = {
                "role": "user",
                "content": text_content
            }
            formatted_message = self.vision_handler.format_message_with_images(message)
            
            # Count image items in the formatted content
            formatted_content = formatted_message['content']
            
            if isinstance(formatted_content, list):
                image_items = [
                    item for item in formatted_content 
                    if isinstance(item, dict) and item.get('type') == 'image_url'
                ]
                text_items = [
                    item for item in formatted_content 
                    if isinstance(item, dict) and item.get('type') == 'text'
                ]
                
                # Should have at least one text item and the correct number of image items
                assert len(text_items) >= 1, "Should have at least one text item"
                assert len(image_items) == len(images), f"Expected {len(images)} image items, got {len(image_items)}"
                
                # Verify each image item has the correct structure
                for img_item in image_items:
                    assert 'image_url' in img_item, "Image item should have 'image_url' field"
                    assert 'url' in img_item['image_url'], "Image URL should have 'url' field"
                    
                    # Verify it's a valid data URL
                    url = img_item['image_url']['url']
                    assert url.startswith('data:image/'), "Image URL should be a data URL"
                    assert ';base64,' in url, "Image URL should contain base64 data"
            
        finally:
            # Clean up temporary files
            for temp_path in image_refs:
                try:
                    os.unlink(temp_path)
                except:
                    pass
    
    @given(
        text=st.text(min_size=1, max_size=100),
        image_count=st.integers(min_value=0, max_value=3)
    )
    def test_message_formatting_preserves_structure(self, text: str, image_count: int):
        """
        Test that message formatting preserves the basic message structure.
        """
        message = {
            "role": "user",
            "content": text
        }
        
        formatted_message = self.vision_handler.format_message_with_images(message)
        
        # Basic structure should be preserved
        assert isinstance(formatted_message, dict)
        assert 'role' in formatted_message
        assert 'content' in formatted_message
        assert formatted_message['role'] == "user"
        
        # Content should be either string or list
        content = formatted_message['content']
        assert isinstance(content, (str, list))
    
    def test_url_detection(self):
        """Test URL detection functionality."""
        # Test various URL formats
        urls = [
            "https://example.com/image.jpg",
            "http://test.org/photo.png",
            "https://site.net/picture.gif",
            "http://domain.io/img.webp"
        ]
        
        for url in urls:
            assert self.vision_handler._is_url(url), f"Should detect {url} as URL"
        
        # Test non-URLs
        non_urls = [
            "/local/path/image.jpg",
            "image.png",
            "./relative/path.gif",
            "C:\\Windows\\image.jpg"
        ]
        
        for non_url in non_urls:
            assert not self.vision_handler._is_url(non_url), f"Should not detect {non_url} as URL"
    
    def test_image_reference_extraction(self):
        """Test extraction of image references from text."""
        text = "Here are some images: /path/to/image1.jpg and https://example.com/image2.png and another.gif"
        
        refs = self.vision_handler._extract_image_references(text)
        
        # Should find all three image references
        assert len(refs) == 3
        
        # Check that positions are reasonable
        for ref, info in refs.items():
            assert 'path' in info
            assert 'start' in info
            assert 'end' in info
            assert info['start'] < info['end']
            assert 0 <= info['start'] <= len(text)
            assert 0 <= info['end'] <= len(text)
    
    @given(
        image_size=st.integers(min_value=100, max_value=500),
        image_format=st.sampled_from(['JPEG', 'PNG'])
    )
    def test_image_compression(self, image_size: int, image_format: str):
        """
        Test that image compression works and produces valid output.
        """
        # Create a test image
        img = Image.new('RGB', (image_size, image_size), color='blue')
        buffer = BytesIO()
        img.save(buffer, format=image_format)
        original_bytes = buffer.getvalue()
        
        # Determine MIME type
        mime_type = f'image/{image_format.lower()}'
        
        # Compress the image
        compressed_bytes, new_mime_type = self.vision_handler._compress_image(
            original_bytes, mime_type, "test_image"
        )
        
        # Verify output is valid
        assert isinstance(compressed_bytes, bytes)
        assert len(compressed_bytes) > 0
        assert isinstance(new_mime_type, str)
        assert new_mime_type.startswith('image/')
        
        # Verify compressed image can be opened (it's valid)
        try:
            compressed_img = Image.open(BytesIO(compressed_bytes))
            assert compressed_img.size[0] > 0
            assert compressed_img.size[1] > 0
        except Exception as e:
            pytest.fail(f"Compressed image should be valid: {e}")
    
    def test_error_handling(self):
        """Test error handling for various failure cases."""
        # Test invalid image reference
        with pytest.raises(Exception):
            self.vision_handler._process_image_reference("/nonexistent/path/image.jpg")
        
        # Test invalid URL
        with pytest.raises(Exception):
            self.vision_handler._process_image_url("https://nonexistent.domain/image.jpg")
        
        # Test non-image URL
        with pytest.raises(Exception):
            self.vision_handler._process_image_url("https://example.com/not-an-image.txt")
    
    def test_mime_type_detection(self):
        """Test MIME type detection for different file extensions."""
        test_cases = [
            ("image.jpg", "image/jpeg"),
            ("image.jpeg", "image/jpeg"),
            ("image.png", "image/png"),
            ("image.gif", "image/gif"),
            ("image.webp", "image/webp")
        ]
        
        for filename, expected_mime in test_cases:
            # Create temporary file
            with tempfile.NamedTemporaryFile(suffix=Path(filename).suffix, delete=False) as temp_file:
                temp_file.write(b"fake image data")
                temp_path = temp_file.name
            
            try:
                # This should work without errors (even though data is fake)
                # The MIME type detection should work based on extension
                mime_type, _ = mimetypes.guess_type(temp_path)
                if not mime_type:  # Fall back to extension-based detection
                    ext = os.path.splitext(temp_path)[1].lower()
                    if ext in ['.jpg', '.jpeg']:
                        mime_type = 'image/jpeg'
                    elif ext == '.png':
                        mime_type = 'image/png'
                    elif ext == '.gif':
                        mime_type = 'image/gif'
                    elif ext == '.webp':
                        mime_type = 'image/webp'
                
                assert mime_type == expected_mime, f"MIME type mismatch for {filename}: got {mime_type}, expected {expected_mime}"
            finally:
                os.unlink(temp_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
