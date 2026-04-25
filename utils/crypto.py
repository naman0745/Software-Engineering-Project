"""
utils/crypto.py
---------------
Cryptographic helpers used across the application.
All sensitive values (amounts, keys) are hashed before storage.
"""

import hashlib


def sha256(value) -> str:
    """
    Return the SHA-256 hex digest of any value.

    Args:
        value: Any value that can be cast to str.

    Returns:
        64-character lowercase hex string.

    Example:
        >>> sha256(15000)
        'd4c999ae43633bd2...'
    """
    return hashlib.sha256(str(value).encode()).hexdigest()
