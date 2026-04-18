"""
agents/base.py — BaseAgent contract for the CS AI pipeline.

Every agent:
  - has a `name` class attribute
  - implements `run(context: dict) -> dict` (returns enriched copy)
  - is callable via `agent(context)` shorthand
"""

import time


class BaseAgent:
    name: str = "base"

    def run(self, context: dict) -> dict:
        raise NotImplementedError(f"{self.__class__.__name__}.run() must be implemented")

    def __call__(self, context: dict) -> dict:
        return self.run(context)

    def _trace_step(
        self,
        ctx:        dict,
        step_name:  str,
        t_start:    float,
        status:     str = "ok",
        error_code: str = "",
    ) -> None:
        """Emit a StepTrace for this pipeline step. Never raises."""
        try:
            from trace_logger import StepTrace, get_tracer
            from datetime import datetime, UTC

            token_usage = ctx.get("token_usage") or {}
            trace = StepTrace(
                run_id=         ctx.get("run_id", ""),
                ticket_id=      str(ctx.get("ticket_id", "?")),
                step_name=      step_name,
                status=         status,
                latency_ms=     round((time.perf_counter() - t_start) * 1000, 1),
                model=          ctx.get("model_used", ""),
                prompt_version= ctx.get("prompt_version", "unversioned"),
                input_tokens=   int(token_usage.get("prompt_tokens",     token_usage.get("prompt",      0))),
                output_tokens=  int(token_usage.get("completion_tokens", token_usage.get("completion",   0))),
                decision=       str(ctx.get("final_decision", ctx.get("decision", "")))[:80],
                error_code=     error_code,
                timestamp=      datetime.now(UTC).isoformat(),
            )
            get_tracer().emit(trace)
        except Exception:
            pass  # trace failures must never affect the pipeline
