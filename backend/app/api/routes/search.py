"""Global search endpoint — searches across proxy hosts, threat actors, blocklist, and certificates."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, cast, String, or_

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.proxy_host import ProxyHost
from app.models.waf import ThreatActor
from app.models.firewall import FirewallBlocklist
from app.models.certificate import Certificate

router = APIRouter()


@router.get("/")
async def global_search(
    q: str = Query(..., min_length=1, max_length=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search across hosts, IPs, threat actors, blocklist entries, and certificates."""
    term = f"%{q}%"
    results = []

    # 1. Proxy Hosts — search domain_names (JSON) and forward_host
    hosts_q = select(ProxyHost).where(
        or_(
            ProxyHost.forward_host.ilike(term),
            cast(ProxyHost.domain_names, String).ilike(term),
        )
    ).limit(10)
    hosts = (await db.execute(hosts_q)).scalars().all()
    for h in hosts:
        domains = h.domain_names if isinstance(h.domain_names, list) else []
        results.append({
            "type": "host",
            "id": h.id,
            "title": ", ".join(domains[:2]) or h.forward_host,
            "subtitle": f"→ {h.forward_host}:{h.forward_port}",
            "url": f"/dashboard/proxy-hosts",
            "enabled": h.enabled,
        })

    # 2. Threat Actors — search by IP or country
    actors_q = select(ThreatActor).where(
        or_(
            ThreatActor.ip_address.ilike(term),
            ThreatActor.country_name.ilike(term),
        )
    ).order_by(ThreatActor.threat_score.desc()).limit(10)
    actors = (await db.execute(actors_q)).scalars().all()
    for a in actors:
        results.append({
            "type": "threat",
            "id": a.id,
            "title": a.ip_address,
            "subtitle": f"Score: {a.threat_score} · {a.current_status}" + (f" · {a.country_name}" if a.country_name else ""),
            "url": f"/dashboard/threats",
        })

    # 3. Firewall Blocklist — search by IP
    bl_q = select(FirewallBlocklist).where(
        FirewallBlocklist.ip_address.ilike(term),
    ).order_by(FirewallBlocklist.id.desc()).limit(10)
    bl_entries = (await db.execute(bl_q)).scalars().all()
    seen_ips = set()
    for b in bl_entries:
        if b.ip_address in seen_ips:
            continue
        seen_ips.add(b.ip_address)
        results.append({
            "type": "blocklist",
            "id": b.id,
            "title": b.ip_address,
            "subtitle": f"Status: {b.status}" + (f" · {b.error_message}" if b.error_message else ""),
            "url": f"/dashboard/firewalls",
        })

    # 4. Certificates — search by name or domain_names
    certs_q = select(Certificate).where(
        or_(
            Certificate.name.ilike(term),
            cast(Certificate.domain_names, String).ilike(term),
        )
    ).limit(5)
    certs = (await db.execute(certs_q)).scalars().all()
    for c in certs:
        domains = c.domain_names if isinstance(c.domain_names, list) else []
        results.append({
            "type": "certificate",
            "id": c.id,
            "title": c.name or ", ".join(domains[:2]),
            "subtitle": ", ".join(domains[:3]),
            "url": f"/dashboard/certificates",
        })

    return {"query": q, "results": results, "total": len(results)}
