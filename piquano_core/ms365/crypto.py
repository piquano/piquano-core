"""Fernet-basierte Token-Verschlüsselung."""

from cryptography.fernet import Fernet
from django.conf import settings


def _fernet():
    key = getattr(settings, "MS365_TOKEN_ENCRYPTION_KEY", "")
    if not key:
        raise ValueError("MS365_TOKEN_ENCRYPTION_KEY ist nicht konfiguriert.")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()
