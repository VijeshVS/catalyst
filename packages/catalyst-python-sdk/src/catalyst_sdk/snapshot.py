"""Snapshot models for the bootstrap payload."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from .evaluator import Condition, Rule


@dataclass(frozen=True)
class FlagSnapshot:
    """One flag's state for a single environment."""

    key: str
    enabled: bool = True
    enable_all: bool = False
    percentage: int = 100
    version: Optional[int] = None
    rules: List[Rule] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], version: Optional[int] = None) -> "FlagSnapshot":
        rules = [Rule.from_dict(entry) for entry in raw.get("rules") or []]
        # The server already orders rules by priority, but sort defensively so a
        # hand-edited or cached snapshot cannot evaluate out of order.
        rules.sort(key=lambda rule: rule.priority)
        return cls(
            key=str(raw.get("key") or ""),
            enabled=bool(raw.get("enabled", True)),
            enable_all=bool(raw.get("enableAll", raw.get("enable_all", False))),
            percentage=int(raw["percentage"]) if raw.get("percentage") is not None else 100,
            version=raw.get("version", version),
            rules=rules,
        )


@dataclass(frozen=True)
class Snapshot:
    """
    The full flag snapshot for one project environment.

    Immutable so it can be swapped atomically by the refresh thread while
    request threads keep evaluating against a consistent view.
    """

    env: str
    version: int = 0
    flags: Dict[str, FlagSnapshot] = field(default_factory=dict)
    etag: Optional[str] = None
    fetched_at: Optional[float] = None

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
        etag: Optional[str] = None,
        fetched_at: Optional[float] = None,
    ) -> "Snapshot":
        version = int(payload.get("version") or 0)
        raw_flags = payload.get("flags") or {}
        flags = {
            str(key): FlagSnapshot.from_dict(value, version=version)
            for key, value in raw_flags.items()
            if isinstance(value, Mapping)
        }
        return cls(
            env=str(payload.get("env") or ""),
            version=version,
            flags=flags,
            etag=etag,
            fetched_at=fetched_at,
        )

    def get(self, flag_key: str) -> Optional[FlagSnapshot]:
        return self.flags.get(flag_key)

    def __len__(self) -> int:
        return len(self.flags)


__all__ = ["Condition", "FlagSnapshot", "Rule", "Snapshot"]
