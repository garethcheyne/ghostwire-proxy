#!/usr/bin/env python3
"""Restore proxy hosts and certificates from nginx config files."""

import asyncio
import json
from datetime import datetime
from app.core.database import AsyncSessionLocal, engine
from app.models import ProxyHost, Certificate
from sqlalchemy import text

# Certificate data extracted from nginx configs
CERTIFICATES = [
    {"id": "17ec7428-4dde-4ccf-aa46-891a2b313d37", "name": "sonarr.err403.com", "domain_names": ["sonarr.err403.com"]},
    {"id": "18ece02c-ff55-4a69-b519-b31fb2d69f9f", "name": "radarr.err403.com", "domain_names": ["radarr.err403.com"]},
    {"id": "4d3505dd-6e51-48bb-ab28-b54e5dd938ff", "name": "route-x.err403.com", "domain_names": ["route-x.err403.com"]},
    {"id": "7855ad37-4013-48e7-865f-725b90b2d58a", "name": "plex.err403.com", "domain_names": ["plex.err403.com"]},
    {"id": "7fe76c5b-8155-4de5-ab02-0bbf8527578c", "name": "ghostwire.err403.com", "domain_names": ["ghostwire.err403.com"]},
    {"id": "95f5bad6-eaf3-4df2-82f8-6346f5f183c2", "name": "overseerr.err403.com", "domain_names": ["overseerr.err403.com"]},
    {"id": "b8260878-da62-4b68-a3dd-17ad17664ef2", "name": "docs.err403.com", "domain_names": ["docs.err403.com"]},
    {"id": "b9baa307-7ac8-49c0-a67b-e536e8c5411c", "name": "dev-cpr.err403.com", "domain_names": ["dev-cpr.err403.com"]},
    {"id": "bb2c3f89-e3e1-4934-b7dd-35f7a05673ae", "name": "err403.com", "domain_names": ["err403.com", "www.err403.com"]},
    {"id": "cda15eb1-ca72-4f26-b83b-090ab1b63de8", "name": "pass.err403.com", "domain_names": ["pass.err403.com"]},
]

# Proxy host data extracted from nginx configs
PROXY_HOSTS = [
    {
        "id": "0bd55afc-4c21-4420-b590-3022f6a0d110",
        "domain_names": ["err403.com", "www.err403.com"],
        "forward_scheme": "http",
        "forward_host": "192.168.0.6",
        "forward_port": 3000,
        "ssl_enabled": True,
        "ssl_force": True,
        "certificate_id": "bb2c3f89-e3e1-4934-b7dd-35f7a05673ae",
        "http2_support": True,
        "hsts_enabled": False,
        "websockets_support": False,
        "block_exploits": True,
    },
    {
        "id": "0d0fa775-d161-4052-af86-2589318e85df",
        "domain_names": ["radarr.err403.com"],
        "forward_scheme": "http",
        "forward_host": "192.168.0.221",
        "forward_port": 7878,
        "ssl_enabled": True,
        "ssl_force": True,
        "certificate_id": "18ece02c-ff55-4a69-b519-b31fb2d69f9f",
        "http2_support": True,
        "hsts_enabled": False,
        "websockets_support": True,
        "block_exploits": True,
    },
    {
        "id": "280fe745-c1bb-459e-890b-aad28deb17d1",
        "domain_names": ["plex.err403.com"],
        "forward_scheme": "http",
        "forward_host": "192.168.0.216",
        "forward_port": 32400,
        "ssl_enabled": True,
        "ssl_force": True,
        "certificate_id": "7855ad37-4013-48e7-865f-725b90b2d58a",
        "http2_support": True,
        "hsts_enabled": False,
        "websockets_support": True,
        "block_exploits": True,
    },
    {
        "id": "70a20075-b989-4576-9a6b-82032f5ec1e4",
        "domain_names": ["docs.err403.com"],
        "forward_scheme": "http",
        "forward_host": "192.168.0.109",
        "forward_port": 8101,
        "ssl_enabled": True,
        "ssl_force": True,
        "certificate_id": "b8260878-da62-4b68-a3dd-17ad17664ef2",
        "http2_support": True,
        "hsts_enabled": True,
        "websockets_support": True,
        "block_exploits": True,
    },
    {
        "id": "7b00c474-0d69-4e11-99d2-f0956357dc51",
        "domain_names": ["ghostwire.err403.com"],
        "forward_scheme": "http",
        "forward_host": "192.168.0.109",
        "forward_port": 8766,
        "ssl_enabled": True,
        "ssl_force": True,
        "certificate_id": "7fe76c5b-8155-4de5-ab02-0bbf8527578c",
        "http2_support": True,
        "hsts_enabled": False,
        "websockets_support": True,
        "block_exploits": True,
    },
    {
        "id": "88ab5dec-2102-4d89-858d-f78484e624d8",
        "domain_names": ["route-x.err403.com"],
        "forward_scheme": "http",
        "forward_host": "192.168.0.109",
        "forward_port": 7285,
        "ssl_enabled": True,
        "ssl_force": True,
        "certificate_id": "4d3505dd-6e51-48bb-ab28-b54e5dd938ff",
        "http2_support": True,
        "hsts_enabled": False,
        "websockets_support": True,
        "block_exploits": True,
    },
    {
        "id": "bf39c887-bd3c-4ae0-a756-1fd3ffb2098f",
        "domain_names": ["overseerr.err403.com"],
        "forward_scheme": "http",
        "forward_host": "192.168.0.226",
        "forward_port": 5055,
        "ssl_enabled": True,
        "ssl_force": True,
        "certificate_id": "95f5bad6-eaf3-4df2-82f8-6346f5f183c2",
        "http2_support": True,
        "hsts_enabled": False,
        "websockets_support": True,
        "block_exploits": True,
    },
    {
        "id": "df3e686a-c61a-48e7-b8f2-175016bc120d",
        "domain_names": ["dev-cpr.err403.com"],
        "forward_scheme": "http",
        "forward_host": "192.168.0.109",
        "forward_port": 8102,
        "ssl_enabled": True,
        "ssl_force": True,
        "certificate_id": "b9baa307-7ac8-49c0-a67b-e536e8c5411c",
        "http2_support": True,
        "hsts_enabled": False,
        "websockets_support": True,
        "block_exploits": True,
    },
    {
        "id": "e6e50098-54f5-4454-a721-8d8519ba3e77",
        "domain_names": ["pass.err403.com"],
        "forward_scheme": "http",
        "forward_host": "192.168.0.4",
        "forward_port": 8000,
        "ssl_enabled": True,
        "ssl_force": True,
        "certificate_id": "cda15eb1-ca72-4f26-b83b-090ab1b63de8",
        "http2_support": True,
        "hsts_enabled": False,
        "websockets_support": True,
        "block_exploits": True,
    },
    {
        "id": "e755bfdd-ae17-48a9-8a27-3ec3c7eee2a3",
        "domain_names": ["sonarr.err403.com"],
        "forward_scheme": "http",
        "forward_host": "192.168.0.222",
        "forward_port": 8989,
        "ssl_enabled": True,
        "ssl_force": True,
        "certificate_id": "17ec7428-4dde-4ccf-aa46-891a2b313d37",
        "http2_support": True,
        "hsts_enabled": False,
        "websockets_support": True,
        "block_exploits": True,
    },
]


