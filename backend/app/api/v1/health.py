from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.db import get_db
from app.core.cache import get_redis
from app.schemas.schemas import HealthCheckResponse

router = APIRouter()


@router.get("/healthz", response_model=HealthCheckResponse)
async def health_check(db: AsyncSession = Depends(get_db)):
    # Check database
    db_status = "ok"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    # Check redis
    redis_client = await get_redis()
    redis_status = "unavailable"
    if redis_client:
        try:
            await redis_client.ping()
            redis_status = "ok"
        except Exception as e:
            redis_status = f"unhealthy: {str(e)}"

    # An absent Redis is deliberately not degradation. The snapshot cache is
    # designed to fail open, so the API keeps serving correct values from
    # PostgreSQL, just more slowly. Only a failing ping, or a failing
    # database, degrades the service.
    overall_status = "ok" if (db_status == "ok" and (redis_status == "ok" or redis_status == "unavailable")) else "degraded"

    return HealthCheckResponse(
        status=overall_status,
        environment=settings.ENVIRONMENT,
        database=db_status,
        redis=redis_status,
        version="0.1.0",
    )
