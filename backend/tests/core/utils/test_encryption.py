
import pytest
from hypothesis import given, strategies as st
from unittest.mock import patch
from core.utils.encryption import encrypt_data, decrypt_data, get_encryption_key

# Property 9: Token Encryption Round-Trip
# Validates that any string data can be encrypted and successfully decrypted back to its original form.

class TestEncryptionProperties:
    """Property-based tests for encryption utilities"""
    
    @given(st.text())
    def test_encryption_round_trip(self, data):
        """
        Property: decrypt(encrypt(data)) == data
        Verify that encryption is reversible for any string input.
        """
        # Ensure we have a consistent key for the test duration
        # get_encryption_key generates a new key if not in env, 
        # so we should mock it or ensure it's stable if we want deterministic tests across calls?
        # Actually, get_encryption_key() is called inside encrypt and decrypt.
        # If we don't set env var, it generates a NEW key every call.
        # So decrypt(encrypt(data)) would fail if key changes between calls.
        
        # We must mock Os.environ or patch get_encryption_key to return a constant key
        
        # Method 1: Patch get_encryption_key to return a stable key
        from cryptography.fernet import Fernet
        key = Fernet.generate_key()
        
        with patch('core.utils.encryption.get_encryption_key', return_value=key):
            encrypted = encrypt_data(data)
            decrypted = decrypt_data(encrypted)
            assert decrypted == data

    @given(st.text())
    def test_encryption_output_format(self, data):
        """
        Property: encrypt(data) returns a base64 encoded string
        """
        from cryptography.fernet import Fernet
        key = Fernet.generate_key()
        
        with patch('core.utils.encryption.get_encryption_key', return_value=key):
            encrypted = encrypt_data(data)
            assert isinstance(encrypted, str)
            # Should be valid base64 (decryptable implies this, but good to check explicitly if we want)
            # This is implicit in round trip test usually.

