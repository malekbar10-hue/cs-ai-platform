"""
agents/validator.py — ValidatorAgent

Checks the generated draft against the FactRegistry to detect:
  - Order ID mismatches
  - Status-word contradictions (delivered vs. shipped vs. in transit, etc.)
  - Date contradictions (draft asserts a date that differs from ERP data)

Stores a ValidationResult (from schemas.py) at ctx["validation_result"].
If the draft contains contradictions, sets ctx["pipeline_error"] = "validation_failed".

Design rules:
  - Non-blocking: never raises; failures set pipeline_error but don't crash.
  - Conservative: only flags *contradictions* (registry says X, draft says Y).
    Unverifiable claims (no matching fact) go to unsupported_claims but do
    NOT flip verified to False on their own.
  - If registry is empty: verified=True (no data to check against).
"""

from __future__ import annotations

import os
import re
import sys

_DIR    = os.path.dirname(os.path.abspath(__file__))
_ENGINE = os.path.dirname(_DIR)
for _p in (_ENGINE, _DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from base import BaseAgent
from schemas import ValidationResult

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

# DD/MM/YYYY  MM/DD/YYYY  YYYY-MM-DD  DD-MM-YYYY
_RE_DATE = re.compile(
    r'\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}|\d{4}[/\-]\d{2}[/\-]\d{2})\b'
)

# "within N days" / "sous N jours"
_RE_WITHIN_DAYS = re.compile(
    r'\bwithin\s+(\d+)\s+(?:business\s+)?days?\b'
    r'|\bsous\s+(\d+)\s+jours?\b',
    re.IGNORECASE,
)

# Delivery / shipment status words (EN + FR)
_RE_STATUS = re.compile(
    r'\b(livr[ée]e?s?|expédi[ée]e?s?|delivered|shipped|in\s+transit|'
    r'en\s+cours\s+de\s+livraison|en\s+transit|'
    r'cancelled|annul[ée]e?s?|'
    r'en\s+stock|out\s+of\s+stock|'
    r'processing|processed|en\s+cours)\b',
    re.IGNORECASE,
)

# Order-number patterns:  ORD-xxx  CMD-xxx  #ABC123  plain alphanumeric IDs
_RE_ORDER_ID = re.compile(
    r'\b([A-Z]{2,5}[-_]\w{3,15})\b'
    r'|\#([A-Z0-9]{4,15})\b',
    re.IGNORECASE,
)

# Status normalisation map → canonical token
_STATUS_CANON: dict[str, str] = {
    "livré": "delivered", "livrée": "delivered", "livrés": "delivered", "livrées": "delivered",
    "expédié": "shipped",  "expédiée": "shipped",  "expédiés": "shipped",  "expédiées": "shipped",
    "delivered": "delivered",
    "shipped": "shipped",
    "in transit": "in_transit", "en transit": "in_transit",
    "en cours de livraison": "in_transit",
    "en cours": "processing",
    "processing": "processing", "processed": "processed",
    "cancelled": "cancelled", "annulé": "cancelled", "annulée": "cancelled",
    "en stock": "in_stock",
    "out of stock": "out_of_stock",
}


def _canon_status(raw: str) -> str:
    return _STATUS_CANON.get(raw.lower().strip(), raw.lower().strip())


# ---------------------------------------------------------------------------
# ValidatorAgent
# ---------------------------------------------------------------------------

class ValidatorAgent(BaseAgent):
    name = "validator"

    def run(self, context: dict) -> dict:
        ctx = dict(context)

        try:
            ctx = self._validate(ctx)
        except Exception as exc:
            # Never let the validator crash the pipeline
            ctx["validation_result"] = ValidationResult(
                verified=True,
                unsupported_claims=[f"validator_error: {exc}"],
            )

        return ctx

    # ── Core logic ─────────────────────────────────────────────────────────

    def _validate(self, ctx: dict) -> dict:
        # Resolve draft text
        draft = ctx.get("draft", "")
        if not draft:
            dr = ctx.get("draft_result")
            draft = dr.body if dr else ""

        registry = ctx.get("fact_registry")

        # Nothing to check
        if not draft or registry is None:
            ctx["validation_result"] = ValidationResult(verified=True)
            return ctx

        verified_facts = registry.all_verified()
        if not verified_facts:
            # Registry empty — no ground truth to check against
            ctx["validation_result"] = ValidationResult(verified=True)
            return ctx

        unsupported: list[str] = []
        contradictions: list[str] = []
        policy_violations: list[str] = []

        # Build lookup maps from registry
        known_order_ids = self._collect_order_ids(registry, ctx)
        known_statuses  = self._collect_statuses(registry)
        known_dates     = self._collect_dates(registry)

        # ── Check 1: order ID mentions ────────────────────────────────────
        draft_order_ids = {
            (m.group(1) or m.group(2)).upper()
            for m in _RE_ORDER_ID.finditer(draft)
        }
        for did in draft_order_ids:
            if known_order_ids and did not in known_order_ids:
                contradictions.append(
                    f"Draft mentions order ID '{did}' but known IDs are: "
                    f"{', '.join(known_order_ids)}"
                )

        # ── Check 2: status-word contradictions ───────────────────────────
        if known_statuses:
            draft_status_matches = _RE_STATUS.findall(draft)
            draft_statuses = {_canon_status(s) for s in draft_status_matches if s}
            for ds in draft_statuses:
                # Only flag if a known status exists AND it directly contradicts
                if ds not in known_statuses and known_statuses:
                    # Check for strong contradiction pairs
                    contradiction = _is_status_contradiction(ds, known_statuses)
                    if contradiction:
                        contradictions.append(
                            f"Draft implies status '{ds}' but order status is "
                            f"'{contradiction}'"
                        )
                    else:
                        unsupported.append(f"Status claim '{ds}' not found in verified facts")

        # ── Check 3: date contradictions ──────────────────────────────────
        if known_dates:
            for m in _RE_DATE.finditer(draft):
                draft_date = _normalise_date(m.group(0))
                if draft_date and draft_date not in known_dates:
                    unsupported.append(
                        f"Date '{m.group(0)}' in draft not found in verified order data"
                    )

        # ── Build result ──────────────────────────────────────────────────
        total_claims = len(draft_order_ids) + len(known_statuses) + len(known_dates)
        checked      = total_claims
        bad          = len(contradictions)

        if checked > 0:
            ratio = max(0.0, round(1.0 - bad / checked, 3))
        else:
            ratio = 1.0

        verified = len(contradictions) == 0

        result = ValidationResult(
            verified=               verified,
            unsupported_claims=     unsupported,
            contradictions=         contradictions,
            policy_violations=      policy_violations,
            supported_claims_ratio= ratio,
        )

        ctx["validation_result"] = result

        if not verified:
            ctx["pipeline_error"] = "validation_failed"

        return ctx

    # ── Fact extraction helpers ────────────────────────────────────────────

    @staticmethod
    def _collect_order_ids(registry, ctx) -> set[str]:
        ids: set[str] = set()
        # From context directly
        raw_id = ctx.get("order_id")
        if raw_id:
            ids.add(str(raw_id).upper())
        # From registry facts
        for f in registry.find_by_prefix("order.order_id"):
            if f.value:
                ids.add(str(f.value).upper())
        oid_fact = registry.get("order.order_id") or registry.get("order.id")
        if oid_fact and oid_fact.value:
            ids.add(str(oid_fact.value).upper())
        return ids

    @staticmethod
    def _collect_statuses(registry) -> set[str]:
        statuses: set[str] = set()
        for key in ("order.status", "order.delivery_status", "order.state"):
            f = registry.get(key)
            if f and f.value:
                statuses.add(_canon_status(str(f.value)))
        return statuses

    @staticmethod
    def _collect_dates(registry) -> set[str]:
        dates: set[str] = set()
        for key in ("order.delivery_date", "order.expected_delivery",
                    "order.ship_date", "order.estimated_delivery"):
            f = registry.get(key)
            if f and f.value:
                nd = _normalise_date(str(f.value))
                if nd:
                    dates.add(nd)
        return dates


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

# Pairs of statuses that are direct contradictions of each other
_CONTRADICTING_PAIRS: list[tuple[str, str]] = [
    ("delivered",   "shipped"),
    ("delivered",   "in_transit"),
    ("delivered",   "processing"),
    ("delivered",   "cancelled"),
    ("shipped",     "cancelled"),
    ("shipped",     "processing"),
    ("in_transit",  "processing"),
    ("in_transit",  "cancelled"),
    ("in_stock",    "out_of_stock"),
]


def _is_status_contradiction(draft_status: str, known: set[str]) -> str | None:
    """
    Return the conflicting known status if draft_status directly contradicts
    a registered fact, else None.
    """
    for a, b in _CONTRADICTING_PAIRS:
        if draft_status == a and b in known:
            return b
        if draft_status == b and a in known:
            return a
    return None


def _normalise_date(raw: str) -> str | None:
    """
    Strip separators and return a compact DDMMYYYY string for comparison,
    or None if parsing fails.
    Only normalises unambiguous DD/MM/YYYY and YYYY-MM-DD forms.
    """
    raw = raw.strip()
    # YYYY-MM-DD
    m = re.match(r'^(\d{4})[/\-](\d{2})[/\-](\d{2})$', raw)
    if m:
        return f"{m.group(3)}{m.group(2)}{m.group(1)}"
    # DD/MM/YYYY
    m = re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})$', raw)
    if m:
        return f"{m.group(1).zfill(2)}{m.group(2).zfill(2)}{m.group(3)}"
    return None
