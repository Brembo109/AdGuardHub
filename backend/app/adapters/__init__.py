"""Adapter registry — the seam that keeps core logic off AdGuard's API (spec §3)."""

from __future__ import annotations

from ..models import Instance
from ..security import Crypto
from .adguard import AdGuardAdapter
from .base import (
    AdapterError,
    DnsAdapter,
    QueryLogEntry,
    RemoteFilterList,
    RemoteState,
    RemoteUpdate,
)

ADAPTERS: dict[str, type[DnsAdapter]] = {"adguard": AdGuardAdapter}


def _http_timeout() -> float:
    """Imported lazily: services import adapters, so a top-level import would cycle."""
    from ..services.hubsettings import current

    return float(current().http_timeout)


def available_adapters() -> list[str]:
    return sorted(ADAPTERS)


def build_adapter(instance: Instance, crypto: Crypto) -> DnsAdapter:
    """Instantiate the adapter for ``instance``, decrypting its stored credentials."""
    adapter_cls = ADAPTERS.get(instance.adapter)
    if adapter_cls is None:
        raise AdapterError(f"Unknown adapter '{instance.adapter}'")
    password = crypto.decrypt(instance.password_encrypted) if instance.password_encrypted else ""
    return adapter_cls(
        instance.base_url,
        instance.username,
        password,
        verify_tls=instance.verify_tls,
        timeout=_http_timeout(),
    )


__all__ = [
    "ADAPTERS",
    "AdGuardAdapter",
    "AdapterError",
    "DnsAdapter",
    "QueryLogEntry",
    "RemoteFilterList",
    "RemoteState",
    "RemoteUpdate",
    "available_adapters",
    "build_adapter",
]
