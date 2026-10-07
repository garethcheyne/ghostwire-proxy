"""Privileged routes need an admin, and inputs that end up in nginx config or a psql
session are validated."""

import pytest

from app.services.backup_service import _check_plain_sql_dump


class TestAdminOnly:
    @pytest.mark.parametrize(
        "method,path",
        [
            ("get", "/api/backups/"),
            ("post", "/api/backups/restore"),
            ("get", "/api/backups/settings/current"),
            ("post", "/api/system/kill-switch"),
            ("post", "/api/system/retention-cleanup"),
            ("post", "/api/updates/app"),
            ("put", "/api/updates/settings"),
            ("put", "/api/reports/smtp"),
            ("post", "/api/presets/x/apply"),
            ("get", "/api/containers/security/anything"),
            ("delete", "/api/traffic"),
        ],
    )
    async def test_regular_user_is_refused(self, client, user_auth_headers, method, path):
        r = await getattr(client, method)(path, headers=user_auth_headers, **({"json": {}} if method in ("post", "put") else {}))
        assert r.status_code == 403, (method, path, r.status_code)


class TestKillSwitchUrl:
    async def test_config_injection_rejected(self, client, auth_headers):
        r = await client.post(
            "/api/system/kill-switch",
            headers=auth_headers,
            json={"active": True, "mode": "redirect", "redirect_url": "https://x; } location /p { return 200; }"},
        )
        assert r.status_code == 422


class TestPlainSqlDump:
    def test_shell_escape_refused(self, tmp_path):
        p = tmp_path / "d.sql"
        p.write_text("SET x = 1;\n\\! touch /tmp/pwned\n")
        with pytest.raises(ValueError):
            _check_plain_sql_dump(str(p))

    def test_pg_dump_output_allowed(self, tmp_path):
        p = tmp_path / "d.sql"
        p.write_text(
            "\\restrict abc123\nSET x = 1;\n"
            "COPY public.t (a, b) FROM stdin;\n\\N\tvalue\n\\!\tnot a command inside COPY data\n\\.\n"
            "\\unrestrict abc123\n"
        )
        _check_plain_sql_dump(str(p))
