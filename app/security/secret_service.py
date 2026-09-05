"""Encrypts/decrypts secret material (passwords, PATs) at rest.

The master key is provided only via the DB_VALIDATOR_MASTER_KEY environment
variable and is NEVER persisted inside data/app.db. If no key is configured,
a process-local ephemeral key is generated so the app remains runnable in
dev/test, but this must not be relied on in production (encrypted values
become undecryptable after restart).
"""
from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

logger = logging.getLogger(__name__)

_ENCRYPTED_PREFIX = "enc::"


def _derive_fernet_key(raw_key: str) -> bytes:
    """Accept either a proper Fernet key or an arbitrary passphrase."""
    try:
        # Valid Fernet keys are urlsafe-base64, 32 bytes when decoded.
        decoded = base64.urlsafe_b64decode(raw_key.encode())
        if len(decoded) == 32:
            return raw_key.encode()
    except Exception:
        pass
    # Derive a 32-byte key deterministically from an arbitrary passphrase.
    digest = hashlib.sha256(raw_key.encode()).digest()
    return base64.urlsafe_b64encode(digest)


class SecretService:
    """Abstraction over secret encryption. Swappable for a KMS-backed impl."""

    def __init__(self, master_key: str | None = None):
        settings = get_settings()
        key = master_key if master_key is not None else settings.db_validator_master_key
        if not key:
            logger.warning(
                "DB_VALIDATOR_MASTER_KEY is not set; using an ephemeral in-memory "
                "key. Encrypted secrets will NOT survive an application restart. "
                "Set DB_VALIDATOR_MASTER_KEY for production use."
            )
            key = Fernet.generate_key().decode()
        self._fernet = Fernet(_derive_fernet_key(key))

    def encrypt(self, plaintext: str | None) -> str | None:
        if plaintext is None:
            return None
        token = self._fernet.encrypt(plaintext.encode()).decode()
        return _ENCRYPTED_PREFIX + token

    def decrypt(self, ciphertext: str | None) -> str | None:
        if ciphertext is None:
            return None
        if not ciphertext.startswith(_ENCRYPTED_PREFIX):
            # Not encrypted (e.g. legacy/plain) - return as-is defensively.
            return ciphertext
        token = ciphertext[len(_ENCRYPTED_PREFIX):]
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except InvalidToken:
            raise ValueError(
                "Unable to decrypt secret. The master key may have changed "
                "or the data is corrupt."
            )

    def is_encrypted(self, value: str | None) -> bool:
        return bool(value) and value.startswith(_ENCRYPTED_PREFIX)


_default_service: SecretService | None = None


def get_secret_service() -> SecretService:
    global _default_service
    if _default_service is None:
        _default_service = SecretService()
    return _default_service
