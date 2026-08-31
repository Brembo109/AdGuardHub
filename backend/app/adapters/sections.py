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

# How a value is presented in the UI. Anything without a field here stays editable
# through the raw document view, so a setting is never unreachable just because it
# has no curated form.
FieldType = Literal["bool", "int", "text", "lines", "select", "pairs", "clients"]


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    type: FieldType
    help: str = ""
    unit: str = ""
    # "select" only: (value, label) pairs.
    options: tuple[tuple[str, str], ...] = ()
    # Heading this field belongs under. Grouping lives here rather than in the
    # page, so a field added below cannot quietly land outside every group.
    group: str = ""


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
    # Read the target's current document and overlay ``keys`` onto it instead of
    # sending them alone. Required where the endpoint replaces the whole object,
    # so the node's own settings survive a push.
    merge_on_push: bool = False
    # Shown on the section at all times, not only when something went wrong.
    notes: str = ""
    # This area is big enough to deserve its own page, so the combined settings
    # list leaves it out and links there instead.
    own_page: bool = False
    # Switching this on can cut the operator off from the node. The UI shows the
    # notes as a warning and asks for confirmation before enabling.
    risky: bool = False
    fields: tuple[FieldSpec, ...] = ()


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
        own_page=True,
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
        fields=(
            FieldSpec("upstream_dns", "Upstream DNS servers", "lines",
                      "One per line, in AdGuard syntax. A line like "
                      "[/example.lan/]192.168.1.1 routes just that domain.",
                      group="Upstream DNS servers"),
            FieldSpec("upstream_mode", "Upstream mode", "select",
                      "How the upstreams above are used for each query.",
                      options=(
                          ("", "Load balance"),
                          ("parallel", "Parallel requests"),
                          ("fastest_addr", "Fastest IP address"),
                      ), group="Upstream DNS servers"),
            FieldSpec("bootstrap_dns", "Bootstrap DNS servers", "lines",
                      "Used to resolve the hostnames of encrypted upstreams. "
                      "Plain IP addresses only — these cannot themselves need DNS.",
                      group="Upstream DNS servers"),
            FieldSpec("fallback_dns", "Fallback DNS servers", "lines",
                      "Used when the upstreams above fail or time out.",
                      group="Upstream DNS servers"),

            FieldSpec("use_private_ptr_resolvers", "Use private reverse DNS resolvers", "bool",
                      "Resolve PTR queries for local addresses with the servers below.",
                      group="Private reverse DNS"),
            FieldSpec("local_ptr_upstreams", "Private reverse DNS servers", "lines",
                      "Left empty, AdGuard uses the addresses your OS is configured with.",
                      group="Private reverse DNS"),
            FieldSpec("private_upstream", "Private DNS upstreams", "lines",
                      group="Private reverse DNS"),
            FieldSpec("resolve_clients", "Resolve client names via rDNS", "bool",
                      "Turns client IPs into hostnames in the query log.",
                      group="Private reverse DNS"),

            FieldSpec("protection_enabled", "Filtering enabled", "bool",
                      "Turning this off stops all filtering on every instance.",
                      group="DNS server configuration"),
            FieldSpec("blocking_mode", "Blocking mode", "select",
                      "What a blocked query is answered with.",
                      options=(
                          ("default", "Default"),
                          ("refused", "REFUSED"),
                          ("nxdomain", "NXDOMAIN"),
                          ("null_ip", "Null IP"),
                          ("custom_ip", "Custom IP"),
                      ), group="DNS server configuration"),
            FieldSpec("blocking_ipv4", "Blocking IPv4", "text",
                      "Only used with the custom IP blocking mode.",
                      group="DNS server configuration"),
            FieldSpec("blocking_ipv6", "Blocking IPv6", "text",
                      "Only used with the custom IP blocking mode.",
                      group="DNS server configuration"),
            FieldSpec("blocked_response_ttl", "Blocked response TTL", "int",
                      "How long clients may cache a blocked answer.",
                      unit="seconds", group="DNS server configuration"),
            FieldSpec("ratelimit", "Rate limit", "int",
                      "Requests per second per client; 0 disables it.",
                      unit="req/s", group="DNS server configuration"),

            FieldSpec("cache_size", "Cache size", "int",
                      unit="bytes", group="DNS cache configuration"),
            FieldSpec("cache_ttl_min", "Minimum cached TTL", "int",
                      "Answers with a shorter TTL are held this long anyway.",
                      unit="seconds", group="DNS cache configuration"),
            FieldSpec("cache_ttl_max", "Maximum cached TTL", "int",
                      unit="seconds", group="DNS cache configuration"),
            FieldSpec("cache_optimistic", "Optimistic caching", "bool",
                      "Serve expired entries while refreshing them in the background.",
                      group="DNS cache configuration"),

            FieldSpec("dnssec_enabled", "Enable DNSSEC", "bool",
                      "Set the DO bit and check the AD bit on answers.", group="DNS options"),
            FieldSpec("disable_ipv6", "Disable IPv6 answers", "bool",
                      "Drop AAAA queries. Only useful on a network without IPv6.",
                      group="DNS options"),
            FieldSpec("edns_cs_enabled", "Enable EDNS client subnet", "bool",
                      "Passes part of the client address to the upstream.",
                      group="DNS options"),
        ),
    ),
    SectionSpec(
        name="clients",
        title="Clients",
        description="Persistent client definitions with their per-client filtering settings.",
        strategy="clients",
        get_path="/control/clients",
        fields=(FieldSpec("clients", "Clients", "clients"),),
    ),
    SectionSpec(
        name="access",
        title="Access control",
        description="Allowed and disallowed clients, and blocked hostnames.",
        strategy="document",
        get_path="/control/access/list",
        set_path="/control/access/set",
        keys=("allowed_clients", "disallowed_clients", "blocked_hosts"),
        fields=(
            FieldSpec("allowed_clients", "Allowed clients", "lines",
                      "When non-empty, only these clients may use the DNS server."),
            FieldSpec("disallowed_clients", "Disallowed clients", "lines"),
            FieldSpec("blocked_hosts", "Blocked hostnames", "lines"),
        ),
    ),
    SectionSpec(
        name="tls",
        title="Encryption (TLS)",
        description="Whether encryption is switched on. Certificates stay per node.",
        strategy="document",
        get_path="/control/tls/status",
        set_path="/control/tls/configure",
        # Only the on/off decision travels: each node terminates TLS itself, with its
        # own certificate and hostname, so copying those between nodes is meaningless.
        keys=("enabled",),
        # /control/tls/configure replaces the whole object, unlike /control/dns_config
        # which merges. Sending "enabled" alone would wipe the target's certificate.
        merge_on_push=True,
        notes=(
            "Install and verify a working certificate on every node before switching this "
            "on. AdGuard Home does not check that a node can actually serve HTTPS: if one "
            "has no valid certificate, enabling encryption can make it unreachable — "
            "including its own web interface, because it redirects to HTTPS. Recovering "
            "then needs shell access to that host to turn TLS off in AdGuardHome.yaml and "
            "restart it. Each node keeps its own certificate; only the on/off state is "
            "replicated."
        ),
        risky=True,
        fields=(FieldSpec("enabled", "Encryption enabled", "bool"),),
    ),
    SectionSpec(
        name="rewrites",
        title="DNS rewrites",
        description="Custom domain-to-answer rewrites.",
        strategy="rewrites",
        get_path="/control/rewrite/list",
        fields=(FieldSpec("items", "Rewrites", "pairs", "Domain to answer with a fixed value."),),
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
        fields=(
            FieldSpec("ids", "Blocked services", "lines",
                      "AdGuard service identifiers, one per line (e.g. tiktok, facebook)."),
        ),
    ),
    SectionSpec(
        name="filtering_config",
        title="Filtering",
        description="Whether filtering is on, and how often the lists are refreshed.",
        strategy="document",
        get_path="/control/filtering/status",
        set_path="/control/filtering/config",
        keys=("enabled", "interval"),
        fields=(
            FieldSpec("enabled", "Use filtering lists", "bool"),
            FieldSpec("interval", "Refresh subscriptions every", "select", options=(
                ("1", "1 hour"),
                ("12", "12 hours"),
                ("24", "1 day"),
                ("72", "3 days"),
                ("168", "7 days"),
            )),
        ),
    ),
    SectionSpec(
        name="safebrowsing",
        title="Safe browsing",
        description="AdGuard's browsing security module.",
        strategy="toggle",
        get_path="/control/safebrowsing/status",
        enable_path="/control/safebrowsing/enable",
        disable_path="/control/safebrowsing/disable",
        fields=(FieldSpec("enabled", "Safe browsing enabled", "bool"),),
    ),
    SectionSpec(
        name="parental",
        title="Parental control",
        description="AdGuard's parental control module.",
        strategy="toggle",
        get_path="/control/parental/status",
        enable_path="/control/parental/enable",
        disable_path="/control/parental/disable",
        fields=(FieldSpec("enabled", "Parental control enabled", "bool"),),
    ),
    SectionSpec(
        name="safesearch",
        title="Safe search",
        description="Enforced safe search, per search engine.",
        strategy="document",
        get_path="/control/safesearch/status",
        set_path="/control/safesearch/settings",
        set_method="PUT",
        fields=(
            FieldSpec("enabled", "Enforce safe search", "bool"),
            FieldSpec("bing", "Bing", "bool"),
            FieldSpec("duckduckgo", "DuckDuckGo", "bool"),
            FieldSpec("google", "Google", "bool"),
            FieldSpec("pixabay", "Pixabay", "bool"),
            FieldSpec("yandex", "Yandex", "bool"),
            FieldSpec("youtube", "YouTube", "bool"),
        ),
    ),
    SectionSpec(
        name="querylog_config",
        title="Query log settings",
        description="Retention, client anonymisation and ignored domains.",
        strategy="document",
        get_path="/control/querylog/config",
        # AdGuard reads and writes this area on different paths: PUT to the read
        # path answers 405 "only method GET is allowed".
        set_path="/control/querylog/config/update",
        set_method="PUT",
        keys=("enabled", "interval", "anonymize_client_ip", "ignored"),
        fields=(
            FieldSpec("enabled", "Log queries", "bool"),
            FieldSpec("anonymize_client_ip", "Anonymise client IPs", "bool"),
            FieldSpec("ignored", "Ignored domains", "lines"),
            # `interval` is deliberately absent: its unit changed between AdGuard
            # versions, so it stays in the raw view rather than being mislabelled.
        ),
    ),
    SectionSpec(
        name="stats_config",
        title="Statistics settings",
        description="Statistics retention and ignored domains.",
        strategy="document",
        get_path="/control/stats/config",
        # As for the query log: the write lives on its own /update path.
        set_path="/control/stats/config/update",
        set_method="PUT",
        keys=("enabled", "interval", "ignored"),
        fields=(
            FieldSpec("enabled", "Keep statistics", "bool"),
            FieldSpec("ignored", "Ignored domains", "lines"),
        ),
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
