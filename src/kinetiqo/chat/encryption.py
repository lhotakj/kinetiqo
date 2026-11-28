"""Versioned AES-GCM envelopes for provider API keys."""

import base64
import os
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_CONTEXT = b"kinetiqo-chat-key-encryption-v1"


class ChatEncryptionError(ValueError):
    """Raised without exposing encryption implementation details."""


def _derive_key(secret: str) -> bytes:
    source = secret.encode("utf-8")
    if len(source) < 32:
        raise ChatEncryptionError("Chat encryption requires a persistent secret of at least 32 bytes.")
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_CONTEXT).derive(source)


def encrypt_api_key(value: str, secret: str) -> str:
    if not value:
        raise ChatEncryptionError("An API key is required.")
    nonce = os.urandom(12)
    ciphertext = AESGCM(_derive_key(secret)).encrypt(nonce, value.encode("utf-8"), None)
    return "v1:" + base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_api_key(envelope: str, secret: str) -> str:
    try:
        version, encoded = envelope.split(":", 1)
        if version != "v1":
            raise ValueError("unsupported version")
        payload = base64.urlsafe_b64decode(encoded.encode("ascii"))
        if len(payload) < 29:
            raise ValueError("invalid envelope")
        return AESGCM(_derive_key(secret)).decrypt(payload[:12], payload[12:], None).decode("utf-8")
    except (ValueError, InvalidTag, UnicodeDecodeError) as exc:
        raise ChatEncryptionError("The saved AI key cannot be decrypted. Ask an administrator to replace it.") from exc

