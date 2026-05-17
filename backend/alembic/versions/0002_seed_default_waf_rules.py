"""seed default WAF rules

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-17

Seeds the default WAF rules into the `waf_rules` table so they are visible
and editable in the UI. Idempotent: only inserts rules whose `id` is not
already present (so re-running won't duplicate, and users can safely delete
rules they don't want without them coming back).

These rules used to live as a hardcoded fallback in proxy/lua/init.lua;
that fallback has been removed — the DB is now the single source of truth.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


# (stable_id, name, category, pattern, severity, action)
# stable_id is stored as the row id so re-seeding is idempotent across installs.
DEFAULT_RULES: list[tuple[str, str, str, str, str, str]] = [
    # SQLi
    ("default-sqli-1",  "SQLi - OR/AND injection", "sqli", r"('|\")(\s)*(or|and)(\s)+(1|true|'|\")", "high",     "block"),
    ("default-sqli-2",  "SQLi - UNION SELECT",     "sqli", r"union(\s)+select",                       "high",     "block"),
    ("default-sqli-3",  "SQLi - SELECT FROM",      "sqli", r"select(\s)+.*from",                      "high",     "block"),
    ("default-sqli-4",  "SQLi - INSERT INTO",      "sqli", r"insert(\s)+into",                        "high",     "block"),
    ("default-sqli-5",  "SQLi - DELETE FROM",      "sqli", r"delete(\s)+from",                        "high",     "block"),
    ("default-sqli-6",  "SQLi - DROP TABLE/DB",    "sqli", r"drop(\s)+(table|database)",              "critical", "block"),
    ("default-sqli-7",  "SQLi - EXEC call",        "sqli", r"exec(\s)*\(",                            "high",     "block"),
    ("default-sqli-8",  "SQLi - EXECUTE call",     "sqli", r"execute(\s)*\(",                         "high",     "block"),
    ("default-sqli-9",  "SQLi - Hex encoding",     "sqli", r"0x[0-9a-fA-F]{8,}",                      "medium",   "log"),
    ("default-sqli-10", "SQLi - CHAR function",    "sqli", r"char\([0-9]+\)",                         "high",     "block"),
    # XSS
    ("default-xss-1", "XSS - Script tag",     "xss", r"<script[^>]*>",
        "high", "block"),
    ("default-xss-2", "XSS - javascript: URI", "xss", r"javascript:",
        "high", "block"),
    ("default-xss-3", "XSS - Event handler",  "xss",
        r"\bon(load|error|click|mouseover|focus|blur|submit|change|input|keyup|keydown|mouseout|mouseenter|mouseleave|contextmenu|dblclick|unload|beforeunload|resize|scroll|abort|copy|cut|paste|drag|drop)\s*=",
        "high", "block"),
    ("default-xss-4", "XSS - iframe",         "xss", r"<iframe",         "high",   "block"),
    ("default-xss-5", "XSS - object tag",     "xss", r"<object",         "medium", "block"),
    ("default-xss-6", "XSS - embed tag",      "xss", r"<embed",          "medium", "block"),
    ("default-xss-7", "XSS - CSS expression", "xss", r"expression\s*\(", "high",   "block"),
    ("default-xss-8", "XSS - vbscript: URI",  "xss", r"vbscript:",       "high",   "block"),
    # Path traversal
    ("default-pt-1", "Path Traversal - forward slash", "path_traversal", r"\.\./",   "high", "block"),
    ("default-pt-2", "Path Traversal - backslash",     "path_traversal", r"\.\.\\",  "high", "block"),
    # RCE
    ("default-rce-1", "RCE - Semicolon command",   "rce", r";\s*(ls|cat|wget|curl|bash|sh|nc|netcat)",  "critical", "block"),
    ("default-rce-2", "RCE - Pipe command",        "rce", r"\|\s*(ls|cat|wget|curl|bash|sh|nc|netcat)", "critical", "block"),
    ("default-rce-3", "RCE - Backtick execution",  "rce", r"`[^`]*`",                                    "critical", "block"),
    ("default-rce-4", "RCE - Subshell execution",  "rce", r"\$\([^)]*\)",                               "critical", "block"),
]

# User-Agent scanner signatures (plain substring match, category=scanner)
SCANNER_SIGS: list[str] = [
    "nikto", "sqlmap", "nmap", "masscan", "dirbuster",
    "gobuster", "wpscan", "acunetix", "nessus",
]


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(timezone.utc)

    # Get existing rule ids so we never overwrite or duplicate
    existing_ids = {
        row[0] for row in bind.execute(sa.text("SELECT id FROM waf_rules")).fetchall()
    }

    insert_sql = sa.text(
        """
        INSERT INTO waf_rules
            (id, rule_set_id, proxy_host_id, name, description, category, pattern,
             severity, action, enabled, is_lua, preset_id, created_at)
        VALUES
            (:id, NULL, NULL, :name, :description, :category, :pattern,
             :severity, :action, TRUE, TRUE, NULL, :created_at)
        """
    )

    for stable_id, name, category, pattern, severity, action in DEFAULT_RULES:
        if stable_id in existing_ids:
            continue
        bind.execute(
            insert_sql,
            {
                "id": stable_id,
                "name": name,
                "description": "Default rule (seeded). Edit or disable from the WAF page.",
                "category": category,
                "pattern": pattern,
                "severity": severity,
                "action": action,
                "created_at": now,
            },
        )

    for sig in SCANNER_SIGS:
        stable_id = f"default-scanner-{sig}"
        if stable_id in existing_ids:
            continue
        bind.execute(
            insert_sql,
            {
                "id": stable_id,
                "name": f"Scanner - {sig}",
                "description": "Default scanner signature (seeded). Plain substring match on User-Agent.",
                "category": "scanner",
                "pattern": sig,
                "severity": "medium",
                "action": "block",
                "created_at": now,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    seeded_ids = (
        [r[0] for r in DEFAULT_RULES]
        + [f"default-scanner-{sig}" for sig in SCANNER_SIGS]
    )
    bind.execute(
        sa.text("DELETE FROM waf_rules WHERE id = ANY(:ids)"),
        {"ids": seeded_ids},
    )
