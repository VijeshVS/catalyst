"""Snapshot models for the bootstrap payload."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from .evaluator import Condition, Rule


@dataclass(frozen=True)
class FlagSnapshot:
    """One flag's state for a single environment."""

    key: str
    default_value: bool = False
    enabled: bool = True
    percentage: int = 0
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
            default_value=bool(raw.get("defaultValue", raw.get("default_value", False))),
            enabled=bool(raw.get("enabled", True)),
            percentage=int(raw.get("percentage") or 0),
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

    def to_dict(self) -> Dict[str, Any]:
        """Serialisable form used by the optional disk cache."""
        return {
            "env": self.env,
            "version": self.version,
            "etag": self.etag,
            "fetched_at": self.fetched_at,
            "flags": {
                key: {
                    "key": flag.key,
                    "defaultValue": flag.default_value,
                    "enabled": flag.enabled,
                    "percentage": flag.percentage,
                    "rules": [
                        {
                            "id": rule.id,
                            "priority": rule.priority,
                            "serve": rule.serve,
                            "conditions": [
                                {"attr": c.attr, "op": c.op, "value": c.value}
                                for c in rule.conditions
                            ],
                        }
                        for rule in flag.rules
                    ],
                }
                for key, flag in self.flags.items()
            },
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Snapshot":
        return cls.from_payload(raw, etag=raw.get("etag"), fetched_at=raw.get("fetched_at"))


__all__ = ["Condition", "FlagSnapshot", "Rule", "Snapshot"]
