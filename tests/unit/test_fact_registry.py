"""
tests/unit/test_fact_registry.py — Unit tests for FactRegistry and Fact.

No database, network, or config required.
Run with:  pytest tests/unit/test_fact_registry.py -v
"""

import sys
import os
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "cs_ai", "engine"))

import pytest
from pydantic import ValidationError
from fact_registry import Fact, FactRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.datetime.utcnow().isoformat()

def _old() -> str:
    """Timestamp 2 hours in the past — older than default TTL."""
    return (datetime.datetime.utcnow() - datetime.timedelta(hours=2)).isoformat()

def _make_fact(key="order.status", value="shipped", source_type="erp",
               source_ref="ORD-001", verified=True, observed_at=None, ttl_s=3600):
    return Fact(
        key=key, value=value, source_type=source_type, source_ref=source_ref,
        verified=verified, observed_at=observed_at or _now(), ttl_s=ttl_s,
    )


# ---------------------------------------------------------------------------
# Fact model
# ---------------------------------------------------------------------------

class TestFact:
    def test_valid_construction(self):
        f = _make_fact()
        assert f.key   == "order.status"
        assert f.value == "shipped"

    def test_invalid_source_type_raises(self):
        with pytest.raises(ValidationError):
            _make_fact(source_type="database")

    def test_invalid_sensitivity_raises(self):
        with pytest.raises(ValidationError):
            Fact(key="k", value="v", source_type="erp", source_ref="r",
                 observed_at=_now(), sensitivity="secret")

    def test_all_valid_source_types(self):
        for st in ("erp", "crm", "email", "attachment", "kb", "derived"):
            f = _make_fact(source_type=st)
            assert f.source_type == st

    def test_value_accepts_none(self):
        f = _make_fact(value=None)
        assert f.value is None

    def test_value_accepts_numeric(self):
        f = _make_fact(value=42)
        assert f.value == 42

    def test_value_accepts_bool(self):
        f = _make_fact(value=True)
        assert f.value is True

    def test_not_expired_fresh(self):
        f = _make_fact(ttl_s=3600)
        assert not f.is_expired()

    def test_expired_old_timestamp(self):
        f = _make_fact(observed_at=_old(), ttl_s=60)   # TTL 1 min, observed 2h ago
        assert f.is_expired()

    def test_not_expired_when_ttl_covers_age(self):
        # observed 2h ago but TTL is 3h
        f = _make_fact(observed_at=_old(), ttl_s=10800)
        assert not f.is_expired()

    def test_default_sensitivity_is_internal(self):
        f = _make_fact()
        assert f.sensitivity == "internal"

    def test_strict_rejects_string_for_bool(self):
        with pytest.raises(ValidationError):
            _make_fact(verified="yes")   # type: ignore


# ---------------------------------------------------------------------------
# FactRegistry
# ---------------------------------------------------------------------------

