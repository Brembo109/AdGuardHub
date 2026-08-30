"""Password hashing, credential encryption and session cookie signing."""

from __future__ import annotations

import base64
import hashlib
import secrets

import bcrypt
from cryptography.fernet import Fernet, InvalidToken
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import get_settings

_DEV_KEY_MARKER = "insecure-dev-key"


def resolve_secret_key() -> str:
    """Return the configured master secret, falling back to an ephemeral dev key.

    A generated key means sessions and stored credentials do not survive a restart,
    so ``main`` warns loudly when this path is taken.
    """
    settings = get_settings()
    if settings.secret_key:
        return settings.secret_key
    return f"{_DEV_KEY_MARKER}:{secrets.token_urlsafe(32)}"


def is_ephemeral_key(key: str) -> bool:
    return key.startswith(_DEV_KEY_MARKER)


class Crypto:
    """Fernet-based encryption for instance credentials.

    The key is derived from the master secret rather than stored anywhere, so the
    database on its own never contains enough to decrypt the credentials.
    """

    def __init__(self, secret_key: str) -> None:
        digest = hashlib.sha256(secret_key.encode("utf-8")).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:  # pragma: no cover - depends on operator error
            raise ValueError(
                "Stored credentials could not be decrypted. Did ADGUARDHUB_SECRET_KEY change?"
            ) from exc


class Sessions:
    """Signed, expiring session cookies for the single admin user."""

    def __init__(self, secret_key: str) -> None:
        self._serializer = URLSafeTimedSerializer(secret_key, salt="adguardhub-session")

    def issue(self, username: str) -> str:
        return self._serializer.dumps({"sub": username})

    def verify(self, token: str, max_age: int) -> str | None:
        try:
            data = self._serializer.loads(token, max_age=max_age)
        except (BadSignature, SignatureExpired):
            return None
        subject = data.get("sub") if isinstance(data, dict) else None
        return subject if isinstance(subject, str) else None


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False
