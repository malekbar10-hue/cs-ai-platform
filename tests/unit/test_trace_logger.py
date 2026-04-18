"""
tests/unit/test_trace_logger.py — Unit tests for TraceLogger and helpers.

No database, network, or LLM required.
Run with:  pytest tests/unit/test_trace_logger.py -v
"""

import json
import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "cs_ai", "engine"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "cs_ai", "engine", "agents"))

import pytest
from trace_logger import redact, StepTrace, TraceLogger, get_tracer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _trace(**kwargs) -> StepTrace:
    defaults = dict(
        run_id="run-123",
        ticket_id="TKT-1",
        step_name="triage",
        status="ok",
        latency_ms=12.5,
        timestamp="2024-01-01T00:00:00+00:00",
    )
    defaults.update(kwargs)
    return StepTrace(**defaults)


class _CapturingHandler(logging.Handler):
    """Captures log records for assertion."""
    def __init__(self):
        super().__init__()
        self.records: list[str] = []

    def emit(self, record):
        self.records.append(self.format(record))


# ---------------------------------------------------------------------------
# redact()
# ---------------------------------------------------------------------------

class TestRedact:
    def test_replaces_email(self):
        result = redact("Contact us at support@example.com for help.")
        assert "[EMAIL]" in result
        assert "support@example.com" not in result

    def test_replaces_multiple_emails(self):
        result = redact("From alice@foo.com to bob@bar.org")
        assert result.count("[EMAIL]") == 2
        assert "alice" not in result
        assert "bob"   not in result

    def test_replaces_phone_international(self):
        result = redact("Call +33 6 12 34 56 78 now.")
        assert "[PHONE]" in result
        assert "+33" not in result

    def test_replaces_phone_us_format(self):
        result = redact("Reach us at (555) 123-4567.")
        assert "[PHONE]" in result

    def test_plain_text_unchanged(self):
        text = "Your order has been shipped."
        assert redact(text) == text

    def test_empty_string(self):
        assert redact("") == ""

    def test_non_string_passthrough(self):
        assert redact(None) is None  # type: ignore
        assert redact(42)   == 42    # type: ignore

    def test_email_and_phone_both_redacted(self):
        result = redact("Email: user@test.com, Phone: +1 800 555 1234")
        assert "[EMAIL]" in result
        assert "[PHONE]" in result
        assert "user@test.com" not in result


# ---------------------------------------------------------------------------
# StepTrace model
# ---------------------------------------------------------------------------

