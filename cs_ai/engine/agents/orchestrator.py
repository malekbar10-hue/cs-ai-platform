"""
agents/orchestrator.py — Orchestrator

Runs the full pipeline:
  1. TriageAgent      — NLP, order lookup, route determination
  2. FactBuilder      — builds FactRegistry from ERP/CRM data; injects verified_facts_context
  3. ResponseAgent    — system prompt (with verified facts), KB/history, AI call, confidence
  4. QAAgent          — draft review (pass / needs_revision)
     Retry loop       — if QA says needs_revision AND retry_count < _MAX_RETRIES,
                        re-run ResponseAgent with qa_feedback injected, then QA again
  5. ValidatorAgent   — fact-checks draft against FactRegistry; sets decision="block" on contradiction
  6. DraftGuardAgent  — content completeness check against config checklist

Per-agent timings are recorded in context["pipeline_timings"]:
  {
    "triage":          float,   # seconds
    "response":        float,
    "qa":              float,
    "response_retry1": float,   # if retried
    "qa_retry1":       float,
    ...
  }
"""

import os
import sys
import time
import uuid

_DIR    = os.path.dirname(os.path.abspath(__file__))
_ENGINE = os.path.dirname(_DIR)
for _p in (_ENGINE, _DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from triage        import TriageAgent
from response      import ResponseAgent
from qa            import QAAgent
from draft_guard   import DraftGuardAgent
from fact_builder  import FactBuilder
from validator     import ValidatorAgent
from state_machine import StateMachine, TicketState, InvalidTransitionError
from schemas         import TriageResult, DraftResponse, QAResult, ValidationResult, DecisionResult
from policy_engine   import PolicyEngine
from fallback_engine import FallbackTemplateEngine
import pydantic

_MAX_RETRIES = 2


class Orchestrator:
    def __init__(self):
        self._triage        = TriageAgent()
        self._fact_builder  = FactBuilder()
        self._response      = ResponseAgent()
        self._qa            = QAAgent()
        self._validator     = ValidatorAgent()
        self._draft_guard   = DraftGuardAgent()
        self._sm            = StateMachine()
        self._policy        = PolicyEngine()
        self._fallback      = FallbackTemplateEngine()

    # ── Schema validation helper ───────────────────────────────────────────

    @staticmethod
    def _validate_typed(ctx: dict, key: str, model_cls) -> None:
        """
        Re-validate the typed result stored at ctx[key] against its Pydantic model.
        On ValidationError: log at ERROR level and set ctx['pipeline_error'].
        """
        obj = ctx.get(key)
        if obj is None:
            return
        try:
            model_cls.model_validate(obj)
        except pydantic.ValidationError as exc:
            msg = f"[ERROR] Schema validation failed for {key}: {exc}"
            print(msg)
            ctx["pipeline_error"] = msg

    # ── State machine helper ───────────────────────────────────────────────

    def _sm_goto(self, ticket, to_state: TicketState) -> None:
        """Apply a state transition. Logs a warning on invalid transitions; never raises."""
        if ticket is None:
            return
        try:
            self._sm.goto(ticket, to_state)
        except InvalidTransitionError as exc:
            print(f"[WARNING] StateMachine: {exc}")

    @staticmethod
    def _persist_state(ticket) -> None:
        """Flush state/version/state_history/retry_count to the DB."""
        if ticket is None:
            return
        try:
            from tickets import TicketManager as _TM
            _TM().update_ticket(
                ticket.ticket_id,
                state=         ticket.state,
                version=       ticket.version,
                state_history= ticket.state_history,
                retry_count=   ticket.retry_count,
            )
        except Exception as exc:
            print(f"[WARNING] StateMachine persist failed: {exc}")

    # ── Pipeline ───────────────────────────────────────────────────────────

    def run(self, context: dict) -> dict:
        """
        Execute Triage → Response → QA pipeline.
        Returns the fully enriched context dict.
        """
        ctx = dict(context)
        ctx.setdefault("pipeline_timings", {})
        ctx.setdefault("retry_count", 0)
        ctx.setdefault("run_id", str(uuid.uuid4()))

        ticket = ctx.get("ticket")   # Ticket object — present in inbox mode, None in app.py

        # ── 1. Triage ──────────────────────────────────────────────────────
        t0  = time.perf_counter()
        try:
            ctx = self._triage(ctx)
            ctx["pipeline_timings"]["triage"] = round(time.perf_counter() - t0, 3)
            self._validate_typed(ctx, "triage_result", TriageResult)
            self._triage._trace_step(ctx, "triage", t0)
        except Exception as _exc:
            self._triage._trace_step(ctx, "triage", t0, status="error", error_code=type(_exc).__name__)
            raise

        # Short-circuit: noise detected — skip Response and QA entirely
        if ctx.get("route") == "noise":
            self._triage._trace_step(ctx, "triage_noise_exit", t0, status="skipped")
            self._sm_goto(ticket, TicketState.NOISE)
            self._persist_state(ticket)
            return ctx

        # ── 2. Fact Builder — builds FactRegistry from ERP/CRM data ──────────
        t0  = time.perf_counter()
        try:
            ctx = self._fact_builder(ctx)
            ctx["pipeline_timings"]["fact_builder"] = round(time.perf_counter() - t0, 3)
            self._fact_builder._trace_step(ctx, "fact_builder", t0)
        except Exception as _exc:
            self._fact_builder._trace_step(ctx, "fact_builder", t0, status="error", error_code=type(_exc).__name__)
            raise

        # Connector fatal → route to review, skip Response/QA/Validator
        if ctx.get("connector_fatal"):
            ctx.setdefault("route", "review")
            ctx.setdefault("pipeline_error", "connector_fatal")
            print("[ERROR] Orchestrator: connector fatal — routing ticket to review queue.")
            return ctx

        # Connector degraded → lower data_completeness confidence
        if ctx.get("connector_degraded"):
            _conf = ctx.get("confidence")
            if isinstance(_conf, dict):
                _conf["data_completeness"] = min(_conf.get("data_completeness", 1.0), 0.4)
            print("[WARNING] Orchestrator: connector degraded — confidence.data_completeness capped at 0.4.")

        # Advance: NEW → TRIAGED → FACTS_BUILT
        self._sm_goto(ticket, TicketState.TRIAGED)
        self._sm_goto(ticket, TicketState.FACTS_BUILT)
        self._persist_state(ticket)

        # ── 3. Response + QA (with retry loop) ────────────────────────────
        for attempt in range(_MAX_RETRIES + 1):
            ctx["retry_count"] = attempt
            if ticket:
                ticket.retry_count = attempt

            r_label = "response" if attempt == 0 else f"response_retry{attempt}"
            t0  = time.perf_counter()
            try:
                ctx = self._response(ctx)
                ctx["pipeline_timings"][r_label] = round(time.perf_counter() - t0, 3)
                self._validate_typed(ctx, "draft_result", DraftResponse)
                self._response._trace_step(ctx, r_label, t0)
            except Exception as _exc:
                self._response._trace_step(ctx, r_label, t0, status="error", error_code=type(_exc).__name__)
                raise

            # Advance: FACTS_BUILT → DRAFTED  (or REVIEW → DRAFTED on retry)
            self._sm_goto(ticket, TicketState.DRAFTED)

            q_label = "qa" if attempt == 0 else f"qa_retry{attempt}"
            t0  = time.perf_counter()
            try:
                ctx = self._qa(ctx)
                ctx["pipeline_timings"][q_label] = round(time.perf_counter() - t0, 3)
                self._validate_typed(ctx, "qa_result_typed", QAResult)
                self._qa._trace_step(ctx, q_label, t0)
            except Exception as _exc:
                self._qa._trace_step(ctx, q_label, t0, status="error", error_code=type(_exc).__name__)
                raise

            if ctx.get("qa_result") == "pass" or attempt >= _MAX_RETRIES:
                if ctx.get("qa_result") == "pass":
                    # Advance: DRAFTED → SELF_REVIEWED → VALIDATED → QA_PASSED
                    self._sm_goto(ticket, TicketState.SELF_REVIEWED)
                    self._sm_goto(ticket, TicketState.VALIDATED)
                    self._sm_goto(ticket, TicketState.QA_PASSED)
                self._persist_state(ticket)
                break
            else:
                # QA failed, will retry — move to REVIEW then back to DRAFTED
                self._sm_goto(ticket, TicketState.REVIEW)
                self._persist_state(ticket)

        # ── 5. Validator — fact-check draft against FactRegistry ─────────
        t0  = time.perf_counter()
        try:
            ctx = self._validator(ctx)
            ctx["pipeline_timings"]["validator"] = round(time.perf_counter() - t0, 3)
            self._validate_typed(ctx, "validation_result", ValidationResult)
            self._validator._trace_step(ctx, "validator", t0)
        except Exception as _exc:
            self._validator._trace_step(ctx, "validator", t0, status="error", error_code=type(_exc).__name__)
            raise

        # Block pipeline if validator detected contradictions
        _vr = ctx.get("validation_result")
        if _vr is not None and not _vr.verified:
            ctx.setdefault("decision", "block")
            # Contradictions reported in pipeline_error (set by ValidatorAgent)

        # ── 6. PolicyEngine — enforce business rules ──────────────────────
        t0             = time.perf_counter()
        policy_decision = self._policy.evaluate(ctx)
        ctx["pipeline_timings"]["policy"] = round(time.perf_counter() - t0, 3)
        ctx["policy_decision"] = policy_decision

        if not policy_decision.passed:
            if "block" in policy_decision.required_actions:
                ctx["decision"] = "block"
                try:
                    ctx["decision_result"] = DecisionResult(
                        action="block",
                        reason=f"Policy violations: {', '.join(policy_decision.violations)}",
                        required_human_review=True,
                        blocked_by=policy_decision.violations,
                    )
                except Exception:
                    pass
            elif "review" in policy_decision.required_actions:
                ctx.setdefault("decision", "review")
                try:
                    ctx["decision_result"] = DecisionResult(
                        action="review",
                        reason=f"Policy requires review: {', '.join(policy_decision.violations)}",
                        required_human_review=True,
                        blocked_by=policy_decision.violations,
                    )
                except Exception:
                    pass

        # ── 7. Fallback draft — safe template when pipeline is blocked ────
        # Only for non-hallucination blocks (validator contradictions already
        # have a draft; fallback covers connector errors, policy, low-confidence).
        _is_validator_block = (
            ctx.get("pipeline_error") == "validation_failed"
            and ctx.get("decision") == "block"
        )
        _needs_fallback = (
            ctx.get("decision") in ("block", "review")
            and not _is_validator_block
            and not ctx.get("used_fallback")
        )
        if _needs_fallback:
            try:
                _fb_reason            = self._fallback.reason_for(ctx)
                ctx["fallback_draft"] = self._fallback.render(_fb_reason, ctx)
                ctx["used_fallback"]  = True
                ctx["fallback_reason"]= _fb_reason
            except Exception as _exc:
                print(f"[WARNING] FallbackEngine: {_exc}")

        # Auto-send fallback only when config explicitly opts in
        if ctx.get("used_fallback"):
            self._sm_goto(ticket, TicketState.FALLBACK_DRAFT)
            self._persist_state(ticket)
            _fb_cfg     = (ctx.get("config") or {}).get("fallback", {})
            _auto_send  = _fb_cfg.get("auto_send", False)
            if not _auto_send:
                ctx.setdefault("decision", "review")

        # ── 8. Draft Guard (content completeness — non-blocking) ──────────
        t0  = time.perf_counter()
        try:
            ctx = self._draft_guard(ctx)
            ctx["pipeline_timings"]["draft_guard"] = round(time.perf_counter() - t0, 3)
            self._draft_guard._trace_step(ctx, "draft_guard", t0)
        except Exception as _exc:
            self._draft_guard._trace_step(ctx, "draft_guard", t0, status="error", error_code=type(_exc).__name__)
            raise

        # Advance: QA_PASSED → READY (only if QA passed and not blocked)
        if (
            ticket
            and ticket.state == TicketState.QA_PASSED.value
            and ctx.get("decision") != "block"
        ):
            self._sm_goto(ticket, TicketState.READY)
            self._persist_state(ticket)

        ctx["pipeline_timings"]["total"] = round(
            sum(v for k, v in ctx["pipeline_timings"].items() if k != "total"), 3
        )
        return ctx
