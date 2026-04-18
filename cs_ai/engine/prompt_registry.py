"""
prompt_registry.py — Version-controlled prompt store.

Every LLM prompt is stored as a JSON file in cs_ai/prompts/.
Agents retrieve prompts by ID, render them with variables, and record the
version + checksum in ctx["prompt_version"] for trace logging.

Usage:
    spec = get_registry().get("response_system")
    text = spec.render(role="Agent", company="Acme", ...)
    ctx["prompt_version"] = f"{spec.prompt_id}@{spec.version}@{spec.checksum}"
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field


@dataclass
class PromptSpec:
    prompt_id: str
    version:   str          # semver e.g. "1.0.0"
    content:   str          # template with {variable} placeholders
    variables: list[str]    = field(default_factory=list)
    changelog: str          = ""
    checksum:  str          = ""

    def __post_init__(self) -> None:
        self.checksum = hashlib.sha256(self.content.encode()).hexdigest()[:12]

    def render(self, **kwargs) -> str:
        try:
            return self.content.format(**kwargs)
        except KeyError as exc:
            raise ValueError(
                f"Missing variable {exc} for prompt {self.prompt_id}@{self.version}"
            )


class PromptRegistry:

    def __init__(self, prompts_dir: str) -> None:
        self._prompts: dict[str, PromptSpec] = {}
        self._dir = prompts_dir
        self._load_all()

    def _load_all(self) -> None:
        if not os.path.isdir(self._dir):
            return
        for fname in os.listdir(self._dir):
            if fname.endswith(".json"):
                path = os.path.join(self._dir, fname)
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
                spec = PromptSpec(**data)
                self._prompts[spec.prompt_id] = spec

    def get(self, prompt_id: str) -> PromptSpec:
        if prompt_id not in self._prompts:
            raise KeyError(f"Prompt not found: {prompt_id}")
        return self._prompts[prompt_id]

    def all_ids(self) -> list[str]:
        return sorted(self._prompts.keys())


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_registry: PromptRegistry | None = None


def get_registry() -> PromptRegistry:
    global _registry
    if _registry is None:
        _dir = os.path.join(os.path.dirname(__file__), "..", "prompts")
        _registry = PromptRegistry(os.path.abspath(_dir))
    return _registry
