from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
class UserRegisterRequest(BaseModel):
    email: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=255)]
    password: Annotated[str, StringConstraints(min_length=8, max_length=256)]
    full_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if (
            "@" not in normalized
            or normalized.startswith("@")
            or normalized.endswith("@")
            or any(character.isspace() for character in normalized)
            or "." not in normalized.rsplit("@", 1)[1]
        ):
            raise ValueError("A valid email address is required")
        return normalized


class UserLoginRequest(BaseModel):
    email: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=255)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=256)]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class RefreshTokenRequest(BaseModel):
    refresh_token: Annotated[str, StringConstraints(min_length=1)]


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
class EvaluationContext(BaseModel):
    user_id: str = Field(..., description="Unique user or entity key for sticky rollout calculation")
    attributes: Dict[str, Any] = Field(
        default_factory=dict,
        description="Context attributes (e.g. email, role, country, app_version)",
    )


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


# ---------------------------------------------------------------------------
# Multi-tenant hierarchy (Organizations, Projects & Environments)
# ---------------------------------------------------------------------------
class OrganizationCreate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    description: Annotated[
        Optional[str], StringConstraints(strip_whitespace=True, max_length=500)
    ] = None


class ProjectCreate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class EnvironmentCreate(BaseModel):
    name: Annotated[
        str,
        StringConstraints(strip_whitespace=True, pattern=r"^[a-z][a-z0-9_-]{0,63}$"),
    ] = Field(..., description="Lowercase environment identifier, e.g. qa or perf-test")


class EnvironmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    name: str
    version: int


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    name: str
    created_at: datetime
    environments: List[EnvironmentResponse] = Field(default_factory=list)
    # These display fields are computed from the currently loaded project
    # relationship and keep the list endpoint inexpensive for the dashboard.
    flag_count: int = 0
    updated_at: Optional[datetime] = None


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: Optional[str] = None
    owner_id: Optional[str]
    created_at: datetime
    projects: List[ProjectResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Flag management
# ---------------------------------------------------------------------------
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
    states: List[FlagStateSchema] = Field(default_factory=list)
    rules: List[TargetingRuleSchema] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Audit & system
# ---------------------------------------------------------------------------
class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    flag_id: Optional[str] = None
    env: Optional[str] = None
    actor: str
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    action: str
    before: Optional[Any] = None
    after: Optional[Any] = None
    created_at: datetime


class HealthCheckResponse(BaseModel):
    status: str
    environment: str
    database: str
    redis: str
    version: str = "0.1.0"
