"""
connector_base.py — Typed error envelopes for connector calls.

ConnectorError  — describes what went wrong (kind, code, message, retry hints)
ConnectorResult — wraps a successful data payload or a ConnectorError

Usage:
    result = connector.get_order_safe("ORD-001")
    if result.ok:
        process(result.data)
    elif result.error.kind == "fatal":
        ctx["connector_fatal"] = True
    else:
        ctx["connector_degraded"] = True
"""

from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ConnectorError(BaseModel):
    model_config = ConfigDict(strict=True)

    kind:                Literal["retryable", "fatal", "auth", "rate_limit", "policy", "timeout"]
    code:                str
    message:             str
    retry_after_s:       int | None = None
    upstream_request_id: str | None = None


class ConnectorResult(BaseModel, Generic[T]):
    model_config = ConfigDict(strict=True)

    status:               Literal["ok", "error"]
    request_id:           str
    data:                 T | None = None
    error:                ConnectorError | None = None
    freshness_expires_at: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok" and self.data is not None


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------

def make_ok(data: T, request_id: str, expires_at: str | None = None) -> ConnectorResult[T]:
    return ConnectorResult(
        status="ok",
        request_id=request_id,
        data=data,
        freshness_expires_at=expires_at,
    )


def make_error(
    kind: str,
    code: str,
    message: str,
    request_id: str,
    retry_after_s: int | None = None,
) -> ConnectorResult:
    return ConnectorResult(
        status="error",
        request_id=request_id,
        error=ConnectorError(
            kind=kind,
            code=code,
            message=message,
            retry_after_s=retry_after_s,
        ),
    )