class TestStepTrace:
    def test_valid_construction(self):
        t = _trace()
        assert t.run_id     == "run-123"
        assert t.ticket_id  == "TKT-1"
        assert t.step_name  == "triage"
        assert t.status     == "ok"
        assert t.latency_ms == 12.5

    def test_invalid_status_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            _trace(status="pending")

    def test_all_valid_statuses(self):
        for s in ("ok", "error", "skipped"):
            t = _trace(status=s)
            assert t.status == s

    def test_default_fields(self):
        t = _trace()
        assert t.model          == ""
        assert t.prompt_version == "unversioned"
        assert t.input_tokens   == 0
        assert t.output_tokens  == 0
        assert t.decision       == ""
        assert t.error_code     == ""

    def test_serialises_to_dict_with_required_keys(self):
        t = _trace()
        d = t.model_dump()
        required = {
            "run_id", "ticket_id", "step_name", "status",
            "latency_ms", "model", "prompt_version",
            "input_tokens", "output_tokens",
            "decision", "error_code", "timestamp",
        }
        assert required.issubset(d.keys())

    def test_model_dump_is_json_serialisable(self):
        t = _trace(model="gpt-4o", input_tokens=100, output_tokens=200)
        assert json.dumps(t.model_dump())  # must not raise

    def test_strict_rejects_string_for_int_tokens(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            _trace(input_tokens="100")  # type: ignore


# ---------------------------------------------------------------------------
# TraceLogger.emit()
# ---------------------------------------------------------------------------

class TestTraceLoggerEmit:
    def _make_logger_with_capture(self):
        handler = _CapturingHandler()
        logger = TraceLogger(name=f"test.trace.{id(self)}")
        logger._log.addHandler(handler)
        logger._log.setLevel(logging.DEBUG)
        logger._log.propagate = False
        return logger, handler

    def test_emit_produces_valid_json(self):
        logger, handler = self._make_logger_with_capture()
        logger.emit(_trace())
        assert len(handler.records) == 1
        json.loads(handler.records[0])  # must not raise

    def test_emit_json_contains_all_keys(self):
        logger, handler = self._make_logger_with_capture()
        logger.emit(_trace(step_name="validator"))
        payload = json.loads(handler.records[0])
        assert payload["step_name"] == "validator"
        assert payload["status"]    == "ok"

    def test_emit_redacts_email_in_decision(self):
        logger, handler = self._make_logger_with_capture()
        logger.emit(_trace(decision="Sent to admin@company.com"))
        payload = json.loads(handler.records[0])
        assert "[EMAIL]" in payload["decision"]
        assert "admin@company.com" not in payload["decision"]

    def test_emit_redacts_phone_in_error_code(self):
        logger, handler = self._make_logger_with_capture()
        logger.emit(_trace(status="error", error_code="+1 555 123 4567"))
        payload = json.loads(handler.records[0])
        assert "[PHONE]" in payload["error_code"]

    def test_emit_clean_decision_unchanged(self):
        logger, handler = self._make_logger_with_capture()
        logger.emit(_trace(decision="send"))
        payload = json.loads(handler.records[0])
        assert payload["decision"] == "send"

    def test_new_run_id_is_unique(self):
        tracer = TraceLogger()
        ids = {tracer.new_run_id() for _ in range(10)}
        assert len(ids) == 10


# ---------------------------------------------------------------------------
# get_tracer() singleton
# ---------------------------------------------------------------------------

class TestGetTracer:
    def test_returns_same_instance(self):
        assert get_tracer() is get_tracer()

    def test_is_trace_logger_instance(self):
        assert isinstance(get_tracer(), TraceLogger)


# ---------------------------------------------------------------------------
# BaseAgent._trace_step integration
# ---------------------------------------------------------------------------

class TestBaseAgentTraceStep:
    def test_trace_step_does_not_raise(self):
        import time
        from base import BaseAgent

        class _NoopAgent(BaseAgent):
            name = "noop"
            def run(self, ctx):
                return ctx

        agent = _NoopAgent()
        t0    = time.perf_counter()
        # Should complete silently even with a minimal context
        agent._trace_step({"run_id": "x", "ticket_id": "T-1"}, "noop", t0)

    def test_trace_step_survives_broken_context(self):
        import time
        from base import BaseAgent

        class _NoopAgent(BaseAgent):
            name = "noop"
            def run(self, ctx):
                return ctx

        agent = _NoopAgent()
        t0    = time.perf_counter()
        agent._trace_step(None, "noop", t0)   # type: ignore — must not raise

    def test_trace_step_records_error_status(self):
        import time
        from base import BaseAgent

        captured = []

        class _InstrumentedAgent(BaseAgent):
            name = "inst"
            def run(self, ctx):
                return ctx

        agent   = _InstrumentedAgent()
        handler = _CapturingHandler()
        agent_logger = TraceLogger(name=f"test.base.{id(agent)}")
        agent_logger._log.addHandler(handler)
        agent_logger._log.setLevel(logging.DEBUG)
        agent_logger._log.propagate = False

        import trace_logger as _tl
        original = _tl._tracer
        _tl._tracer = agent_logger
        try:
            t0 = time.perf_counter()
            agent._trace_step(
                {"run_id": "r1", "ticket_id": "T-2"},
                "test_step", t0,
                status="error", error_code="ValueError",
            )
        finally:
            _tl._tracer = original

        assert len(handler.records) == 1
        payload = json.loads(handler.records[0])
        assert payload["status"]     == "error"
        assert payload["error_code"] == "ValueError"
        assert payload["step_name"]  == "test_step"
