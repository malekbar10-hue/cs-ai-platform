"""
tests/unit/test_connector_resilience.py — Unit tests for connector resilience.

No real ERP/CRM required — connector methods are monkey-patched to raise
specific exceptions, verifying that get_order_safe() returns the correct
ConnectorResult envelope.

Run with:  pytest tests/unit/test_connector_resilience.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "cs_ai", "engine"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "cs_ai", "engine", "agents"))

import pytest
from connector_base import ConnectorResult, ConnectorError, make_ok, make_error
from connector import JSONConnector, _classify_exception


# ---------------------------------------------------------------------------
# Helpers — minimal stub connector
# ---------------------------------------------------------------------------

from connector import BaseConnector as _BaseConnector


class _StubConnector(_BaseConnector):
    """Minimal stand-in — inherits safe wrappers from BaseConnector."""

    def __init__(self, raises=None, returns=None):
        self._raises  = raises
        self._returns = returns

    def get_order(self, order_id):
        if self._raises:
            raise self._raises
        return self._returns

    def get_customer_profile(self, customer_name):
        if self._raises:
            raise self._raises
        return self._returns

    # Satisfy remaining abstract-like stubs (unused in these tests)
    def list_order_ids(self):          return []
    def update_order(self, *a):        return False
    def get_logs(self):                return []
    def save_log(self, e):             pass
    def get_all_profiles(self):        return {}
    def update_customer_profile(self, *a): pass


# ---------------------------------------------------------------------------
# ConnectorError / ConnectorResult model
# ---------------------------------------------------------------------------

class TestConnectorModels:
    def test_make_ok_sets_ok_true(self):
        r = make_ok({"order_id": "X"}, "req-1")
        assert r.ok is True
        assert r.status == "ok"
        assert r.data == {"order_id": "X"}
        assert r.error is None

    def test_make_error_sets_ok_false(self):
        r = make_error("fatal", "NOT_FOUND", "Order not found", "req-2")
        assert r.ok is False
        assert r.status == "error"
        assert r.data is None
        assert r.error.kind == "fatal"
        assert r.error.code == "NOT_FOUND"

    def test_ok_false_when_data_none(self):
        r = ConnectorResult(status="ok", request_id="x", data=None)
        assert r.ok is False

    def test_connector_error_invalid_kind_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ConnectorError(kind="network_blip", code="X", message="m")

    def test_make_error_with_retry_after(self):
        r = make_error("rate_limit", "429", "Too many requests", "req-3", retry_after_s=30)
        assert r.error.retry_after_s == 30


# ---------------------------------------------------------------------------
# _classify_exception
# ---------------------------------------------------------------------------

class TestClassifyException:
    def test_timeout_error_maps_to_timeout(self):
        r = _classify_exception(TimeoutError("timed out"), "req")
        assert r.error.kind == "timeout"
        assert r.error.code == "TIMEOUT"

    def test_connection_error_maps_to_retryable(self):
        r = _classify_exception(ConnectionError("refused"), "req")
        assert r.error.kind == "retryable"
        assert r.error.code == "CONN_ERROR"

    def test_permission_error_maps_to_auth(self):
        r = _classify_exception(PermissionError("forbidden"), "req")
        assert r.error.kind == "auth"
        assert r.error.code == "AUTH_ERROR"

    def test_generic_exception_maps_to_fatal(self):
        r = _classify_exception(ValueError("unexpected"), "req")
        assert r.error.kind == "fatal"
        assert r.error.code == "UNKNOWN"


# ---------------------------------------------------------------------------
# get_order_safe
# ---------------------------------------------------------------------------

class TestGetOrderSafe:
    def test_valid_data_returns_ok(self):
        stub = _StubConnector(returns={"order_id": "ORD-1", "status": "shipped"})
        r = stub.get_order_safe("ORD-1")
        assert r.ok is True
        assert r.data["order_id"] == "ORD-1"

    def test_none_result_returns_fatal(self):
        stub = _StubConnector(returns=None)
        r = stub.get_order_safe("ORD-MISSING")
        assert r.ok is False
        assert r.error.kind == "fatal"
        assert r.error.code == "NOT_FOUND"

    def test_timeout_error_returns_timeout(self):
        stub = _StubConnector(raises=TimeoutError("connection timed out"))
        r = stub.get_order_safe("ORD-1")
        assert r.ok is False
        assert r.error.kind == "timeout"

    def test_connection_error_returns_retryable(self):
        stub = _StubConnector(raises=ConnectionError("connection refused"))
        r = stub.get_order_safe("ORD-1")
        assert r.ok is False
        assert r.error.kind == "retryable"

    def test_generic_exception_returns_fatal(self):
        stub = _StubConnector(raises=RuntimeError("unexpected crash"))
        r = stub.get_order_safe("ORD-1")
        assert r.ok is False
        assert r.error.kind == "fatal"

    def test_permission_error_returns_auth(self):
        stub = _StubConnector(raises=PermissionError("401 Unauthorized"))
        r = stub.get_order_safe("ORD-1")
        assert r.ok is False
        assert r.error.kind == "auth"

    def test_result_has_request_id(self):
        stub = _StubConnector(returns={"status": "ok"})
        r = stub.get_order_safe("ORD-1")
        assert r.request_id and len(r.request_id) > 0


# ---------------------------------------------------------------------------
# get_customer_safe
# ---------------------------------------------------------------------------

class TestGetCustomerSafe:
    def test_valid_profile_returns_ok(self):
        stub = _StubConnector(returns={"name": "Acme", "tier": "gold"})
        r = stub.get_customer_safe("Acme")
        assert r.ok is True
        assert r.data["name"] == "Acme"

    def test_none_profile_returns_fatal(self):
        stub = _StubConnector(returns=None)
        r = stub.get_customer_safe("Unknown Corp")
        assert r.ok is False
        assert r.error.kind == "fatal"

    def test_timeout_returns_timeout(self):
        stub = _StubConnector(raises=TimeoutError())
        r = stub.get_customer_safe("Acme")
        assert r.error.kind == "timeout"


# ---------------------------------------------------------------------------
# FactBuilder integration — connector_fatal / connector_degraded flags
# ---------------------------------------------------------------------------

class TestFactBuilderConnectorFlags:
    def _run_fact_builder(self, connector, order_id="ORD-1", customer_name="Acme"):
        from fact_builder import FactBuilder
        agent = FactBuilder()
        ctx = {
            "order_id":      order_id,
            "customer_name": customer_name,
            "connector":     connector,
        }
        return agent.run(ctx)

    def test_fatal_order_error_sets_connector_fatal(self):
        stub = _StubConnector(raises=ValueError("db down"))
        result = self._run_fact_builder(stub)
        assert result.get("connector_fatal") is True

    def test_timeout_order_error_sets_connector_degraded(self):
        stub = _StubConnector(raises=TimeoutError("slow"))
        result = self._run_fact_builder(stub)
        assert result.get("connector_degraded") is True

    def test_ok_order_populates_registry(self):
        stub = _StubConnector(returns={"order_id": "ORD-1", "status": "shipped"})
        result = self._run_fact_builder(stub)
        reg = result["fact_registry"]
        assert reg.get_value("order.status") == "shipped"

    def test_no_connector_falls_back_to_order_info(self):
        import json
        from fact_builder import FactBuilder
        agent = FactBuilder()
        ctx = {
            "order_id":   "ORD-2",
            "order_info": json.dumps({"status": "in transit"}),
        }
        result = agent.run(ctx)
        reg = result["fact_registry"]
        assert reg.get_value("order.status") == "in transit"
