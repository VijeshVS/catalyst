import uuid
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def generate_uuid() -> str:
    """Return a stable UUID representation for string-backed primary keys."""
    return str(uuid.uuid4())


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # Nullable only to keep legacy Phase 1 organizations readable during the
    # one-time schema transition. New organizations always set an owner.
    owner_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    owner: Mapped[Optional["User"]] = relationship("User", back_populates="organizations")
    projects: Mapped[List["Project"]] = relationship(
        "Project",
        back_populates="organization",
        cascade="all, delete-orphan",
    )


class User(Base):
    """An authenticated Catalyst account.

    A user can own more than one organization.  The original Phase 1 model
    represented a user as belonging to one organization; authentication needs
    the reverse ownership relation so the same account can manage several
    organizations without duplicating the User table.
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    # Keep the Phase 1 physical column name for a painless existing-database
    # transition while exposing the clearer roadmap-facing attribute.
    hashed_password: Mapped[str] = mapped_column("password_hash", String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    organizations: Mapped[List["Organization"]] = relationship(
        "Organization",
        back_populates="owner",
        cascade="all, delete-orphan",
    )

    @property
    def password_hash(self) -> str:
        """Compatibility alias for the Phase 1 physical column name."""
        return self.hashed_password

    @password_hash.setter
    def password_hash(self, value: str) -> None:
        self.hashed_password = value


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    org_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    organization: Mapped["Organization"] = relationship("Organization", back_populates="projects")
    environments: Mapped[List["Environment"]] = relationship(
        "Environment",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    flags: Mapped[List["Flag"]] = relationship(
        "Flag",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    api_keys: Mapped[List["ApiKey"]] = relationship(
        "ApiKey",
        back_populates="project",
        cascade="all, delete-orphan",
    )


class Environment(Base):
    __tablename__ = "environments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)  # dev, staging, prod
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped["Project"] = relationship("Project", back_populates="environments")

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_project_env_name"),
    )


class Flag(Base):
    __tablename__ = "flags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    project: Mapped["Project"] = relationship("Project", back_populates="flags")
    states: Mapped[List["FlagEnvState"]] = relationship(
        "FlagEnvState",
        back_populates="flag",
        cascade="all, delete-orphan",
    )
    rules: Mapped[List["TargetingRule"]] = relationship(
        "TargetingRule",
        back_populates="flag",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("project_id", "key", name="uq_project_flag_key"),
    )


class FlagEnvState(Base):
    """Per-environment flag state.

    Two switches, in priority order: ``enabled`` is the Emergency Kill Switch
    (off means nobody), and ``enable_all`` is "enable to all users" (on means
    everybody, with no targeting).  ``percentage`` is then the share of the
    remaining eligible population that receives the feature, so 0 serves
    nobody and 100 serves everybody.  The state version is retained for
    compatibility with existing clients; the environment version drives the
    bootstrap ETag.
    """

    __tablename__ = "flag_env_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    flag_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("flags.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    env: Mapped[str] = mapped_column(String(64), nullable=False)
    # The Emergency Kill Switch. Off means nobody gets the feature.
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # "Enable to all users". On means everybody does, with no targeting at all.
    enable_all: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # The share of eligible users who receive the feature, so 0 serves nobody.
    percentage: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Bumped on every state mutation, kill switch and rollout alike, so
    # "when did this rollout last move" is answerable.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    flag: Mapped["Flag"] = relationship("Flag", back_populates="states")

    __table_args__ = (
        UniqueConstraint("flag_id", "env", name="uq_flag_env_state"),
    )


class TargetingRule(Base):
    """Targeting rules for targeted beta testing and user segmentation."""

    __tablename__ = "targeting_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    flag_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("flags.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    env: Mapped[str] = mapped_column(String(64), nullable=False)
    # An operator-facing label. Optional: an unnamed rule reads as "Rule #3".
    name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    conditions_json: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)
    serve: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    flag: Mapped["Flag"] = relationship("Flag", back_populates="rules")

    __table_args__ = (
        Index("ix_flag_env_priority", "flag_id", "env", "priority"),
    )


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    env: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    prefix: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
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
    # ``actor`` is retained for backwards compatibility with Phase 1 clients;
    # authenticated writes now populate both actor and the normalized email.
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    before: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    after: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
