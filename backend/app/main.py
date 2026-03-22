from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import os
import asyncio

from app.core.config import settings
from app.core.database import engine, Base
from app.core.redis import close_redis
from app.api import router as api_router

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Ghostwire Proxy API...")

    # Ensure data directories exist
    os.makedirs(settings.nginx_config_path, exist_ok=True)
    os.makedirs(settings.certificates_path, exist_ok=True)

    # Create database tables if they don't exist
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables verified/created")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

    # Check if setup is required
    from app.models.user import User
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import select, func

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(func.count(User.id)))
        count = result.scalar() or 0

        if count == 0:
            logger.info("No users found - initial setup required at /auth/login")
        else:
            logger.info(f"Found {count} users in database")

    # Start background metrics collection task
    from app.services.system_service import system_monitor_service

    async def metrics_collection_loop():
        """Periodically collect system metrics."""
        while True:
            try:
                await asyncio.sleep(60)  # Collect every 60 seconds
                await system_monitor_service.collect_and_store_metrics()
            except asyncio.CancelledError:
                logger.info("Metrics collection task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in metrics collection: {e}")

    metrics_task = asyncio.create_task(metrics_collection_loop())
    logger.info("Started background metrics collection task")

    yield

    # Cancel metrics collection task
    metrics_task.cancel()
    try:
        await metrics_task
    except asyncio.CancelledError:
        pass

    # Shutdown
    logger.info("Shutting down Ghostwire Proxy API...")
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title="Ghostwire Proxy API",
    description="Reverse Proxy Management API",
    version="0.1.0",
    lifespan=lifespan,
    redirect_slashes=True,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "ghostwire-proxy-api"}


# Include API routes
app.include_router(api_router, prefix="/api")
