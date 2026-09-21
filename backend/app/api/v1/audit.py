from typing import List, Optional, Any
from datetime import datetime
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.models import AuditLog

router = APIRouter(prefix="/audit", tags=["Audit Log"])


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    flag_id: Optional[str] = None
    env: Optional[str] = None
    actor: str
    action: str
    before: Optional[Any] = None
    after: Optional[Any] = None
    created_at: datetime



@router.get("", response_model=List[AuditLogResponse])
async def list_audit_logs(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    res = await db.execute(stmt)
    return res.scalars().all()
