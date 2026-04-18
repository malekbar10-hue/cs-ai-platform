"""
fact_registry.py — In-process registry of ground-truth facts drawn from ERP,
CRM, email, KB, and derived sources.

Facts are the only things the ResponseAgent is permitted to state with
certainty.  The ValidatorAgent checks the generated draft against this
registry and flags any claim it cannot support.
"""

from __future__ import annotations

import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Fact(BaseModel):
    model_config = ConfigDict(strict=True)

    key:         str
    value:       str | int | float | bool | None
    source_type: Literal["erp", "crm", "email", "attachment", "kb", "derived"]
    source_ref:  str
    verified:    bool = False
    observed_at: str
    ttl_s:       int  = 3600
    sensitivity: Literal["public", "internal", "pii", "restricted"] = "internal"

    def is_expired(self) -> bool:
        try:
            obs = datetime.datetime.fromisoformat(self.observed_at)
            age = (datetime.datetime.utcnow() - obs).total_seconds()
            return age > self.ttl_s
        except Exception:
            return False


class FactRegistry:
    """In-memory store of Fact objects, keyed by fact.key."""

    def __init__(self) -> None:
        self._facts: dict[str, Fact] = {}

    def register(self, fact: Fact) -> None:
        self._facts[fact.key] = fact

    def get(self, key: str) -> Fact | None:
        f = self._facts.get(key)
        if f and f.is_expired():
            return None
        return f

    def all_verified(self) -> list[Fact]:
        return [
            f for f in self._facts.values()
            if f.verified and not f.is_expired()
        ]

    def to_context_string(self) -> str:
        """Return a compact text block for injection into the system prompt."""
        lines = [
            f"[{f.source_type.upper()}] {f.key}: {f.value}"
            for f in self.all_verified()
        ]
        return "\n".join(lines) if lines else "(no verified facts)"

    # ── Lookup helpers used by ValidatorAgent ──────────────────────────────

    def get_value(self, key: str):
        """Return the value of a verified, non-expired fact, or None."""
        f = self.get(key)
        return f.value if (f and f.verified) else None

    def find_by_prefix(self, prefix: str) -> list[Fact]:
        """Return all verified facts whose key starts with prefix."""
        return [
            f for f in self.all_verified()
            if f.key.startswith(prefix)
        ]
