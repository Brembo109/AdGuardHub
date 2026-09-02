"""Process-wide singletons derived from the master secret."""

from __future__ import annotations

from functools import lru_cache

from .security import Crypto, Sessions, VerifiedCredentials, is_ephemeral_key, resolve_secret_key
from .services.throttle import LoginThrottle
from .services.updates import UpdateChecker
from .version import VERSION


@lru_cache
def _secret() -> str:
    return resolve_secret_key()


@lru_cache
def get_crypto() -> Crypto:
    return Crypto(_secret())


@lru_cache
def get_sessions() -> Sessions:
    return Sessions(_secret())


@lru_cache
def get_credentials() -> VerifiedCredentials:
    return VerifiedCredentials()


@lru_cache
def get_login_throttle() -> LoginThrottle:
    return LoginThrottle()


@lru_cache
def get_update_checker() -> UpdateChecker:
    """One checker for the process, so its cache is shared by every request."""
    return UpdateChecker(VERSION)


def using_ephemeral_secret() -> bool:
    return is_ephemeral_key(_secret())
