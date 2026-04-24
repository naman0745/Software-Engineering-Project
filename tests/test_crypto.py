"""
tests/test_crypto.py
--------------------
Unit tests for cryptographic helpers.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.crypto import sha256


class TestSha256:

    def test_returns_64_char_hex(self):
        result = sha256("hello")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self):
        assert sha256("trustgrid") == sha256("trustgrid")

    def test_different_values_differ(self):
        assert sha256("abc") != sha256("xyz")

    def test_int_input_works(self):
        result = sha256(15000)
        assert len(result) == 64

    def test_known_hash(self):
        # SHA-256 of empty string is well-known
        expected = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        assert sha256("") == expected
