"""The Basic Auth credential cache.

bcrypt costs roughly 300 ms per check here. That is the right price for a login
form and the wrong one for an API a phone polls, because Basic Auth presents the
password on every single request. This cache is what makes the difference, so the
properties it has to hold are worth pinning down.
"""

from __future__ import annotations

from app.security import VerifiedCredentials, hash_password, verify_password


def test_a_remembered_pair_is_recognised() -> None:
    cache = VerifiedCredentials()
    assert cache.check("admin", "secret") is False
    cache.remember("admin", "secret")
    assert cache.check("admin", "secret") is True


def test_only_the_exact_pair_matches() -> None:
    cache = VerifiedCredentials()
    cache.remember("admin", "secret")
    assert cache.check("admin", "secrez") is False
    assert cache.check("admis", "secret") is False


def test_an_entry_expires() -> None:
    cache = VerifiedCredentials(ttl=60.0)
    cache.remember("admin", "secret", now=1_000.0)
    assert cache.check("admin", "secret", now=1_059.0) is True
    assert cache.check("admin", "secret", now=1_060.0) is False


def test_the_plaintext_password_is_never_held() -> None:
    """Whatever is in memory here, a heap dump must not hand over the password."""
    cache = VerifiedCredentials()
    cache.remember("admin", "hunter2-in-the-clear")
    stored = "".join(cache._seen)  # noqa: SLF001 — the point is what is in there
    assert "hunter2-in-the-clear" not in stored
    assert "admin" not in stored


def test_a_changed_password_invalidates_everything() -> None:
    cache = VerifiedCredentials()
    cache.remember("admin", "secret")
    cache.forget_all()
    assert cache.check("admin", "secret") is False


def test_a_wrong_password_is_still_a_real_check() -> None:
    """The cache holds successes only, so it cannot be filled from outside.

    If failures were cached too, anyone could grow this without limit by trying
    passwords — and each wrong guess would get cheaper rather than staying at the
    full bcrypt cost that makes guessing expensive.
    """
    stored = hash_password("secret")
    cache = VerifiedCredentials()

    assert verify_password("wrong", stored) is False
    assert cache.check("admin", "wrong") is False
    assert cache._seen == {}  # noqa: SLF001
