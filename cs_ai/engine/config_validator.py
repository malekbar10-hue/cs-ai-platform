"""
config_validator.py — Startup config validation for the CS AI platform.

Validates a loaded config dict before the app or poller starts.
No file I/O — the caller is responsible for loading the dict.

Usage:
    from config_validator import ConfigValidator
    result = ConfigValidator().validate(config)
    # {"ok": bool, "errors": list[str], "warnings": list[str]}
"""

from __future__ import annotations


class ConfigValidator:
    """Validates a company config dict. Returns errors and warnings."""

    # Fields that must be present and non-empty — absence is a hard error.
    _REQUIRED: list[tuple[str, ...]] = [
        ("company", "name"),
        ("company", "agent_role"),
        ("company", "agent_signature"),
    ]

    def validate(self, config: dict) -> dict:
        errors:   list[str] = []
        warnings: list[str] = []

        # ── Required fields ────────────────────────────────────────────────
        for path in self._REQUIRED:
            val = self._get(config, *path)
            if not val:
                errors.append(f"Missing required field: {'.'.join(path)}")

        # ai.models.standard.model (separate path)
        std_model = self._get(config, "ai", "models", "standard", "model")
        if not std_model:
            errors.append("Missing required field: ai.models.standard.model")

        # sla.Normal.response_hours
        sla_normal_hours = self._get(config, "sla", "Normal", "response_hours")
        if sla_normal_hours is None:
            errors.append("Missing required field: sla.Normal.response_hours")

        # ── Optional — warn if absent ──────────────────────────────────────
        if not self._get(config, "communication", "inbound", "host"):
            warnings.append(
                "Email inbound not configured — manual mode only"
            )

        if not self._get(config, "communication", "outbound", "host"):
            warnings.append(
                "Email outbound not configured — responses cannot be sent automatically"
            )

        if not self._get(config, "erp", "endpoint"):
            warnings.append("ERP not configured — using mock data")

        if self._get(config, "confidence", "auto_send_enabled") is None:
            warnings.append("Auto-send not configured — defaulting to false")

        # ── Type checks ────────────────────────────────────────────────────
        errors.extend(self._check_sla_types(config))
        errors.extend(self._check_confidence_types(config))
        errors.extend(self._check_languages(config))

        # ── Value / range checks ───────────────────────────────────────────
        errors.extend(self._check_threshold_order(config))
        errors.extend(self._check_polling_interval(config))

        return {
            "ok":       len(errors) == 0,
            "errors":   errors,
            "warnings": warnings,
        }

    # ── Private helpers ────────────────────────────────────────────────────

    @staticmethod
    def _get(d: dict, *keys):
        """Safe nested dict access. Returns None if any key is missing."""
        for k in keys:
            if not isinstance(d, dict):
                return None
            d = d.get(k)
            if d is None:
                return None
        return d

    def _check_sla_types(self, config: dict) -> list[str]:
        errs = []
        sla = config.get("sla", {})
        for tier in ("Normal", "High", "Critical"):
            tier_cfg = sla.get(tier)
            if tier_cfg is None:
                continue
            if not isinstance(tier_cfg, dict):
                errs.append(f"sla.{tier} must be an object, got {type(tier_cfg).__name__}")
                continue
            for key in ("response_hours", "resolution_days"):
                val = tier_cfg.get(key)
                if val is not None and not isinstance(val, (int, float)):
                    errs.append(
                        f"sla.{tier}.{key} must be a number "
                        f"(got {type(val).__name__}: {val!r})"
                    )
        return errs

    def _check_confidence_types(self, config: dict) -> list[str]:
        errs = []
        conf = config.get("confidence", {})
        for field in ("auto_send_threshold", "human_review_threshold"):
            val = conf.get(field)
            if val is None:
                continue
            if not isinstance(val, (int, float)):
                errs.append(
                    f"confidence.{field} must be a float "
                    f"(got {type(val).__name__}: {val!r})"
                )
            elif not (0.0 <= float(val) <= 1.0):
                errs.append(
                    f"confidence.{field} must be between 0 and 1 (got {val})"
                )
        return errs

    def _check_languages(self, config: dict) -> list[str]:
        langs = self._get(config, "company", "supported_languages")
        if langs is None:
            return []
        if not isinstance(langs, list) or len(langs) == 0:
            return ["company.supported_languages must be a non-empty list"]
        return []

    def _check_threshold_order(self, config: dict) -> list[str]:
        conf   = config.get("confidence", {})
        auto_t = conf.get("auto_send_threshold")
        hr_t   = conf.get("human_review_threshold")
        if (
            isinstance(auto_t,  (int, float))
            and isinstance(hr_t, (int, float))
            and float(auto_t) <= float(hr_t)
        ):
            return [
                f"confidence.auto_send_threshold ({auto_t}) must be greater than "
                f"confidence.human_review_threshold ({hr_t})"
            ]
        return []

    def _check_polling_interval(self, config: dict) -> list[str]:
        polling = self._get(config, "communication", "polling_interval_seconds")
        if polling is None:
            return []
        if not isinstance(polling, (int, float)):
            return [
                f"communication.polling_interval_seconds must be a number "
                f"(got {type(polling).__name__})"
            ]
        if int(polling) < 10:
            return [
                f"communication.polling_interval_seconds must be >= 10 (got {polling})"
            ]
        return []
