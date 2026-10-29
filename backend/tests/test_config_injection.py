"""Values that reach the generated nginx config, and the routes that set them.

Every field here is written into a server block as a bare token (or in double
quotes). A `;`, `{`, `}`, quote or newline would end the directive and let the
rest of the value add directives of its own, Lua included; `nginx -t` checks
syntax only, so it wouldn't notice.
"""

import os
import stat
import sys

import pytest
from app.models.setting import Setting
from app.schemas.access_list import _check_redirect_url
from app.schemas.certificate import CertificateLetsEncrypt
from app.schemas.proxy_host import (
    ProxyHostCreate,
    ProxyHostUpdate,
    ProxyLocationCreate,
    ProxyLocationUpdate,
)
from pydantic import ValidationError

LUA = "rewrite_by_lua_block { ngx.say(io.popen('id'):read('*a')) }"


def _location(**overrides):
    data = {"path": "/api", "forward_host": "10.0.0.5", "forward_port": 8080}
    data.update(overrides)
    return ProxyLocationCreate(**data)


def _host(**overrides):
    data = {"domain_names": ["app.example.com"], "forward_host": "10.0.0.5", "forward_port": 8080}
    data.update(overrides)
    return ProxyHostCreate(**data)


class TestLocationFields:
    @pytest.mark.parametrize(
        ("path", "match_type"),
        [
            ("/api", "prefix"),
            ("/exact", "exact"),
            (r"\.php$", "regex"),
            ("^/(v1|v2)/", "regex_case_insensitive"),
            ("/static/~user/a-b_c.d", "prefix"),
        ],
    )
    def test_ordinary_paths(self, path, match_type):
        assert _location(path=path, match_type=match_type).path == path

    @pytest.mark.parametrize(
        "path",
        [
            f"/x {{ {LUA} }} location /y",
            "/a b",
            "/x;",
            '/x"',
            "/x#comment",
            "/x\nlocation /y",
            "ends-with\\",
        ],
    )
    def test_injection_in_path_refused(self, path):
        with pytest.raises(ValidationError, match="Location path"):
            _location(path=path, match_type="regex")

    def test_prefix_path_must_start_with_slash(self):
        with pytest.raises(ValidationError, match="must start with '/'"):
            _location(path="api", match_type="prefix")

    def test_forward_host_checked_like_a_host(self):
        with pytest.raises(ValidationError, match="not a valid"):
            _location(forward_host=f"a:1; {LUA} #")

    def test_update_has_the_same_checks(self):
        for bad in (
            {"path": "/x { }"},
            {"forward_host": "a; return 302 //evil"},
            {"forward_scheme": "http://a;#"},
            {"forward_port": 70000},
            {"match_type": "anything"},
            {"cache_valid": "10m; " + LUA},
        ):
            with pytest.raises(ValidationError):
                ProxyLocationUpdate(**bad)
        assert ProxyLocationUpdate(path="/ok", forward_host="backend.local").path == "/ok"

    def test_headers(self):
        loc = _location(
            custom_headers={"X-Frame-Options": "DENY", "Content-Security-Policy": "default-src 'self'"},
            proxy_headers={"Host": "$host", "X-Real-IP": "$remote_addr"},
            hide_headers=["X-Powered-By"],
        )
        assert loc.proxy_headers["Host"] == "$host"
        for bad in (
            {"custom_headers": {"X-A": 'b"; ' + LUA + " #"}},
            {"custom_headers": {"X; " + LUA: "v"}},
            {"proxy_headers": {"Host": "$host; " + LUA}},
            {"proxy_headers": {"Host": "a b"}},
            {"hide_headers": ["X-A; " + LUA]},
        ):
            with pytest.raises(ValidationError, match=r"[Hh]eader"):
                _location(**bad)

    def test_cache_fields(self):
        loc = _location(cache_valid="200 302 10m", cache_bypass="$http_cache_control $cookie_nocache")
        assert loc.cache_valid == "200 302 10m"
        assert _location(cache_valid="any 1h").cache_valid == "any 1h"
        assert _location(cache_valid="").cache_valid is None
        with pytest.raises(ValidationError, match="Cache valid"):
            _location(cache_valid="10m; " + LUA + " #")
        with pytest.raises(ValidationError, match="Cache bypass"):
            _location(cache_bypass="$x; " + LUA)


