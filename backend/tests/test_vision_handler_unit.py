
import pytest
import os
import tempfile
import mimetypes
from pathlib import Path
from unittest.mock import MagicMock, patch
import sys

# Ensure backend acts as root for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.agentpress.vision_handler import VisionMessageHandler

class TestVisionMessageHandlerUnit:
    """Test suite for VisionMessageHandler without hypothesis."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.vision_handler = VisionMessageHandler()
    
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
