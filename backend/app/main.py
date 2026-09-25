import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect

from app.core.config import settings
from app.core.db import engine, Base
from app.core.cache import init_redis, close_redis
from app.api.v1 import api_v1_router
from app.api.v1.health import router as health_router


class SchemaCompatibilityError(RuntimeError):
    """Raised when an existing database predates the auth schema."""


def _verify_auth_schema(connection) -> None:
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    required_columns = {
        "users": {"password_hash", "full_name"},
        "organizations": {"description", "owner_id"},
        "audit_logs": {"user_id", "user_email"},
    }
    missing = []
    for table_name, columns in required_columns.items():
        if table_name not in tables:
            continue
        existing = {column["name"] for column in inspector.get_columns(table_name)}
        missing.extend(f"{table_name}.{column}" for column in columns - existing)
    if missing:
        names = ", ".join(sorted(missing))
        raise SchemaCompatibilityError(
            f"Database schema is missing auth columns ({names}). "
            "Apply backend/migrations/001_auth_ownership.sql before starting Catalyst."
        )

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("catalyst")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Catalyst API service...")
    # Initialize DB tables for fresh development/bootstrap databases. This
    # does not upgrade an existing Phase 1 schema; apply the documented
    # backend/migrations/001_auth_ownership.sql transition before deploying
    # the authentication-enabled API to such a database.
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(_verify_auth_schema)
        logger.info("Database tables verified.")
    except SchemaCompatibilityError:
        logger.exception("Database schema is not compatible with Catalyst authentication.")
        raise
    except Exception as e:
        logger.warning(f"Could not automatically sync database tables at startup: {e}")

    # Initialize Redis connection
    await init_redis()

    yield

    logger.info("Shutting down Catalyst API service...")
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title="Catalyst Feature Flag Platform",
    description="High-performance, low-latency Feature Flag & Rollout Management Engine",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers
app.include_router(health_router, tags=["Health"])
app.include_router(api_v1_router, prefix=settings.API_V1_STR)


@app.get("/")
async def root():
    return {
        "name": "Catalyst Feature Flag Platform",
        "status": "operational",
        "docs_url": "/docs",
        "api_v1": settings.API_V1_STR,
    }
