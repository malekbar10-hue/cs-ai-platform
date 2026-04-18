"""
pipeline.py — Thin wrapper so the eval simulator can import run_pipeline.

The simulator does: from pipeline import run_pipeline
The actual pipeline lives in agents/orchestrator.py.
"""

from __future__ import annotations

import os
import sys

_DIR    = os.path.dirname(os.path.abspath(__file__))
_AGENTS = os.path.join(_DIR, "agents")
for _p in (_DIR, _AGENTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from orchestrator import Orchestrator

_orch = Orchestrator()


def run_pipeline(ctx: dict) -> dict:
    """Run the full CS AI pipeline and return the enriched context dict."""
    ctx.setdefault("company", "default")
    ctx.setdefault("ticket", None)
    return _orch.run(ctx)
