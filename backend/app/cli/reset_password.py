"""Emergency admin access: set a user's password from the server's shell.

    docker exec -it ghostwire-proxy-api python -m app.cli.reset_password admin@example.com
    docker exec -it ghostwire-proxy-api python -m app.cli.reset_password --list
    docker exec -it ghostwire-proxy-api python -m app.cli.reset_password admin@example.com --disable-2fa

Without a password argument it asks for one (or generates one with --generate). It also
re-enables the account and signs the user out everywhere. Add --make-admin to restore the admin
role. --disable-2fa turns off the user's two-factor (lost phone and backup codes); on its own it
leaves the password as it is. If two-factor is required for everyone, they set it up again at
their next sign-in. Works whatever state the admin UI is in, because it writes straight to the database.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import secrets
import string
import sys

from sqlalchemy import select

from app.core.auth_session import revoke_sessions, set_password
from app.core.database import AsyncSessionLocal, engine
from app.models.audit_log import AuditLog
from app.models.user import User
from app.services import admin_mfa_service


def _generate() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(20))


async def _list() -> int:
    async with AsyncSessionLocal() as db:
        users = (await db.execute(select(User).order_by(User.created_at))).scalars().all()
        if not users:
            print("No users yet. Open the admin UI to run the first-time setup.")
        for user in users:
            state = "active" if user.is_active else "disabled"
            two_factor = "2FA on" if admin_mfa_service.is_enrolled(user) else "2FA off"
            print(f"{user.email:40} {user.role:6} {state:8} {two_factor}")
    return 0


async def _reset(email: str, password: str | None, make_admin: bool, disable_2fa: bool = False) -> int:
    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.email == email.strip().lower()))
        ).scalar_one_or_none()
        if not user:
            print(f"No user with email {email}. Use --list to see them.", file=sys.stderr)
            return 1

        if password:
            await set_password(db, user, password)
        if disable_2fa:
            await admin_mfa_service.disable_mfa(db, user)
        user.is_active = True
        if make_admin:
            user.role = "admin"
        await revoke_sessions(db, user.id)
        db.add(
            AuditLog(
                user_id=user.id,
                email=user.email,
                action="password_reset_cli",
                details="From the server shell (app.cli.reset_password): "
                + ", ".join(
                    part
                    for part, done in (("password reset", bool(password)), ("two-factor disabled", disable_2fa))
                    if done
                ),
            )
        )
        await db.commit()
        changes = [c for c, done in (("password set", bool(password)), ("two-factor turned off", disable_2fa)) if done]
        print(f"{user.email} ({user.role}): {', '.join(changes)}; the account is active.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("email", nargs="?", help="the user's email")
    parser.add_argument("--password", help="the new password (asked for if omitted)")
    parser.add_argument("--generate", action="store_true", help="generate a random password and print it")
    parser.add_argument("--make-admin", action="store_true", help="also give the user the admin role")
    parser.add_argument("--disable-2fa", action="store_true", help="turn off the user's two-factor")
    parser.add_argument("--list", action="store_true", help="list users")
    args = parser.parse_args()

    async def run() -> int:
        try:
            if args.list:
                return await _list()
            if not args.email:
                parser.print_usage()
                return 2

            password = args.password
            if args.disable_2fa and not (password or args.generate):
                return await _reset(args.email, None, args.make_admin, disable_2fa=True)
            if args.generate:
                password = _generate()
            elif not password:
                password = getpass.getpass("New password: ")
                if password != getpass.getpass("Again: "):
                    print("The passwords don't match.", file=sys.stderr)
                    return 1
            if len(password) < 8:
                print("Use at least 8 characters.", file=sys.stderr)
                return 1

            code = await _reset(args.email, password, args.make_admin, args.disable_2fa)
            if code == 0 and args.generate:
                print(f"New password: {password}")
            return code
        finally:
            await engine.dispose()

    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
