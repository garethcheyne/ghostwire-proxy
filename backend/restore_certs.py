#!/usr/bin/env python3
"""Restore certificate content from files to database."""

import asyncio
import os

from app.core.database import AsyncSessionLocal
from app.core.security import encrypt_data
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

            # A one-off CLI script: blocking reads are fine here.
            if os.path.exists(crt_path) and os.path.exists(key_path):  # noqa: ASYNC240
                with open(crt_path) as f:  # noqa: ASYNC230
                    cert_content = f.read()
                with open(key_path) as f:  # noqa: ASYNC230
                    key_content = f.read()

                cert.certificate = cert_content
                # The app keeps private keys encrypted at rest (and decrypts them to write nginx's files).
                cert.certificate_key = encrypt_data(key_content)
                print(f"  Restored: {cert.name}")
            else:
                print(f"  Missing files for: {cert.name}")

        await session.commit()
        print("\nCertificate content restored!")


if __name__ == "__main__":
    asyncio.run(restore_certs())
