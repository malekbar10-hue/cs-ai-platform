"""
agents/fact_builder.py — FactBuilder

Reads structured data already in context (order_info from ERP, customer
profile from CRM) and registers each field as a verified Fact.

The resulting FactRegistry is stored at ctx["fact_registry"].
A compact text representation is stored at ctx["verified_facts_context"]
for injection into the ResponseAgent's system prompt.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import sys

_DIR    = os.path.dirname(os.path.abspath(__file__))
_ENGINE = os.path.dirname(_DIR)
for _p in (_ENGINE, _DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from base import BaseAgent
from fact_registry import Fact, FactRegistry

log = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.datetime.utcnow().isoformat()


def _safe_str(v) -> str | int | float | bool | None:
    """Cast a value to a type Fact.value accepts; fall back to str."""
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    return str(v)


class FactBuilder(BaseAgent):
    name = "fact_builder"

    def run(self, context: dict) -> dict:
        ctx      = dict(context)
        registry = FactRegistry()
        now      = _now_iso()

        order_ref    = ctx.get("order_id", "unknown_order")
        customer_ref = ctx.get("customer_name", "unknown_customer")

        # ── ERP: fetch order via connector when available ──────────────────
        connector    = ctx.get("connector")
        order_dict: dict = {}

        if connector is not None and order_ref and order_ref != "unknown_order":
            result = connector.get_order_safe(order_ref)
            if result.ok:
                order_dict = result.data or {}
            else:
                err = result.error
                if err.kind == "fatal":
                    log.error(
                        "FactBuilder: connector fatal error fetching order %s: %s",
                        order_ref, err.message,
                    )
                    ctx["connector_fatal"] = True
                else:
                    log.warning(
                        "FactBuilder: connector degraded fetching order %s (%s): %s",
                        order_ref, err.kind, err.message,
                    )
                    ctx["connector_degraded"] = True
        else:
            # Fallback: use order_info already in context (app.py / mock path)
            order_info_raw = ctx.get("order_info", "")
            if order_info_raw:
                order_dict = _parse_order_info(order_info_raw)

        for k, v in order_dict.items():
            try:
                registry.register(Fact(
                    key=         f"order.{k}",
                    value=       _safe_str(v),
                    source_type= "erp",
                    source_ref=  str(order_ref),
                    verified=    True,
                    observed_at= now,
                ))
            except Exception:
                pass

        # ── CRM: customer profile ──────────────────────────────────────────
        profile: dict | None = None

        if connector is not None and customer_ref and customer_ref != "unknown_customer":
            result = connector.get_customer_safe(customer_ref)
            if result.ok:
                profile = result.data
            else:
                err = result.error
                if err.kind == "fatal":
                    log.error(
                        "FactBuilder: connector fatal error fetching customer %s: %s",
                        customer_ref, err.message,
                    )
                    ctx.setdefault("connector_fatal", True)
                else:
                    log.warning(
                        "FactBuilder: connector degraded fetching customer %s (%s): %s",
                        customer_ref, err.kind, err.message,
                    )
                    ctx.setdefault("connector_degraded", True)
        else:
            profile = ctx.get("profile") or ctx.get("customer_profile")

        if isinstance(profile, dict):
            for k, v in profile.items():
                try:
                    registry.register(Fact(
                        key=         f"customer.{k}",
                        value=       _safe_str(v),
                        source_type= "crm",
                        source_ref=  str(customer_ref),
                        verified=    True,
                        observed_at= now,
                    ))
                except Exception:
                    pass

        ctx["fact_registry"]          = registry
        ctx["verified_facts_context"] = registry.to_context_string()
        return ctx


# ---------------------------------------------------------------------------
# Helper: parse order_info to dict
# ---------------------------------------------------------------------------

def _parse_order_info(raw: str) -> dict:
    """
    order_info may be a JSON string, a plain "key: value" block, or empty.
    Returns a flat dict of string keys → raw values.
    """
    raw = raw.strip()
    if not raw:
        return {}

    # Try JSON first
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, ValueError):
        pass

    # Fall back: "key: value" lines
    result = {}
    for line in raw.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            k = k.strip().lower().replace(" ", "_")
            v = v.strip()
            if k:
                result[k] = v
    return result
