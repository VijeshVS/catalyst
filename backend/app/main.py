import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.db import engine, Base
from app.core.cache import init_redis, close_redis
from app.api.v1 import api_v1_router
from app.api.v1.health import router as health_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("catalyst")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Catalyst API service...")
    # Initialize DB tables (for development/bootstrap)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables verified.")
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
