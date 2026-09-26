from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

from app.services.evaluator import PRESENCE_OPERATORS, RULE_OPERATORS, normalize_operator


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


class RuleCondition(BaseModel):
    """
    A single targeting condition. All conditions inside a rule are ANDed.
    """

    attr: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=64,
            pattern=r"^[A-Za-z0-9_.:-]+$",
        ),
    ] = Field(..., description="Attribute name evaluated against the request context, e.g. email")
    op: str = Field(default="equals", description="One of the supported condition operators")
    value: Any = Field(
        default=None,
        validate_default=True,
        description="Comparison value; ignored by exists/not_exists",
    )

    @field_validator("op")
    @classmethod
    def validate_operator(cls, value: str) -> str:
        normalized = normalize_operator(value)
        if normalized not in RULE_OPERATORS:
            raise ValueError(
                f"Unsupported operator '{value}'. Supported: {', '.join(RULE_OPERATORS)}"
            )
        return normalized

    @field_validator("value")
    @classmethod
    def default_presence_value(cls, value: Any, info) -> Any:
        # `exists` / `not_exists` carry no comparison value; pin it to a
        # boolean so stored conditions stay self-describing.
        if info.data.get("op") in PRESENCE_OPERATORS:
            return normalize_operator(info.data.get("op")) == "exists"
        return value


class RuleCreate(BaseModel):
    conditions: List[RuleCondition] = Field(
        ...,
        min_length=1,
        max_length=25,
        description="All conditions must match (AND) for the rule to apply",
    )
    serve: bool = Field(default=True, description="Value served when every condition matches")
    priority: Optional[int] = Field(
        default=None,
        ge=0,
        description="0 is the highest priority. Appended to the end when omitted.",
    )


class RuleUpdate(BaseModel):
    conditions: Optional[List[RuleCondition]] = Field(default=None, min_length=1, max_length=25)
    serve: Optional[bool] = None
    priority: Optional[int] = Field(default=None, ge=0)


class RuleReorder(BaseModel):
    rule_ids: List[str] = Field(
        ...,
        min_length=1,
        description="Every rule id of the environment, ordered from highest to lowest priority",
    )


class TargetingRuleSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[str] = None
    env: str
    priority: int = 0
    conditions: List[RuleCondition] = Field(
        default_factory=list,
        # The database column is `conditions_json`; every wire format (flag
        # list, rule CRUD, bootstrap) exposes the same `conditions` shape.
        validation_alias=AliasChoices("conditions", "conditions_json"),
    )
    serve: bool = True


class TargetingRuleResponse(TargetingRuleSchema):
    id: str


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


# ---------------------------------------------------------------------------
# API Key Management
# ---------------------------------------------------------------------------
class ApiKeyCreate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
    env: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[a-z][a-z0-9_-]{0,63}$")] = Field(
        ..., description="Environment name (e.g., dev, staging, prod)"
    )


class ApiKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    env: str
    name: str
    prefix: str  # The full API key (we use the prefix as the secret)
    revoked: bool
    created_at: datetime


class ApiKeyListResponse(BaseModel):
    keys: List[ApiKeyResponse]
