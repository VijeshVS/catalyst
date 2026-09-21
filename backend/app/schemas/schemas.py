from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict


# Evaluation
class EvaluationContext(BaseModel):
    user_id: str = Field(..., description="Unique user or entity key for sticky rollout calculation")
    attributes: Dict[str, Any] = Field(default_factory=dict, description="Context attributes (e.g. email, role, country, app_version)")


class EvaluateRequest(BaseModel):
    flag_key: str
    context: EvaluationContext
    env: str = Field(default="dev", description="Target environment (dev, staging, prod)")


class EvaluateResponse(BaseModel):
    flag_key: str
    value: bool
    reason: str  # KILL_SWITCH_ACTIVE, RULE_MATCH, PERCENTAGE_ROLLOUT, DEFAULT_VALUE, FLAG_NOT_FOUND
    rule_id: Optional[str] = None


class BatchEvaluateRequest(BaseModel):
    context: EvaluationContext
    env: str = Field(default="dev")
    flag_keys: Optional[List[str]] = None


class BatchEvaluateResponse(BaseModel):
    evaluations: Dict[str, EvaluateResponse]


class BootstrapResponse(BaseModel):
    env: str
    version: int
    flags: Dict[str, Any]


# Flag Management
class FlagStateSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[str] = None
    env: str
    enabled: bool = True
    percentage: int = Field(default=0, ge=0, le=100)
    version: int = 1


class FlagStateUpdate(BaseModel):
    enabled: Optional[bool] = None
    percentage: Optional[int] = Field(default=None, ge=0, le=100)


class TargetingRuleSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[str] = None
    env: str
    priority: int = 0
    conditions_json: List[Dict[str, Any]] = Field(default_factory=list)
    serve: bool = True


class FlagCreate(BaseModel):
    key: str = Field(..., pattern=r"^[a-z0-9-_.]+$")
    name: str
    description: Optional[str] = None
    default_value: bool = False


class FlagUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    default_value: Optional[bool] = None
    archived: Optional[bool] = None


class FlagResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    key: str
    name: str
    description: Optional[str] = None
    default_value: bool
    archived: bool
    created_at: datetime
    states: List[FlagStateSchema] = []
    rules: List[TargetingRuleSchema] = []



# Health & System
class HealthCheckResponse(BaseModel):
    status: str
    environment: str
    database: str
    redis: str
    version: str = "0.1.0"
