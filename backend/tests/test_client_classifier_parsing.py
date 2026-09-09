"""Browser / OS / device parsing.

Ordering is the whole difficulty: every Edge UA contains "chrome", and every
Chrome UA contains "safari", so a naive substring check reports the wrong
browser for most of the internet.
"""
import pytest

from app.services.client_classifier import parse_browser, parse_os, parse_device_type

CHROME_WIN = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
EDGE_WIN = CHROME_WIN + " Edg/120.0.0.0"
SAFARI_IPHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                 "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
SAFARI_IPAD = ("Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
               "(KHTML, like Gecko) Version/17.0 Safari/604.1")
FIREFOX_LINUX = "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0"
CHROME_ANDROID = ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")
GOOGLEBOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"


class TestBrowser:
    @pytest.mark.parametrize("ua,expected", [
        (EDGE_WIN, "Edge"),          # must beat both chrome and safari
        (CHROME_WIN, "Chrome"),      # must beat safari
        (SAFARI_IPHONE, "Safari"),
        (FIREFOX_LINUX, "Firefox"),
        (CHROME_ANDROID, "Chrome"),
    ])
    def test_identifies_browser(self, ua, expected):
        assert parse_browser(ua) == expected

    def test_bots_are_named_not_counted_as_browsers(self):
        assert parse_browser(GOOGLEBOT) == "Googlebot"
        assert parse_browser("curl/8.4.0") == "Bot"

    def test_missing_user_agent(self):
        assert parse_browser(None) == "Unknown"
        assert parse_browser("") == "Unknown"


class TestOperatingSystem:
    @pytest.mark.parametrize("ua,expected", [
        (CHROME_WIN, "Windows 10/11"),
        (SAFARI_IPHONE, "iOS"),
        (SAFARI_IPAD, "iPadOS"),
        (FIREFOX_LINUX, "Linux"),
        (CHROME_ANDROID, "Android"),
    ])
    def test_identifies_os(self, ua, expected):
        assert parse_os(ua) == expected

    def test_macos(self):
        ua = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        assert parse_os(ua) == "macOS"

    def test_missing_user_agent(self):
        assert parse_os(None) == "Unknown"


class TestDeviceType:
    @pytest.mark.parametrize("ua,expected", [
        (CHROME_WIN, "Desktop"),
        (FIREFOX_LINUX, "Desktop"),
        (SAFARI_IPHONE, "Mobile"),
        (CHROME_ANDROID, "Mobile"),
        (SAFARI_IPAD, "Tablet"),     # iPad has no "mobile" token
        (GOOGLEBOT, "Bot"),
    ])
    def test_identifies_device(self, ua, expected):
        assert parse_device_type(ua) == expected

    def test_no_user_agent_is_treated_as_automation(self):
        assert parse_device_type(None) == "Bot"
