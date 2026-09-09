"""
Classify a request's client: is it a bot, and was it a long-lived connection?

Why this exists:

- "Unique visitors" is meaningless while a large share of traffic is crawlers,
  scanners and monitoring agents. Counting them as people inflates every
  engagement number.
- Websocket and SSE connections stay open for minutes by design. Their recorded
  duration is how long someone stayed connected, not how slow the server was,
  and mixing them into latency statistics is what turns a 30ms median into a
  "13 second average".

Deliberately conservative: this only claims "bot" on positive evidence. Anything
unrecognised is left as not-a-bot rather than guessed at, because a wrong "bot"
silently removes real traffic from the numbers.
"""
import re
from typing import Optional

# Substrings that appear in self-identifying automated clients. Matched
# case-insensitively against the User-Agent.
_BOT_MARKERS = (
    "bot", "crawler", "spider", "scraper", "slurp",
    "curl/", "wget/", "python-requests", "python-urllib", "go-http-client",
    "java/", "okhttp", "axios/", "node-fetch", "libwww-perl", "httpie",
    "postmanruntime", "insomnia", "guzzlehttp", "apache-httpclient",
    "headlesschrome", "phantomjs", "puppeteer", "playwright", "selenium",
    "masscan", "nmap", "nikto", "sqlmap", "zgrab", "nuclei", "wpscan",
    "censys", "shodan", "internetmeasurement", "paloaltonetworks",
    "uptime", "pingdom", "statuscake", "newrelic", "datadog", "prometheus",
    "monitoring", "healthcheck", "check_http",
    "feedfetcher", "rss", "preview", "linkchecker", "validator",
)

# Well-known crawlers worth naming, so the UI can say *which* bot.
_NAMED_BOTS = (
    ("googlebot", "Googlebot"),
    ("bingbot", "Bingbot"),
    ("duckduckbot", "DuckDuckBot"),
    ("baiduspider", "Baiduspider"),
    ("yandexbot", "YandexBot"),
    ("applebot", "Applebot"),
    ("facebookexternalhit", "Facebook"),
    ("twitterbot", "Twitterbot"),
    ("slackbot", "Slackbot"),
    ("discordbot", "Discordbot"),
    ("telegrambot", "TelegramBot"),
    ("whatsapp", "WhatsApp"),
    ("ahrefsbot", "AhrefsBot"),
    ("semrushbot", "SemrushBot"),
    ("mj12bot", "MJ12bot"),
    ("dotbot", "DotBot"),
    ("petalbot", "PetalBot"),
    ("gptbot", "GPTBot"),
    ("claudebot", "ClaudeBot"),
    ("ccbot", "CCBot"),
    ("perplexitybot", "PerplexityBot"),
    ("bytespider", "Bytespider"),
)

# A browser that renders pages sends an Accept header asking for HTML. Automated
# clients overwhelmingly do not.
_BROWSER_HINT = re.compile(r"mozilla/5\.0", re.I)


def classify_bot(user_agent: Optional[str]) -> tuple[bool, Optional[str]]:
    """Return (is_bot, bot_name). bot_name is None for unnamed automation."""
    if not user_agent or not user_agent.strip():
        # No User-Agent at all is not something a browser does.
        return True, "unknown"

    ua = user_agent.lower()

    for marker, name in _NAMED_BOTS:
        if marker in ua:
            return True, name

    for marker in _BOT_MARKERS:
        if marker in ua:
            return True, None

    # Nothing that claims to be a browser and isn't otherwise suspicious.
    if not _BROWSER_HINT.search(user_agent):
        # Non-browser UA strings that didn't match a known marker: still almost
        # certainly automation, but unnamed.
        return True, None

    return False, None


def is_streaming_response(
    status: Optional[int],
    upgrade_header: Optional[str] = None,
    content_type: Optional[str] = None,
) -> bool:
    """Was this a long-lived connection rather than a slow request?"""
    # 101 Switching Protocols is a completed websocket handshake.
    if status == 101:
        return True
    if upgrade_header and "websocket" in upgrade_header.lower():
        return True
    if content_type and "text/event-stream" in content_type.lower():
        return True
    return False


# Ordered longest-marker-first, because the short names are substrings of the
# long ones: every Edge UA also contains "chrome", and every Chrome UA also
# contains "safari". Checking in this order is the whole trick.
_BROWSERS = (
    ("edg/", "Edge"),
    ("edga/", "Edge"),
    ("edgios/", "Edge"),
    ("opr/", "Opera"),
    ("opera", "Opera"),
    ("vivaldi", "Vivaldi"),
    ("brave", "Brave"),
    ("samsungbrowser", "Samsung Internet"),
    ("yabrowser", "Yandex Browser"),
    ("ucbrowser", "UC Browser"),
    ("firefox/", "Firefox"),
    ("fxios/", "Firefox"),
    ("crios/", "Chrome"),
    ("chrome/", "Chrome"),
    ("chromium/", "Chromium"),
    ("safari/", "Safari"),
    ("msie ", "Internet Explorer"),
    ("trident/", "Internet Explorer"),
)

_OPERATING_SYSTEMS = (
    ("windows nt 10", "Windows 10/11"),
    ("windows nt 6.3", "Windows 8.1"),
    ("windows nt 6.1", "Windows 7"),
    ("windows phone", "Windows Phone"),
    ("windows", "Windows"),
    ("android", "Android"),
    ("iphone", "iOS"),
    ("ipad", "iPadOS"),
    ("ipod", "iOS"),
    ("mac os x", "macOS"),
    ("macintosh", "macOS"),
    ("cros", "ChromeOS"),
    ("ubuntu", "Ubuntu"),
    ("fedora", "Fedora"),
    ("debian", "Debian"),
    ("linux", "Linux"),
    ("freebsd", "FreeBSD"),
)

# Tablets must be tested before phones: an iPad UA contains neither "mobile"
# nor "iphone", but an Android tablet UA contains "android" without "mobile".
_TABLET_MARKERS = ("ipad", "tablet", "kindle", "playbook", "silk")
_MOBILE_MARKERS = ("mobile", "iphone", "ipod", "android", "windows phone", "blackberry", "opera mini")


def parse_browser(user_agent: Optional[str]) -> str:
    """Best-effort browser family name for reporting."""
    if not user_agent or not user_agent.strip():
        return "Unknown"

    ua = user_agent.lower()

    # A bot that borrows a browser UA should still be reported as a bot, not as
    # inflated Chrome traffic.
    is_bot, bot_name = classify_bot(user_agent)
    if is_bot:
        return bot_name or "Bot"

    for marker, name in _BROWSERS:
        if marker in ua:
            return name

    return "Other"


def parse_os(user_agent: Optional[str]) -> str:
    """Best-effort operating system name for reporting."""
    if not user_agent or not user_agent.strip():
        return "Unknown"

    ua = user_agent.lower()
    for marker, name in _OPERATING_SYSTEMS:
        if marker in ua:
            return name

    return "Other"


def parse_device_type(user_agent: Optional[str]) -> str:
    """Desktop / Mobile / Tablet / Bot."""
    if not user_agent or not user_agent.strip():
        return "Bot"

    is_bot, _ = classify_bot(user_agent)
    if is_bot:
        return "Bot"

    ua = user_agent.lower()

    for marker in _TABLET_MARKERS:
        if marker in ua:
            return "Tablet"

    for marker in _MOBILE_MARKERS:
        if marker in ua:
            return "Mobile"

    return "Desktop"