class TestFactRegistry:
    def test_register_and_get(self):
        reg = FactRegistry()
        f   = _make_fact(key="order.status", value="shipped")
        reg.register(f)
        assert reg.get("order.status") is f

    def test_get_missing_returns_none(self):
        reg = FactRegistry()
        assert reg.get("nonexistent") is None

    def test_get_expired_returns_none(self):
        reg = FactRegistry()
        f   = _make_fact(key="order.status", observed_at=_old(), ttl_s=60)
        reg.register(f)
        assert reg.get("order.status") is None

    def test_register_overwrites(self):
        reg = FactRegistry()
        reg.register(_make_fact(key="k", value="v1"))
        reg.register(_make_fact(key="k", value="v2"))
        assert reg.get("k").value == "v2"

    def test_all_verified_excludes_unverified(self):
        reg = FactRegistry()
        reg.register(_make_fact(key="k1", verified=True))
        reg.register(_make_fact(key="k2", verified=False))
        result = reg.all_verified()
        assert len(result) == 1
        assert result[0].key == "k1"

    def test_all_verified_excludes_expired(self):
        reg = FactRegistry()
        reg.register(_make_fact(key="fresh",   ttl_s=3600))
        reg.register(_make_fact(key="expired", observed_at=_old(), ttl_s=60))
        result = reg.all_verified()
        assert len(result) == 1
        assert result[0].key == "fresh"

    def test_to_context_string_empty(self):
        reg = FactRegistry()
        assert reg.to_context_string() == "(no verified facts)"

    def test_to_context_string_format(self):
        reg = FactRegistry()
        reg.register(_make_fact(key="order.status", value="shipped", source_type="erp"))
        s = reg.to_context_string()
        assert "[ERP]" in s
        assert "order.status" in s
        assert "shipped" in s

    def test_to_context_string_only_verified(self):
        reg = FactRegistry()
        reg.register(_make_fact(key="k1", value="v1", verified=True))
        reg.register(_make_fact(key="k2", value="v2", verified=False))
        s = reg.to_context_string()
        assert "k1" in s
        assert "k2" not in s

    def test_get_value_helper(self):
        reg = FactRegistry()
        reg.register(_make_fact(key="order.id", value="ORD-999"))
        assert reg.get_value("order.id") == "ORD-999"

    def test_get_value_unverified_returns_none(self):
        reg = FactRegistry()
        reg.register(_make_fact(key="order.id", value="ORD-999", verified=False))
        assert reg.get_value("order.id") is None

    def test_find_by_prefix(self):
        reg = FactRegistry()
        reg.register(_make_fact(key="order.status",       value="shipped"))
        reg.register(_make_fact(key="order.delivery_date",value="2024-05-01"))
        reg.register(_make_fact(key="customer.name",      value="Acme"))
        result = reg.find_by_prefix("order.")
        keys = {f.key for f in result}
        assert "order.status"        in keys
        assert "order.delivery_date" in keys
        assert "customer.name"       not in keys


# ---------------------------------------------------------------------------
# FactBuilder integration (no external deps needed)
# ---------------------------------------------------------------------------

class TestFactBuilder:
    def test_builds_from_order_info_json(self):
        sys.path.insert(0, os.path.join(
            os.path.dirname(__file__), "..", "..", "cs_ai", "engine", "agents"
        ))
        from fact_builder import FactBuilder, _parse_order_info

        parsed = _parse_order_info('{"order_id": "ORD-1", "status": "shipped"}')
        assert parsed["order_id"] == "ORD-1"
        assert parsed["status"]   == "shipped"

    def test_parse_order_info_key_value_lines(self):
        from fact_builder import _parse_order_info
        parsed = _parse_order_info("order_id: ORD-2\nstatus: delivered")
        assert parsed["order_id"] == "ORD-2"

    def test_parse_order_info_empty(self):
        from fact_builder import _parse_order_info
        assert _parse_order_info("") == {}

    def test_fact_builder_run_populates_registry(self):
        import json
        from fact_builder import FactBuilder
        agent = FactBuilder()
        ctx = {
            "order_info": json.dumps({"order_id": "ORD-3", "status": "in transit"}),
            "order_id":   "ORD-3",
            "profile":    {"total_interactions": 3, "dominant_emotion": "Neutral"},
            "customer_name": "Acme",
        }
        result = agent.run(ctx)
        reg = result["fact_registry"]
        assert reg.get_value("order.order_id") == "ORD-3"
        assert reg.get_value("order.status")   == "in transit"
        assert reg.get_value("customer.total_interactions") == 3

    def test_fact_builder_sets_verified_facts_context(self):
        import json
        from fact_builder import FactBuilder
        agent = FactBuilder()
        ctx = {"order_info": json.dumps({"status": "shipped"}), "order_id": "X"}
        result = agent.run(ctx)
        assert "verified_facts_context" in result
        assert "shipped" in result["verified_facts_context"]
