"""Who may pass an auth wall through an OAuth provider (Google, GitHub).

A wall's allow-list is a set of exact email addresses plus a set of email
domains. Signing in with Google or GitHub only proves who someone is; without
an allow-list anyone with an account at that provider gets through. An empty
allow-list keeps that behaviour (so upgrading never locks anyone out) and the
admin UI warns about it.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

# Provider types that admit outside accounts (local users and LDAP are managed lists already).
OAUTH_PROVIDER_TYPES = frozenset({"google", "github", "azure_ad", "oidc"})

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def normalize_email(value: str) -> str:
    value = (value or "").strip().lower()
    if not _EMAIL_RE.match(value):
        raise ValueError(f"Not an email address: {value!r}")
    return value


def normalize_domain(value: str) -> str:
    value = (value or "").strip().lower().lstrip("@")
    if not _DOMAIN_RE.match(value):
        raise ValueError(f"Not a domain name: {value!r}")
    return value


def clean_list(values: Optional[Iterable[str]], normalize) -> list[str]:
    """Normalise, drop blanks and duplicates, keep order. Raises ValueError on a bad entry."""
    out: list[str] = []
    for raw in values or []:
        if raw is None or not str(raw).strip():
            continue
        item = normalize(str(raw))
        if item not in out:
            out.append(item)
    return out


def has_allow_list(wall) -> bool:
    return bool(getattr(wall, "allowed_emails", None) or getattr(wall, "allowed_email_domains", None))


def is_email_allowed(wall, email: Optional[str]) -> bool:
    """True if this (provider-verified) email may pass the wall.

    No allow-list: everyone the provider vouches for (previous behaviour).
    With one: the exact address, or an address whose domain is listed exactly
    (a listed `example.com` does not admit `sub.example.com`).
    """
    if not has_allow_list(wall):
        return True
    if not email:
        return False
    try:
        email = normalize_email(email)
    except ValueError:
        return False
    emails = {e.lower() for e in (wall.allowed_emails or [])}
    domains = {d.lower() for d in (wall.allowed_email_domains or [])}
    if email in emails:
        return True
    return email.rsplit("@", 1)[1] in domains


def open_to_any_account(wall, providers: Optional[Iterable] = None) -> bool:
    """True when an enabled OAuth provider would admit any account (no allow-list)."""
    if has_allow_list(wall):
        return False
    providers = providers if providers is not None else (getattr(wall, "auth_providers", None) or [])
    return any(
        getattr(p, "enabled", False) and getattr(p, "provider_type", None) in OAUTH_PROVIDER_TYPES
        for p in providers
    )
