"""Shared test fixtures for Ghostwire Proxy tests."""

import os
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

# Override settings BEFORE importing app modules
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-key-for-testing-only")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key-for-testing-only")
# NOTE: DATABASE_URL is deliberately NOT set from the ambient environment here.
#
# This suite calls Base.metadata.drop_all() after every single test. It used to
# do os.environ.setdefault("DATABASE_URL", <test db>), which only applies when
# the variable is unset — so anywhere it was already set (inside the API
# container, where it points at production) the safe default was silently
# skipped and the tests dropped the live schema. That is what happened on
# 2026-09-08, and almost certainly on 2026-08-16 before that.
#
# The target now comes from its own variable and is validated below.
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("BCRYPT_ROUNDS", "4")  # Fast rounds for tests
os.environ.setdefault("BETTER_AUTH_SECRET", "test-better-auth-secret")
os.environ.setdefault("INTERNAL_AUTH_TOKEN", "test-internal-token")

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from httpx import AsyncClient, ASGITransport

from app.core.database import Base, get_db
from app.core.security import get_password_hash
from app.core.auth_session import create_session
from app.models.user import User

# Test database URL — a dedicated throwaway database, never the ambient one.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://ghostwire:GhostwireProxy2024Secure@ghostwire-proxy-postgres:5432/ghostwire_proxy_test",
)

# Hard stop rather than a silent fallback: the cost of getting this wrong is the
# entire database.
_target_db = TEST_DATABASE_URL.rsplit("/", 1)[-1].split("?")[0]
if not _target_db.endswith("_test"):
    raise RuntimeError(
        f"Refusing to run the test suite against database {_target_db!r}.\n"
        "Every test calls Base.metadata.drop_all(), so the target database name "
        "must end in '_test'. Set TEST_DATABASE_URL to a throwaway database."
    )

# Point application code that reads DATABASE_URL at the same throwaway database,
# so nothing under test can reach the real one.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

TestSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest.fixture(autouse=True)
async def setup_database():
    """Create all tables before each test, drop after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    # Dispose connections so they don't leak across event loops
    await test_engine.dispose()


@pytest.fixture
async def db_session():
    """Provide a transactional database session for tests."""
    async with TestSessionLocal() as session:
        yield session


@pytest.fixture
async def admin_user(db_session: AsyncSession):
    """Create an admin user for testing."""
    user = User(
        id=str(uuid.uuid4()),
        email="admin@test.com",
        name="Test Admin",
        password_hash=get_password_hash("testpassword123"),
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def regular_user(db_session: AsyncSession):
    """Create a regular user for testing."""
    user = User(
        id=str(uuid.uuid4()),
        email="user@test.com",
        name="Test User",
        password_hash=get_password_hash("testpassword123"),
        role="user",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def inactive_user(db_session: AsyncSession):
    """Create a disabled user for testing."""
    user = User(
        id=str(uuid.uuid4()),
        email="inactive@test.com",
        name="Inactive User",
        password_hash=get_password_hash("testpassword123"),
        role="user",
        is_active=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def admin_token(db_session: AsyncSession, admin_user: User):
    """A signed-in session (Better Auth) for the admin user; its token works as a Bearer."""
    session = await create_session(db_session, admin_user.id)
    await db_session.commit()
    return session.token


@pytest.fixture
async def user_token(db_session: AsyncSession, regular_user: User):
    """A signed-in session (Better Auth) for a regular user."""
    session = await create_session(db_session, regular_user.id)
    await db_session.commit()
    return session.token


@pytest.fixture
def auth_headers(admin_token: str):
    """Auth headers with admin token."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def user_auth_headers(user_token: str):
    """Auth headers with regular user token."""
    return {"Authorization": f"Bearer {user_token}"}


async def _override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@pytest.fixture
async def client():
    """Async HTTP test client with dependency overrides."""
    from app.main import app

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
