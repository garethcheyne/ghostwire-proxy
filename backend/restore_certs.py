#!/usr/bin/env python3
"""Restore certificate content from files to database."""

import asyncio
import os
from app.core.database import AsyncSessionLocal
from app.models.certificate import Certificate
from sqlalchemy import select

CERTS_PATH = "/data/certificates"


async def restore_certs():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Certificate))
        certs = result.scalars().all()

        print(f"Found {len(certs)} certificates in database")

        for cert in certs:
            crt_path = os.path.join(CERTS_PATH, f"{cert.id}.crt")
            key_path = os.path.join(CERTS_PATH, f"{cert.id}.key")

            if os.path.exists(crt_path) and os.path.exists(key_path):
                with open(crt_path, "r") as f:
                    cert_content = f.read()
                with open(key_path, "r") as f:
                    key_content = f.read()

                cert.certificate = cert_content
                cert.certificate_key = key_content
                print(f"  Restored: {cert.name}")
            else:
                print(f"  Missing files for: {cert.name}")

        await session.commit()
        print("\nCertificate content restored!")


if __name__ == "__main__":
    asyncio.run(restore_certs())
