"""The AdGuard Home configuration areas AdGuardHub keeps in sync.

Everything a second node needs to be a faithful copy of the master lives here —
DNS and upstreams, clients, encryption, access lists, rewrites, blocked services,
protection toggles and logging.

DHCP is deliberately absent: leases and interface bindings are per-host state, and
copying them between nodes would be actively wrong.

Each section is described declaratively so the sync, reconcile and version layers
can treat them uniformly and a new area is a table entry rather than new code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Strategy = Literal["document", "toggle", "clients", "rewrites"]


@dataclass(frozen=True)
class SectionSpec:
    name: str
    title: str
    description: str
    strategy: Strategy
    get_path: str
    set_path: str = ""
    set_method: str = "POST"
    # Restricts what is read and written; empty means the whole document.
    keys: tuple[str, ...] = ()
    # "toggle" only: endpoints that flip the flag.
    enable_path: str = ""
    disable_path: str = ""
    # Push this section only when the operator opts in, because it can carry
    # material the API does not hand back in full (see push_guard).
    sensitive: bool = False
    notes: str = ""


SPECS: tuple[SectionSpec, ...] = (
    SectionSpec(
        name="dns",
        title="DNS & upstreams",
        description=(
            "Upstream, bootstrap and fallback resolvers, upstream mode, DNSSEC, caching, "
            "rate limiting and the blocking mode."
        ),
        strategy="document",
        get_path="/control/dns_info",
        set_path="/control/dns_config",
        keys=(
            "upstream_dns",
            "upstream_dns_file",
            "bootstrap_dns",
            "fallback_dns",
            "upstream_mode",
            "upstream_timeout",
            "protection_enabled",
            "dnssec_enabled",
            "disable_ipv6",
            "blocking_mode",
            "blocking_ipv4",
            "blocking_ipv6",
            "blocked_response_ttl",
            "edns_cs_enabled",
            "edns_cs_use_custom",
            "edns_cs_custom_ip",
            "cache_size",
            "cache_ttl_min",
            "cache_ttl_max",
            "cache_optimistic",
            "resolve_clients",
            "use_private_ptr_resolvers",
            "local_ptr_upstreams",
            "private_upstream",
            "ratelimit",
            "ratelimit_subnet_len_ipv4",
            "ratelimit_subnet_len_ipv6",
            "ratelimit_whitelist",
        ),
    ),
    SectionSpec(
        name="clients",
        title="Clients",
        description="Persistent client definitions with their per-client filtering settings.",
        strategy="clients",
        get_path="/control/clients",
    ),
    SectionSpec(
        name="access",
        title="Access control",
        description="Allowed and disallowed clients, and blocked hostnames.",
        strategy="document",
        get_path="/control/access/list",
        set_path="/control/access/set",
        keys=("allowed_clients", "disallowed_clients", "blocked_hosts"),
    ),
    SectionSpec(
        name="tls",
        title="Encryption (TLS)",
        description="HTTPS, DoT and DoQ settings, including the certificate and key.",
        strategy="document",
        get_path="/control/tls/status",
        set_path="/control/tls/configure",
        keys=(
            "enabled",
            "server_name",
            "force_https",
            "port_https",
            "port_dns_over_tls",
            "port_dns_over_quic",
            "certificate_chain",
            "private_key",
            "certificate_path",
            "private_key_path",
            "allow_unencrypted_doh",
        ),
        sensitive=True,
        notes=(
            "AdGuard Home does not return a stored private key over the API. This section "
            "is only pushed when the master exposes usable key material — inline "
            "certificate_chain plus private_key, or both file paths."
        ),
    ),
    SectionSpec(
        name="rewrites",
        title="DNS rewrites",
        description="Custom domain-to-answer rewrites.",
        strategy="rewrites",
        get_path="/control/rewrite/list",
    ),
    SectionSpec(
        name="blocked_services",
        title="Blocked services",
        description="Globally blocked services and their schedule.",
        strategy="document",
        get_path="/control/blocked_services/get",
        set_path="/control/blocked_services/update",
        set_method="PUT",
        keys=("ids", "schedule"),
    ),
    SectionSpec(
        name="filtering_config",
        title="Filtering",
        description="Whether filtering is on, and how often the lists are refreshed.",
        strategy="document",
        get_path="/control/filtering/status",
        set_path="/control/filtering/config",
        keys=("enabled", "interval"),
    ),
    SectionSpec(
        name="safebrowsing",
        title="Safe browsing",
        description="AdGuard's browsing security module.",
        strategy="toggle",
        get_path="/control/safebrowsing/status",
        enable_path="/control/safebrowsing/enable",
        disable_path="/control/safebrowsing/disable",
    ),
    SectionSpec(
        name="parental",
        title="Parental control",
        description="AdGuard's parental control module.",
        strategy="toggle",
        get_path="/control/parental/status",
        enable_path="/control/parental/enable",
        disable_path="/control/parental/disable",
    ),
    SectionSpec(
        name="safesearch",
        title="Safe search",
        description="Enforced safe search, per search engine.",
        strategy="document",
        get_path="/control/safesearch/status",
        set_path="/control/safesearch/settings",
        set_method="PUT",
    ),
    SectionSpec(
        name="querylog_config",
        title="Query log settings",
        description="Retention, client anonymisation and ignored domains.",
        strategy="document",
        get_path="/control/querylog/config",
        set_path="/control/querylog/config",
        set_method="PUT",
        keys=("enabled", "interval", "anonymize_client_ip", "ignored"),
    ),
    SectionSpec(
        name="stats_config",
        title="Statistics settings",
        description="Statistics retention and ignored domains.",
        strategy="document",
        get_path="/control/stats/config",
        set_path="/control/stats/config",
        set_method="PUT",
        keys=("enabled", "interval", "ignored"),
    ),
)

SPEC_BY_NAME: dict[str, SectionSpec] = {spec.name: spec for spec in SPECS}
SECTION_NAMES: tuple[str, ...] = tuple(spec.name for spec in SPECS)


@dataclass
class SectionState:
    """What a section holds centrally, plus whether it is pushed at all."""

    name: str
    managed: bool = False
    data: dict[str, Any] = field(default_factory=dict)


def push_guard(name: str, data: dict[str, Any]) -> str:
    """Return a reason to skip pushing this section, or "" when it is safe.

    Pushing a TLS document whose private key the API withheld would disable
    encryption on the target rather than replicate it.
    """
    if name != "tls":
        return ""
    if not data.get("enabled"):
        return ""
    has_inline = bool(data.get("certificate_chain")) and bool(data.get("private_key"))
    has_paths = bool(data.get("certificate_path")) and bool(data.get("private_key_path"))
    if has_inline or has_paths:
        return ""
    return (
        "the master did not expose the private key (AdGuard Home never returns a stored "
        "key), so pushing would turn encryption off on the target"
    )