class TestHostFields:
    def test_defaults_pass(self):
        host = _host()
        assert (host.client_max_body_size, host.proxy_buffer_size, host.proxy_buffers) == ("100m", "4k", "8 4k")

    @pytest.mark.parametrize("value", ["0", "1G", "512k", " 50M "])
    def test_sizes(self, value):
        assert _host(client_max_body_size=value).client_max_body_size == value.strip()

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("client_max_body_size", "1m;return 302 //e.co"),
            ("proxy_buffer_size", "4k; " + LUA),
            ("proxy_buffers", "8 4k;location /p{}"),
            ("cache_valid", "10m;location /p{" + LUA + "}#"),
            ("cache_bypass", "$a;" + LUA),
            ("cdn_provider", "cloudflare\nlocation /p {}"),
        ],
    )
    def test_injection_refused_on_create_and_update(self, field, value):
        with pytest.raises(ValidationError):
            _host(**{field: value})
        with pytest.raises(ValidationError):
            ProxyHostUpdate(**{field: value})

    def test_error_pages(self):
        pages = {"404": "/404.html", "502": "https://status.example.com/down", "500": "@fallback"}
        assert _host(custom_error_pages=pages).custom_error_pages == pages
        for bad in (
            {"404": "/e; location /p { " + LUA + " } #"},
            {"4x4": "/e.html"},
            {"404 ; x": "/e.html"},
            {"404": "https://a/$http_x_to"},
        ):
            with pytest.raises(ValidationError, match="Error page"):
                _host(custom_error_pages=bad)

    def test_cdn_providers(self):
        for provider in ("none", "cloudflare", "imperva", "generic"):
            assert _host(cdn_provider=provider).cdn_provider == provider


class TestCertificateDomains:
    def test_ordinary(self):
        cert = CertificateLetsEncrypt(name="c", domain_names=["example.com", "www.example.com"], email="a@b.co")
        assert cert.domain_names == ["example.com", "www.example.com"]

    @pytest.mark.parametrize("domain", ["../../etc", "--config-dir=/tmp", "a b.com", "x.com/../../y", ""])
    def test_bad_names_refused(self, domain):
        # They go to certbot as arguments and into /etc/letsencrypt/live/<name>/ paths.
        with pytest.raises(ValidationError, match="Invalid domain name"):
            CertificateLetsEncrypt(name="c", domain_names=[domain], email="a@b.co")


class TestRedirectUrl:
    def test_plain_urls(self):
        assert _check_redirect_url("https://example.com/path?x=1#top") == "https://example.com/path?x=1#top"
        assert _check_redirect_url("  ") is None

    @pytest.mark.parametrize(
        "url",
        ["https://a; } location /p { } #", "https://$http_x_to", "https://a\\b", "javascript:alert(1)", "https://a b"],
    )
    def test_refused(self, url):
        with pytest.raises(ValueError, match="Redirect URL"):
            _check_redirect_url(url)


class TestDefaultSite:
    async def test_route_refuses_unsafe_url(self, client, auth_headers):
        r = await client.put(
            "/api/settings/default-site",
            headers=auth_headers,
            json={"behavior": "redirect", "redirect_url": "https://a; } location /p { } #"},
        )
        assert r.status_code == 422

    async def test_generic_setting_route_refuses_unsafe_url(self, client, auth_headers):
        r = await client.put(
            "/api/settings/default_site_redirect_url",
            headers=auth_headers,
            json={"value": "https://a; } location /p { } #"},
        )
        assert r.status_code == 422
        r = await client.put(
            "/api/settings/",
            headers=auth_headers,
            json={"settings": {"default_site_redirect_url": "https://$http_host"}},
        )
        assert r.status_code == 422

    async def test_generator_never_writes_an_unsafe_stored_url(self, db_session):
        from app.services.openresty_service import generate_default_site_config

        db_session.add(Setting(key="default_site_behavior", value="redirect"))
        db_session.add(Setting(key="default_site_redirect_url", value="https://a; } location /p { } #"))
        await db_session.commit()
        config = await generate_default_site_config(db_session)
        assert "location /p" not in config
        assert "return 301" not in config


class TestTrustedProxyRanges:
    async def test_unknown_provider_keys_dropped(self, db_session):
        import json

        from app.services.trusted_proxy_service import SETTING_KEY, get_ranges

        db_session.add(
            Setting(
                key=SETTING_KEY,
                value=json.dumps({"cloudflare": ["1.2.3.0/24"], "x\nlocation /p {}": ["5.6.7.0/24"]}),
            )
        )
        await db_session.commit()
        ranges = await get_ranges(db_session)
        assert ranges["cloudflare"] == ["1.2.3.0/24"]
        assert not any("\n" in k for k in ranges)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
class TestPrivateFiles:
    async def test_private_file_is_owner_only_from_the_start(self, tmp_path):
        from app.core.files import write_text

        path = tmp_path / "key.pem"
        path.write_text("old")
        os.chmod(path, 0o644)
        await write_text(str(path), "secret", private=True)
        assert path.read_text() == "secret"
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
