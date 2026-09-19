"""Render a host report as an email.

Kept separate from the report data so the numbers have exactly one source: the
scheduled email and the on-screen report are the same `build_host_report`
output, formatted differently.

Deliberately table-based, inline-styled HTML — that is what survives Outlook,
Gmail and Apple Mail. No external CSS, no web fonts, no images.
"""
from typing import Optional

BRAND = "#0ea5e9"
INK = "#0f172a"
MUTED = "#64748b"
LINE = "#e2e8f0"


def _bytes_human(value: Optional[int]) -> str:
    n = float(value or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} PB"


def _num(value) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "—"


def _ms(value) -> str:
    """Format a latency. Tolerates str/Decimal as well as float, so a report
    that has been through a JSON round-trip still renders."""
    if value is None:
        return "—"
    try:
        return f"{float(value):,.0f} ms"
    except (TypeError, ValueError):
        return str(value)


def _change(value: Optional[float]) -> str:
    if value is None:
        return ""
    arrow = "▲" if value >= 0 else "▼"
    colour = "#dc2626" if value >= 0 else "#16a34a"
    return f"<span style='color:{colour};font-size:12px'> {arrow} {abs(value):.1f}%</span>"


def _escape(text) -> str:
    return (
        str(text if text is not None else "")
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def _stat(label: str, value: str, extra: str = "") -> str:
    return (
        f"<td style='padding:12px 16px;border:1px solid {LINE};border-radius:8px;"
        f"background:#f8fafc'>"
        f"<div style='font-size:12px;color:{MUTED};text-transform:uppercase;"
        f"letter-spacing:.04em'>{label}</div>"
        f"<div style='font-size:22px;font-weight:600;color:{INK};margin-top:4px'>"
        f"{value}{extra}</div></td>"
    )


def _section(title: str, body: str) -> str:
    return (
        f"<h3 style='font:600 16px sans-serif;color:{INK};margin:28px 0 10px;"
        f"padding-bottom:6px;border-bottom:2px solid {LINE}'>{title}</h3>{body}"
    )


def _table(headers: list[str], rows: list[list[str]], aligns: Optional[list[str]] = None) -> str:
    if not rows:
        return f"<p style='font:14px sans-serif;color:{MUTED};margin:4px 0'>No data for this period.</p>"

    aligns = aligns or ["left"] * len(headers)
    head = "".join(
        f"<th style='text-align:{a};padding:6px 10px;font:600 12px sans-serif;"
        f"color:{MUTED};text-transform:uppercase;letter-spacing:.04em;"
        f"border-bottom:1px solid {LINE}'>{h}</th>"
        for h, a in zip(headers, aligns)
    )
    body = "".join(
        "<tr>" + "".join(
            f"<td style='text-align:{a};padding:6px 10px;font:14px sans-serif;"
            f"color:{INK};border-bottom:1px solid #f1f5f9'>{c}</td>"
            for c, a in zip(row, aligns)
        ) + "</tr>"
        for row in rows
    )
    return (
        f"<table style='width:100%;border-collapse:collapse;margin:4px 0 8px'>"
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
    )


def render_report_email(report: dict, top_n: int = 10) -> tuple[str, str, str]:
    """Return (subject, text_body, html_body)."""
    host = report.get("host", {})
    meta = report.get("meta", {})
    ov = report.get("overview", {}) or {}
    sec = report.get("security", {}) or {}
    life = report.get("lifetime", {}) or {}
    paths = report.get("paths", {}) or {}
    clients = report.get("clients", {}) or {}
    geo = report.get("geography", {}) or {}
    refs = report.get("referrers", {}) or {}

    domain = host.get("primary_domain", "all hosts")
    period = meta.get("period", "")
    subject = f"Ghostwire Proxy — {domain} traffic report ({period})"

    # ---- plain text fallback -------------------------------------------------
    text = "\n".join([
        f"{domain} — traffic report ({period})",
        f"Generated {meta.get('generated_at', '')}",
        "",
        f"Requests:         {_num(ov.get('total_requests'))}",
        f"Unique visitors:  {_num(ov.get('unique_visitors'))}",
        f"Data sent:        {_bytes_human(ov.get('bytes_sent'))}",
        f"Error rate:       {ov.get('error_rate', 0)}%",
        f"Bot traffic:      {ov.get('bot_percent', 0)}%",
        f"p95 response:     {_ms(ov.get('p95_response_time_ms'))}",
        "",
        f"Security events:  {_num(sec.get('total_events'))}",
        f"Unique attackers: {_num(sec.get('unique_attackers'))}",
        f"Blocked:          {_num(sec.get('blocked'))}",
        "",
        f"Lifetime requests: {_num(life.get('total_requests'))} "
        f"over {_num(life.get('days_with_traffic'))} days",
    ])

    # ---- headline stats ------------------------------------------------------
    stats_row_1 = (
        "<tr>"
        + _stat("Requests", _num(ov.get("total_requests")), _change(ov.get("requests_change_percent")))
        + "<td style='width:12px'></td>"
        + _stat("Unique visitors", _num(ov.get("unique_visitors")), _change(ov.get("visitors_change_percent")))
        + "<td style='width:12px'></td>"
        + _stat("Data sent", _bytes_human(ov.get("bytes_sent")))
        + "</tr>"
    )
    stats_row_2 = (
        "<tr>"
        + _stat("Error rate", f"{ov.get('error_rate', 0)}%")
        + "<td style='width:12px'></td>"
        + _stat("Bot traffic", f"{ov.get('bot_percent', 0)}%")
        + "<td style='width:12px'></td>"
        + _stat("p95 response", _ms(ov.get("p95_response_time_ms")))
        + "</tr>"
    )
    stats = (
        f"<table style='width:100%;border-collapse:separate;border-spacing:0 12px'>"
        f"{stats_row_1}{stats_row_2}</table>"
    )

    # ---- sections ------------------------------------------------------------
    top_paths = _table(
        ["Path", "Requests", "Visitors", "Avg", "Errors"],
        [
            [
                _escape(p.get("uri", ""))[:80],
                _num(p.get("requests")),
                _num(p.get("unique_visitors")),
                _ms(p.get("avg_response_time_ms")),
                _num(p.get("errors")),
            ]
            for p in (paths.get("top_paths") or [])[:top_n]
        ],
        ["left", "right", "right", "right", "right"],
    )

    browsers = _table(
        ["Browser", "Share"],
        [[_escape(b.get("name")), f"{b.get('percent', 0)}%"]
         for b in (clients.get("browsers") or [])[:top_n]],
        ["left", "right"],
    )

    devices = _table(
        ["Device", "Share"],
        [[_escape(d.get("name")), f"{d.get('percent', 0)}%"]
         for d in (clients.get("devices") or [])[:top_n]],
        ["left", "right"],
    )

    countries = _table(
        ["Country", "Requests", "Visitors"],
        [
            [
                _escape(c.get("country_name") or c.get("country_code")),
                _num(c.get("requests")),
                _num(c.get("unique_visitors")),
            ]
            for c in (geo.get("countries") or [])[:top_n]
        ],
        ["left", "right", "right"],
    )

    referrers = _table(
        ["Referring domain", "Requests"],
        [[_escape(r.get("domain")), _num(r.get("requests"))]
         for r in (refs.get("referring_domains") or [])[:top_n]],
        ["left", "right"],
    )

    attack_summary = (
        f"<table style='width:100%;border-collapse:separate;border-spacing:0 12px'><tr>"
        + _stat("Security events", _num(sec.get("total_events")), _change(sec.get("events_change_percent")))
        + "<td style='width:12px'></td>"
        + _stat("Unique attackers", _num(sec.get("unique_attackers")))
        + "<td style='width:12px'></td>"
        + _stat("Blocked", f"{sec.get('blocked_percent', 0)}%")
        + "</tr></table>"
    )

    attackers = _table(
        ["Attacker IP", "Events", "Category", "Blocked"],
        [
            [
                _escape(a.get("client_ip")),
                _num(a.get("events")),
                _escape(a.get("category") or "—"),
                _num(a.get("blocked")),
            ]
            for a in (sec.get("top_attackers") or [])[:top_n]
        ],
        ["left", "right", "left", "right"],
    )

    targeted = _table(
        ["Targeted path", "Events"],
        [[_escape(t.get("uri", ""))[:80], _num(t.get("events"))]
         for t in (sec.get("targeted_paths") or [])[:top_n]],
        ["left", "right"],
    )

    lifetime = _table(
        ["Metric", "Value"],
        [
            ["Total requests (all time)", _num(life.get("total_requests"))],
            ["Total threats (all time)", _num(life.get("total_threats"))],
            ["Data sent (all time)", _bytes_human(life.get("bytes_sent"))],
            ["Days with traffic", _num(life.get("days_with_traffic"))],
            ["Average requests/day", _num(life.get("avg_requests_per_day"))],
            [
                "Busiest day",
                (
                    f"{life['busiest_day']['date']} ({_num(life['busiest_day']['requests'])})"
                    if life.get("busiest_day") else "—"
                ),
            ],
        ],
        ["left", "right"],
    )

    sampled_note = ""
    if clients.get("sampled"):
        sampled_note = (
            f"<p style='font:12px sans-serif;color:{MUTED};margin:0 0 8px'>"
            f"Browser, device and bot figures are from the most recent "
            f"{_num(clients.get('sample_size'))} of {_num(clients.get('total_in_period'))} "
            f"requests in this period.</p>"
        )

    html = f"""
<div style="max-width:720px;margin:0 auto;padding:24px;background:#ffffff">
  <div style="border-left:4px solid {BRAND};padding-left:12px;margin-bottom:20px">
    <div style="font:600 20px sans-serif;color:{INK}">{_escape(domain)}</div>
    <div style="font:14px sans-serif;color:{MUTED};margin-top:2px">
      Traffic report · {_escape(period)} · generated {_escape((meta.get('generated_at') or '')[:16].replace('T', ' '))} UTC
    </div>
  </div>

  {stats}

  {_section("Most requested paths", top_paths)}
  {_section("Security", attack_summary + attackers + targeted)}
  {_section("Browsers", sampled_note + browsers)}
  {_section("Devices", devices)}
  {_section("Countries", countries)}
  {_section("Referring domains", referrers)}
  {_section("Lifetime totals", lifetime)}

  <p style="font:12px sans-serif;color:{MUTED};margin-top:28px;padding-top:12px;
            border-top:1px solid {LINE}">
    Detail sections cover the reporting window and are limited by log retention.
    Lifetime totals come from daily rollups, which survive retention pruning.
    <br>Sent by Ghostwire Proxy.
  </p>
</div>
""".strip()

    return subject, text, html
