"""Helpers for the central, AdGuard-native rule model (spec §5)."""

from __future__ import annotations

from ..models import RuleKind

COMMENT_PREFIXES = ("!", "#")


def is_comment(text: str) -> bool:
    return text.lstrip().startswith(COMMENT_PREFIXES)


def classify(text: str) -> RuleKind:
    """AdGuard marks exception (allow) rules with a leading ``@@``."""
    return RuleKind.allow if text.lstrip().startswith("@@") else RuleKind.block


def normalise(text: str) -> str:
    return text.strip()


def allow_rule_for_domain(domain: str) -> str:
    """The rule AdGuard itself generates for the query log's "Unblock" action."""
    return f"@@||{domain.strip().lower().rstrip('.')}^"


def block_rule_for_domain(domain: str) -> str:
    return f"||{domain.strip().lower().rstrip('.')}^"
