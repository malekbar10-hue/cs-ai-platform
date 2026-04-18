"""
cs_ai/engine/pipeline.py — Single callable entry point for the eval harness and tests.

Wraps Orchestrator.run() so external code (evals, smoke tests, integrations)
never has to import Orchestrator directly.
"""

from __future__ import annotations

import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
_AGENTS = os.path.join(_DIR, "agents")
for _p in (_DIR, _AGENTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from orchestrator import Orchestrator   # noqa: E402

_orchestrator: Orchestrator | None = None


def _get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator


def run_pipeline(context: dict) -> dict:
    """
    Execute the full CS AI pipeline and return the enriched context dict.

    Expected input keys:
        user_input      str   — the customer message
        customer_email  str   — sender address
        company         str   — company slug (default: "default")
        ticket          Ticket | None
        session_id      str

    Returns context enriched with (among others):
        route           str   — auto | standard | priority | supervisor | noise
        draft           str   — the AI-generated response text
        decision        str   — send | review | block
        intent          str   — NLP-detected intent
        confidence      dict  — per-dimension confidence scores
    """
    ctx = dict(context)
    ctx.setdefault("company", "default")
    ctx.setdefault("ticket", None)
    return _get_orchestrator().run(ctx)
