"""Password hashing, credential encryption and session cookie signing."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import os
import secrets
import time
from dataclasses import dataclass
from functools import lru_cache

import bcrypt
from cryptography.fernet import Fernet, InvalidToken
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import get_settings

logger = logging.getLogger(__name__)

_DEV_KEY_MARKER = "insecure-dev-key"

KEY_FILENAME = "secret.key"

# Keys that have appeared in this project's own documentation. Anyone running
# with one of these has an encryption key that can be read off GitHub, and —
# unlike a missing key — nothing about it looks wrong: the hub starts, works,
# and warns about nothing. That is the more dangerous failure of the two, since
# a missing key loses the stored credentials while a published one exposes them.
PLACEHOLDER_KEYS = frozenset(
    {
        "change-me-to-a-long-random-string",
        "<a long random string>",
        "change-me",
        "changeme",
        "your-secret-key",
        "secret",
    }
)

# Long enough that a key is not being typed by hand. Short keys are only warned
# about, never refused: they are weak but private, which is a different problem
# from one that is published.
ADVISED_KEY_LENGTH = 24


class SecretKeyError(RuntimeError):
    """The configured key must not be used, and using it anyway would be worse."""


def resolve_secret_key() -> str:
    """Return the master secret, generating and persisting one if none is set.

    Three cases, in the order they are checked:

    * **Configured** — used as given. This stays the recommended setup, because
      it is the only one where the key does not live beside the data it protects.
    * **A documented placeholder** — refused. See ``PLACEHOLDER_KEYS``.
    * **Unset** — a strong key is generated once and kept in the data directory.
      Instance credentials then survive a restart without anyone having to set
      anything, which is what makes the encryption worth having at all: without
      persistence the realistic default was a hub that lost its credentials on
      every update, and the realistic workaround was pasting the placeholder.

    That last case is a deliberate reading of spec §8 rather than a literal one.
    The key sits next to the database instead of outside it, so it no longer
    defends against someone holding the whole data directory — but it still does
    the one thing the encryption is for: the database file alone is not enough.
    """
    settings = get_settings()
    configured = settings.secret_key.strip()
    if configured:
        if configured in PLACEHOLDER_KEYS:
            raise SecretKeyError(
                f"ADGUARDHUB_SECRET_KEY is set to {configured!r}, which is a placeholder from "
                "AdGuardHub's own documentation — anyone can read it, so the stored AdGuard "
                "credentials would not be protected. Generate one with "
                "`openssl rand -base64 48`, or remove the variable entirely and the hub will "
                "create and keep its own. Either way the instance passwords have to be entered "
                "again, because changing the key makes the stored ones unreadable."
            )
        if len(configured) < ADVISED_KEY_LENGTH:
            logger.warning(
                "ADGUARDHUB_SECRET_KEY is only %d characters. Generate a longer one with "
                "`openssl rand -base64 48`.",
                len(configured),
            )
        return configured
    return _stored_key(settings.data_dir)


def _stored_key(data_dir: str) -> str:
    """Read the generated key from the data directory, creating it once.

    Falls back to the old ephemeral key when the directory cannot be written, so
    an unwritable volume still starts the hub with the warning it always had,
    rather than turning a warning into an outage.
    """
    path = os.path.join(data_dir.rstrip("/") or ".", KEY_FILENAME)
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        # O_EXCL rather than "check then write": two workers starting together
        # would otherwise generate different keys and the loser's would silently
        # replace the winner's, leaving half the credentials undecryptable.
        try:
            handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            with open(path, encoding="utf-8") as existing:
                stored = existing.read().strip()
            if stored:
                return stored
            # An empty file is a half-finished write from a previous start.
            os.unlink(path)
            return _stored_key(data_dir)
        with os.fdopen(handle, "w", encoding="utf-8") as created:
            key = secrets.token_urlsafe(48)
            created.write(key + "\n")
        logger.info(
            "ADGUARDHUB_SECRET_KEY is not set, so a key was generated and stored at %s. "
            "Back that file up with the database — without it the stored instance "
            "credentials cannot be read.",
            path,
        )
        return key
    except OSError as exc:
        logger.warning(
            "Could not read or write %s (%s), so a temporary key is in use. Sessions and "
            "stored instance credentials will NOT survive a restart.",
            path,
            exc,
        )
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


@dataclass(frozen=True, slots=True)
class SessionClaims:
    """What a valid session cookie says: who it is for, and which password it was issued under."""

    subject: str
    password_fingerprint: str

    def issued_under(self, password_hash: str) -> bool:
        """Whether the account's password is still the one this session was issued with."""
        return hmac.compare_digest(self.password_fingerprint, password_fingerprint(password_hash))


