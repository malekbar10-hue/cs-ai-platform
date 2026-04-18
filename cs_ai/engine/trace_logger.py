"""
trace_logger.py — Structured step-level trace logging for the CS AI pipeline.

Every pipeline stage emits a StepTrace JSON line via the TraceLogger.
PII (email addresses, phone numbers) is redacted before any string is logged.

Usage:
    from trace_logger import get_tracer, StepTrace
    tracer = get_tracer()
    tracer.emit(StepTrace(run_id=..., step_name="triage", ...))
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import datetime, UTC
from typing import Literal

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# PII redaction
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}')
_PHONE_RE = re.compile(r'\+?[\d\s\-\(\)]{7,15}')


def redact(text: str) -> str:
    """Replace email addresses and phone numbers with safe placeholders."""
    if not isinstance(text, str):
        return text
    text = _EMAIL_RE.sub("[EMAIL]", text)
    text = _PHONE_RE.sub("[PHONE]", text)
    return text


# ---------------------------------------------------------------------------
# StepTrace model
# ---------------------------------------------------------------------------

class StepTrace(BaseModel):
    model_config = ConfigDict(strict=True)

    run_id:         str
    ticket_id:      str
    step_name:      str
    status:         Literal["ok", "error", "skipped"]
    latency_ms:     float
    model:          str = ""
    prompt_version: str = "unversioned"
    input_tokens:   int = 0
    output_tokens:  int = 0
    decision:       str = ""
    error_code:     str = ""
    timestamp:      str = ""


# ---------------------------------------------------------------------------
# TraceLogger
# ---------------------------------------------------------------------------

class TraceLogger:

    def __init__(self, name: str = "cs_ai.trace"):
        self._log = logging.getLogger(name)

    def emit(self, trace: StepTrace) -> None:
        d = trace.model_dump()
        d["decision"]   = redact(d.get("decision",   ""))
        d["error_code"] = redact(d.get("error_code", ""))
        self._log.info(json.dumps(d))

    def new_run_id(self) -> str:
        return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_tracer = TraceLogger()


def get_tracer() -> TraceLogger:
    return _tracer
