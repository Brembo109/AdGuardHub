"""Password hashing, credential encryption and session cookie signing."""

from __future__ import annotations

import base64
import hashlib
import secrets
import time

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


class VerifiedCredentials:
    """Remembers that a username and password checked out, so bcrypt runs once.

    bcrypt is deliberately slow — around 300 ms on this hardware — which is right
    for a login form and wrong for an API that a phone polls every few seconds.
    HTTP Basic Auth presents the password on every single request, so without this
    the AdGuard-compatible surface would spend a third of a second of CPU per call.

    Only successes are remembered. A wrong password therefore always costs the
    full check and cannot be used to fill this from outside, which keeps the
    dictionary bounded by the number of credentials that actually work.
    """

    def __init__(self, ttl: float = 300.0) -> None:
        self._ttl = ttl
        self._seen: dict[str, float] = {}

    @staticmethod
    def _key(username: str, password: str) -> str:
        # A digest, so the plaintext password is never held in the dictionary.
        return hashlib.sha256(f"{username}\0{password}".encode()).hexdigest()

    def check(self, username: str, password: str, *, now: float | None = None) -> bool:
        moment = time.monotonic() if now is None else now
        key = self._key(username, password)
        expires = self._seen.get(key)
        if expires is None:
            return False
        if expires <= moment:
            del self._seen[key]
            return False
        return True

    def remember(self, username: str, password: str, *, now: float | None = None) -> None:
        moment = time.monotonic() if now is None else now
        self._seen[self._key(username, password)] = moment + self._ttl

    def forget_all(self) -> None:
        """Drop everything — the password changed, so nothing accepted before may pass."""
        self._seen.clear()