def password_fingerprint(password_hash: str) -> str:
    """A short, non-reversible stand-in for the stored hash.

    The cookie is signed, not encrypted, so whatever ties it to the password has
    to be safe to hand to the browser. A digest of the bcrypt hash says nothing
    about the password — the hash already carries its own salt and work factor —
    and it changes whenever the password does, which is the whole point.
    """
    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()[:16]


class Sessions:
    """Signed, expiring session cookies for the single admin user.

    A cookie is tied to the password it was issued under. Until it was, the
    signature alone decided, so a cookie stayed valid for its full fourteen days
    however many times the password was changed in between — and changing the
    password is exactly what an operator does when they suspect a session has
    been taken. Logging out never reached the server either, and there is no
    session table to revoke from; binding the token to the password hash is what
    gives the operator a way to end every session at once.
    """

    def __init__(self, secret_key: str) -> None:
        self._serializer = URLSafeTimedSerializer(secret_key, salt="adguardhub-session")

    def issue(self, username: str, password_hash: str) -> str:
        return self._serializer.dumps(
            {"sub": username, "pw": password_fingerprint(password_hash)}
        )

    def verify(self, token: str, max_age: int) -> SessionClaims | None:
        """The claims of a well-signed, unexpired token, or ``None``.

        Whether the password behind the claims is still current is the caller's
        question, because only the caller has the account in hand: see
        ``SessionClaims.issued_under``. A token from before fingerprints existed
        has none and is refused, which signs everyone out once on upgrade — the
        alternative is to keep honouring exactly the tokens this change exists
        to be able to end.
        """
        try:
            data = self._serializer.loads(token, max_age=max_age)
        except (BadSignature, SignatureExpired):
            return None
        if not isinstance(data, dict):
            return None
        subject, fingerprint = data.get("sub"), data.get("pw")
        if not isinstance(subject, str) or not isinstance(fingerprint, str):
            return None
        return SessionClaims(subject=subject, password_fingerprint=fingerprint)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


@lru_cache(maxsize=1)
def _decoy_hash() -> str:
    """A hash to check an unknown account's password against.

    Made once, from a password nobody knows, so that a sign-in for a name that
    does not exist costs the same bcrypt run as one for a name that does.
    """
    return hash_password(secrets.token_urlsafe(32))


async def check_password(password: str, password_hash: str | None) -> bool:
    """Whether ``password`` matches ``password_hash`` — off the event loop, and
    at the same cost whether or not there is an account behind it.

    bcrypt is ~300 ms of straight CPU work, by design. Run on the loop, that is
    300 ms during which nothing else in the hub moves: no push reaches a node,
    no query log entry is read, the event stream stalls, and every other request
    waits. And a login form is the one route on the hub that anyone on the
    network can hit without a session. ``asyncio.to_thread`` puts the work where
    it belongs.

    ``password_hash`` is ``None`` for an account that does not exist. Answering
    that case without hashing took about a millisecond against three hundred for
    a real account, which told anyone on the network the admin's username — half
    of the only credential the hub has — from timing alone. So the decoy hash is
    checked instead, and the answer is still no.
    """
    hashed = password_hash if password_hash is not None else _decoy_hash()
    matched = await asyncio.to_thread(verify_password, password, hashed)
    return matched and password_hash is not None


async def make_password_hash(password: str) -> str:
    """``hash_password`` off the event loop, for the same reason as ``check_password``."""
    return await asyncio.to_thread(hash_password, password)


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