async def restore_data():
    """Restore certificates and proxy hosts to database."""
    async with AsyncSessionLocal() as session:
        now = datetime.utcnow()

        # Insert certificates
        print("Restoring certificates...")
        for cert_data in CERTIFICATES:
            cert = Certificate(
                id=cert_data["id"],
                name=cert_data["name"],
                domain_names=cert_data["domain_names"],  # JSON column takes list directly
                is_letsencrypt=False,
                status="valid",
                created_at=now,
                updated_at=now,
            )
            session.add(cert)
            print(f"  - {cert_data['name']}")

        await session.commit()
        print(f"Restored {len(CERTIFICATES)} certificates")

        # Insert proxy hosts
        print("\nRestoring proxy hosts...")
        for host_data in PROXY_HOSTS:
            host = ProxyHost(
                id=host_data["id"],
                domain_names=host_data["domain_names"],  # JSON column takes list directly
                forward_scheme=host_data["forward_scheme"],
                forward_host=host_data["forward_host"],
                forward_port=host_data["forward_port"],
                ssl_enabled=host_data["ssl_enabled"],
                ssl_force=host_data["ssl_force"],
                certificate_id=host_data["certificate_id"],
                http2_support=host_data["http2_support"],
                hsts_enabled=host_data["hsts_enabled"],
                hsts_subdomains=False,
                websockets_support=host_data["websockets_support"],
                block_exploits=host_data["block_exploits"],
                enabled=True,
                traffic_logging_enabled=False,
                # New fields with defaults
                client_max_body_size="100m",
                proxy_buffering=True,
                proxy_buffer_size="4k",
                proxy_buffers="8 4k",
                cache_enabled=False,
                rate_limit_enabled=False,
                rate_limit_requests=100,
                rate_limit_period="1s",
                rate_limit_burst=50,
                created_at=now,
                updated_at=now,
            )
            session.add(host)
            print(f"  - {host_data['domain_names'][0]} -> {host_data['forward_host']}:{host_data['forward_port']}")

        await session.commit()
        print(f"Restored {len(PROXY_HOSTS)} proxy hosts")

        print("\nData restoration complete!")


if __name__ == "__main__":
    asyncio.run(restore_data())
