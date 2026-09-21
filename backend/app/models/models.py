import uuid
from datetime import datetime
from typing import Optional, List, Any
from sqlalchemy import (
    String,
    Boolean,
    Integer,
    ForeignKey,
    DateTime,
    Index,
    UniqueConstraint,
    JSON,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    users: Mapped[List["User"]] = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    projects: Mapped[List["Project"]] = relationship("Project", back_populates="organization", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    organization: Mapped["Organization"] = relationship("Organization", back_populates="users")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    organization: Mapped["Organization"] = relationship("Organization", back_populates="projects")
    environments: Mapped[List["Environment"]] = relationship("Environment", back_populates="project", cascade="all, delete-orphan")
    flags: Mapped[List["Flag"]] = relationship("Flag", back_populates="project", cascade="all, delete-orphan")
    api_keys: Mapped[List["ApiKey"]] = relationship("ApiKey", back_populates="project", cascade="all, delete-orphan")


class Environment(Base):
    __tablename__ = "environments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)  # dev, staging, prod
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    project: Mapped["Project"] = relationship("Project", back_populates="environments")

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_project_env_name"),
    )


class Flag(Base):
    __tablename__ = "flags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    default_value: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped["Project"] = relationship("Project", back_populates="flags")
    states: Mapped[List["FlagEnvState"]] = relationship("FlagEnvState", back_populates="flag", cascade="all, delete-orphan")
    rules: Mapped[List["TargetingRule"]] = relationship("TargetingRule", back_populates="flag", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("project_id", "key", name="uq_project_flag_key"),
        Index("ix_flag_project_archived", "project_id", "archived"),
    )


class FlagEnvState(Base):
    """
    Per-environment flag state.
    - enabled: Emergency Kill Switch (false = immediately serve default_value)
    - percentage: Canary / Gradual rollout (0-100)
    - version: incremental counter for cache invalidation
    """
    __tablename__ = "flag_env_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    flag_id: Mapped[str] = mapped_column(String(36), ForeignKey("flags.id", ondelete="CASCADE"), nullable=False, index=True)
    env: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    percentage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    flag: Mapped["Flag"] = relationship("Flag", back_populates="states")

    __table_args__ = (
        UniqueConstraint("flag_id", "env", name="uq_flag_env_state"),
    )


class TargetingRule(Base):
    """
    Targeting rules for targeted beta testing and user segmentation.
    """
    __tablename__ = "targeting_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    flag_id: Mapped[str] = mapped_column(String(36), ForeignKey("flags.id", ondelete="CASCADE"), nullable=False, index=True)
    env: Mapped[str] = mapped_column(String(64), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    conditions_json: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)  # list of {attr, op, value}
    serve: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    flag: Mapped["Flag"] = relationship("Flag", back_populates="rules")

    __table_args__ = (
        Index("ix_flag_env_priority", "flag_id", "env", "priority"),
    )


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    env: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    prefix: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # cp_dev_xxxx
    hash: Mapped[str] = mapped_column(String(128), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped["Project"] = relationship("Project", back_populates="api_keys")

    __table_args__ = (
        Index("ix_api_key_project_env", "project_id", "env"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    org_id: Mapped[str] = mapped_column(String(36), nullable=False)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    flag_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    env: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)  # flag.created, kill_switch.toggled, rollout.updated, etc.
    before: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    after: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
