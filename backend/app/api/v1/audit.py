from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_project_or_404
from app.core.db import get_db
from app.models.models import AuditLog, User
from app.schemas.schemas import AuditLogResponse


router = APIRouter(prefix="/audit", tags=["Audit Log"])


@router.get("", response_model=List[AuditLogResponse])
async def list_audit_logs(
    project_id: str = Query(..., description="ID of the project that scopes this request"),
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await get_project_or_404(db, project_id, current_user.id)
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.project_id == project.id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()
