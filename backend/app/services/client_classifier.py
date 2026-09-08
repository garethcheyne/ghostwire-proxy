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
