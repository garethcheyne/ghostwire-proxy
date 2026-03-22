#!/usr/bin/env python3
"""Regenerate all nginx configs from database."""

import asyncio
from app.core.database import AsyncSessionLocal
from app.services.openresty_service import generate_all_configs, reload_nginx


async def main():
    async with AsyncSessionLocal() as db:
        print("Regenerating nginx configs...")
        files = await generate_all_configs(db)
        print(f"Generated {len(files)} config files:")
        for f in files:
            print(f"  - {f}")

        print("\nReloading nginx...")
        success, msg = reload_nginx()
        print(f"Result: {msg}")


if __name__ == "__main__":
    asyncio.run(main())
