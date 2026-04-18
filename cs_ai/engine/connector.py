"""
connector.py — Data abstraction layer between the AI engine and external systems.

TWO integration points, both generic:
  1. ERP  — order management (stock, delivery, status updates)
             Examples: SAP, Oracle, MS Dynamics, any REST/SOAP order API
  2. CRM  — customer communication & profile management
             Examples: Salesforce, HubSpot, Zendesk, any REST CRM API

To plug in a real system:
  1. Set config.json → erp.type = "erp_api"  (or crm.type = "crm_api")
  2. Fill in erp.endpoint + erp.auth  (or crm.endpoint + crm.auth)
  3. Implement the methods marked TODO in ERPConnector / CRMConnector

The AI engine only calls BaseConnector methods — never any vendor API directly.
Swapping the backend never requires touching main.py, app.py, or any other file.
"""

import json
import os
import time
import uuid
import logging
from datetime import datetime, UTC

from auth import AuthManager, MissingEnvVarError
from paths import resolve_company_file, resolve_data_file
from connector_base import ConnectorResult, make_ok, make_error

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency — tenacity (graceful degradation if not installed)
# ---------------------------------------------------------------------------
try:
    from tenacity import (
        retry, stop_after_attempt, wait_exponential_jitter,
        retry_if_exception_type, RetryError,
    )
    _TENACITY_AVAILABLE = True
except ImportError:
    _TENACITY_AVAILABLE = False
    log.warning("tenacity not installed — retries disabled. Run: pip install tenacity")

# ---------------------------------------------------------------------------
# Optional dependency — only required when type = "erp_api"
# ---------------------------------------------------------------------------
try:
    import requests as _requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False


# ==============================================================================
# BASE INTERFACE — every connector must implement these methods
# ==============================================================================

class BaseConnector:

    def get_order(self, order_id: str) -> dict | None:
        raise NotImplementedError

    def list_order_ids(self) -> list:
        raise NotImplementedError

    def update_order(self, order_id: str, changes: dict) -> bool:
        raise NotImplementedError

    def get_logs(self) -> list:
        raise NotImplementedError

    def save_log(self, entry: dict) -> None:
        raise NotImplementedError

    def get_customer_profile(self, customer_name: str) -> dict | None:
        raise NotImplementedError

    def get_all_profiles(self) -> dict:
        raise NotImplementedError

    def update_customer_profile(self, customer_name: str, data: dict) -> None:
        raise NotImplementedError

    # ── Safe wrappers with tenacity retries ───────────────────────────────

    def get_order_safe(self, order_id: str) -> ConnectorResult:
        """Wraps get_order() with retries and typed error envelope."""
        req_id = str(uuid.uuid4())[:8]

        def _call():
            return self.get_order(order_id)

        if _TENACITY_AVAILABLE:
            @retry(
                stop=stop_after_attempt(3),
                wait=wait_exponential_jitter(initial=1, max=10),
                retry=retry_if_exception_type((TimeoutError, ConnectionError, OSError)),
                reraise=False,
            )
            def _call_with_retry():
                return _call()
            try:
                data = _call_with_retry()
            except RetryError as exc:
                cause = exc.last_attempt.exception()
                return _classify_exception(cause, req_id)
            except Exception as exc:
                return _classify_exception(exc, req_id)
        else:
            try:
                data = _call()
            except Exception as exc:
                return _classify_exception(exc, req_id)

        if data is None:
            return make_error("fatal", "NOT_FOUND", f"Order {order_id} not found", req_id)
        return make_ok(data, req_id)

    def get_customer_safe(self, customer_name: str) -> ConnectorResult:
        """Wraps get_customer_profile() with retries and typed error envelope."""
        req_id = str(uuid.uuid4())[:8]

        def _call():
            return self.get_customer_profile(customer_name)

        if _TENACITY_AVAILABLE:
            @retry(
                stop=stop_after_attempt(3),
                wait=wait_exponential_jitter(initial=1, max=10),
                retry=retry_if_exception_type((TimeoutError, ConnectionError, OSError)),
                reraise=False,
            )
            def _call_with_retry():
                return _call()
            try:
                data = _call_with_retry()
            except RetryError as exc:
                cause = exc.last_attempt.exception()
                return _classify_exception(cause, req_id)
            except Exception as exc:
                return _classify_exception(exc, req_id)
        else:
            try:
                data = _call()
            except Exception as exc:
                return _classify_exception(exc, req_id)

        if data is None:
            return make_error("fatal", "NOT_FOUND", f"Customer {customer_name} not found", req_id)
        return make_ok(data, req_id)

    def search_kb_safe(self, *args, **kwargs) -> ConnectorResult:
        """Stub — KB search doesn't use BaseConnector; always returns ok(None)."""
        return make_ok(None, str(uuid.uuid4())[:8])


# ---------------------------------------------------------------------------
# Exception → ConnectorError kind mapper
# ---------------------------------------------------------------------------

def _classify_exception(exc: Exception, request_id: str) -> ConnectorResult:
    if isinstance(exc, TimeoutError):
        return make_error("timeout",   "TIMEOUT",     str(exc), request_id)
    if isinstance(exc, ConnectionError):
        return make_error("retryable", "CONN_ERROR",  str(exc), request_id)
    if isinstance(exc, PermissionError):
        return make_error("auth",      "AUTH_ERROR",  str(exc), request_id)
    return make_error("fatal",         "UNKNOWN",     str(exc), request_id)


# ==============================================================================
# JSON CONNECTOR — local files, used for development and demos
# ==============================================================================

class JSONConnector(BaseConnector):

    def __init__(self, config):
        # orders live in the company dir (company-specific reference data)
        self.orders_file   = resolve_company_file(config["erp"].get("orders_file",   "orders_mock.json"))
        # logs and profiles live in the data dir (runtime data, changes over time)
        self.logs_file     = resolve_data_file(config["crm"].get("logs_file",     "logs.json"))
        self.profiles_file = resolve_data_file(config["crm"].get("profiles_file", "customer_profiles.json"))
        self._orders_cache = None

    def _load_orders(self) -> dict:
        if self._orders_cache is None:
            with open(self.orders_file, "r", encoding="utf-8") as f:
                self._orders_cache = json.load(f)
        return self._orders_cache

    def get_order(self, order_id):
        return self._load_orders().get(order_id)

    def list_order_ids(self):
        return list(self._load_orders().keys())

    def update_order(self, order_id, changes):
        orders = self._load_orders()
        if order_id not in orders:
            return False
        for k, v in changes.items():
            if v is not None:
                orders[order_id][k] = v
        with open(self.orders_file, "w", encoding="utf-8") as f:
            json.dump(orders, f, ensure_ascii=False, indent=2)
        self._orders_cache = orders
        return True

    def get_logs(self):
        if not os.path.exists(self.logs_file):
            return []
        with open(self.logs_file, "r", encoding="utf-8") as f:
            try:    return json.load(f)
            except: return []

    def save_log(self, entry):
        logs = self.get_logs()
        logs.append(entry)
        with open(self.logs_file, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)

    def get_all_profiles(self):
        if not os.path.exists(self.profiles_file):
            return {}
        with open(self.profiles_file, "r", encoding="utf-8") as f:
            try:    return json.load(f)
            except: return {}

    def get_customer_profile(self, customer_name):
        return self.get_all_profiles().get(customer_name)

    def update_customer_profile(self, customer_name, data):
        profiles = self.get_all_profiles()
        profiles[customer_name] = data
        with open(self.profiles_file, "w", encoding="utf-8") as f:
            json.dump(profiles, f, ensure_ascii=False, indent=2)


# ==============================================================================
# ERP MAPPING MIXIN — shared field/status translation logic
# Used by both ERPConnector (live) and MockERPConnector (test)
# ==============================================================================

_REQUIRED_MAPPING_KEYS = {"endpoints", "field_map", "status_map", "reverse_status_map"}
_REQUIRED_ENDPOINTS    = {"get_order", "list_orders", "update_order"}


class ERPMappingMixin:
    """
    Provides field/status mapping between our internal schema and any ERP API.
    Loaded from erp_mapping.json — no vendor-specific logic here.
    """

    def _load_mapping(self, config: dict) -> None:
        mapping_file = config["erp"].get("mapping_file", "erp_mapping.json")
        base_dir     = os.path.dirname(os.path.abspath(__file__))
        path         = os.path.join(base_dir, mapping_file)

        if not os.path.exists(path):
            raise FileNotFoundError(
                f"ERP mapping file not found: {path}\n"
                "Create it from the erp_mapping.json template."
            )

        with open(path, "r", encoding="utf-8") as f:
            mapping = json.load(f)

        self._validate_mapping(mapping)
        self._mapping        = mapping
        self._endpoints      = mapping["endpoints"]
        self._field_map      = mapping["field_map"]           # internal → ERP
        self._rev_field_map  = {v: k for k, v in mapping["field_map"].items()}  # ERP → internal
        self._status_map     = mapping["status_map"]          # ERP status → internal
        self._rev_status_map = mapping["reverse_status_map"]  # internal → ERP status
        self._response_cfg   = mapping.get("response", {"list_key": "orders", "id_field": "id"})

    @staticmethod
    def _validate_mapping(mapping: dict) -> None:
        missing_keys = _REQUIRED_MAPPING_KEYS - mapping.keys()
        if missing_keys:
            raise ValueError(f"erp_mapping.json missing required keys: {missing_keys}")

        missing_ep = _REQUIRED_ENDPOINTS - mapping["endpoints"].keys()
        if missing_ep:
            raise ValueError(f"erp_mapping.json missing required endpoints: {missing_ep}")

    def _parse_endpoint(self, name: str) -> tuple[str, str]:
        """
        Parse an endpoint entry like "GET /orders/{order_id}" into (method, path_template).
        """
        raw = self._endpoints[name]
        parts = raw.split(" ", 1)
        if len(parts) != 2:
            raise ValueError(
                f"Invalid endpoint format in erp_mapping.json for '{name}': '{raw}'. "
                "Expected 'METHOD /path/template'."
            )
        return parts[0].upper(), parts[1]

    def _map_to_standard(self, raw: dict) -> dict:
        """
        Translate a raw ERP API response to our internal order schema.
        Unknown fields are passed through unchanged.
        """
        result = {}
        for erp_field, value in raw.items():
            internal_field = self._rev_field_map.get(erp_field, erp_field)
            result[internal_field] = value

        # Normalize status value
        if "status" in result:
            result["status"] = self._status_map.get(result["status"], result["status"])

        return result

    def _map_to_erp(self, changes: dict) -> dict:
        """
        Translate our internal change dict to ERP field names.
        Only fields present in field_map are translated; others pass through.
        """
        result = {}
        for internal_field, value in changes.items():
            if value is None:
                continue
            erp_field = self._field_map.get(internal_field, internal_field)
            # Translate status value to ERP representation
            if internal_field == "status":
                value = self._rev_status_map.get(value, value)
            result[erp_field] = value
        return result


# ==============================================================================
# ERP CONNECTOR — generic REST ERP integration
# Handles: orders, stock levels, delivery dates, order status updates
# ==============================================================================

class ERPConnector(ERPMappingMixin, BaseConnector):
    """
    Generic ERP REST connector. 100% config- and mapping-driven.

    config.json → erp:
      endpoint     — base URL (e.g. https://erp.yourcompany.com/api/v1)
      mapping_file — path to erp_mapping.json (default: "erp_mapping.json")
      auth:
        type "bearer":                   { "token_env_var": "ERP_TOKEN" }
        type "basic":                    { "username_env_var": "ERP_USER", "password_env_var": "ERP_PASS" }
        type "api_key":                  { "header": "X-API-Key", "key_env_var": "ERP_API_KEY" }
        type "oauth2_client_credentials":{ "token_url_env_var": "OAUTH_URL",
                                           "client_id_env_var": "OAUTH_CLIENT_ID",
                                           "client_secret_env_var": "OAUTH_SECRET",
                                           "scope": "orders:read orders:write" }
    """

    _MAX_RETRIES = 3

    def __init__(self, config: dict):
        if not _REQUESTS_AVAILABLE:
            raise ImportError(
                "The 'requests' library is required for ERPConnector. "
                "Install it with: pip install requests"
            )

        erp_cfg = config["erp"]
        self.endpoint = erp_cfg.get("endpoint", "").rstrip("/")
        if not self.endpoint:
            raise ValueError("config.json → erp.endpoint is required for ERPConnector.")

        self._auth_cfg = erp_cfg.get("auth", {})

        self._session = _requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})
        AuthManager.apply_to_session(self._session, self._auth_cfg)

        self._load_mapping(config)

    # ---- HTTP core ----------------------------------------------------------

    def _call(
        self,
        method: str,
        path_template: str,
        path_params: dict | None = None,
        body: dict | None = None,
    ) -> dict | list:
        """
        Execute an HTTP request against the ERP API.

        Handles:
          401  — refresh OAuth2 token (once), then retry
          429  — respect Retry-After header, retry up to _MAX_RETRIES times
          5xx  — retry once with 2s backoff, then raise ERPConnectionError
        """
        # Proactively refresh OAuth2 token before it expires
        AuthManager.refresh_if_expired(self._session, self._auth_cfg)

        # Fill path template
        path = path_template
        if path_params:
            path = path.format(**path_params)

        # Split query string if present (comes from list_orders endpoint)
        if "?" in path:
            path_part, query = path.split("?", 1)
        else:
            path_part, query = path, None

        url = self.endpoint + path_part
        params = {}
        if query:
            for kv in query.split("&"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    params[k] = v
                else:
                    params[kv] = ""

        kwargs: dict = {"timeout": 30}
        if body:
            kwargs["json"] = body
        if params:
            kwargs["params"] = params

        last_exc = None
        for attempt in range(self._MAX_RETRIES):
            try:
                resp = self._session.request(method, url, **kwargs)

                if resp.status_code == 401:
                    if attempt == 0:
                        refreshed = AuthManager.refresh_if_expired(
                            self._session, self._auth_cfg, force=True
                        )
                        if refreshed:
                            log.warning("ERPConnector: 401 — token refreshed, retrying.")
                            continue
                    raise ERPAuthError(f"ERP API auth failed (401): {url}")

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 5))
                    retry_after = min(retry_after, 60)  # cap at 60s
                    log.warning(
                        "ERPConnector: 429 rate-limited — waiting %ss (attempt %d/%d).",
                        retry_after, attempt + 1, self._MAX_RETRIES,
                    )
                    time.sleep(retry_after)
                    continue

                if resp.status_code >= 500:
                    if attempt < self._MAX_RETRIES - 1:
                        wait = 2 ** attempt  # 1s, 2s, 4s
                        log.warning(
                            "ERPConnector: %s server error — retrying in %ss.",
                            resp.status_code, wait,
                        )
                        time.sleep(wait)
                        continue
                    raise ERPConnectionError(
                        f"ERP API server error {resp.status_code}: {url}\n"
                        f"Response: {resp.text[:500]}"
                    )

                resp.raise_for_status()

                if not resp.content:
                    return {}
                return resp.json()

            except (ERPAuthError, ERPConnectionError):
                raise
            except _requests.exceptions.Timeout:
                last_exc = ERPConnectionError(f"ERP API request timed out: {url}")
            except _requests.exceptions.ConnectionError as exc:
                last_exc = ERPConnectionError(f"ERP API connection failed: {url} — {exc}")
            except Exception as exc:
                last_exc = ERPConnectionError(f"ERP API unexpected error: {exc}")

            if attempt < self._MAX_RETRIES - 1:
                time.sleep(2 ** attempt)

        raise last_exc or ERPConnectionError(f"ERP API call failed after {self._MAX_RETRIES} attempts: {url}")

    # ---- BaseConnector interface --------------------------------------------

    def get_order(self, order_id: str) -> dict | None:
        method, path_tpl = self._parse_endpoint("get_order")
        try:
            raw = self._call(method, path_tpl, path_params={"order_id": order_id})
            if not raw:
                return None
            return self._map_to_standard(raw)
        except ERPConnectionError as exc:
            log.error("ERPConnector.get_order(%s): %s", order_id, exc)
            return None

    def list_order_ids(self) -> list:
        method, path_tpl = self._parse_endpoint("list_orders")
        try:
            raw = self._call(method, path_tpl)
        except ERPConnectionError as exc:
            log.error("ERPConnector.list_order_ids: %s", exc)
            return []

        list_key = self._response_cfg.get("list_key", "orders")
        id_field  = self._response_cfg.get("id_field",  "id")

        if isinstance(raw, list):
            items = raw
        elif isinstance(raw, dict):
            items = raw.get(list_key, [])
        else:
            return []

        return [item[id_field] for item in items if id_field in item]

    def update_order(self, order_id: str, changes: dict) -> bool:
        method, path_tpl = self._parse_endpoint("update_order")
        erp_payload = self._map_to_erp(changes)
        if not erp_payload:
            return True  # nothing to update
        try:
            self._call(method, path_tpl, path_params={"order_id": order_id}, body=erp_payload)
            return True
        except ERPConnectionError as exc:
            log.error("ERPConnector.update_order(%s): %s", order_id, exc)
            return False

    def get_logs(self)         -> list: return []
    def save_log(self, entry)  -> None: pass
    def get_all_profiles(self) -> dict: return {}
    def get_customer_profile(self, customer_name) -> None: return None
    def update_customer_profile(self, customer_name, data) -> None: pass

    # ---- Diagnostics --------------------------------------------------------

    def test_connection(self) -> dict:
        """
        Verify the ERP endpoint is reachable and credentials are accepted.
        Calls list_orders with limit=1 — read-only, minimal data.
        Returns {"ok": True/False, "message": str}.
        """
        method, path_tpl = self._parse_endpoint("list_orders")

        # Override limit to 1 for the probe
        probe_path = path_tpl.split("?")[0] + "?limit=1"

        try:
            self._call(method, probe_path)
            return {"ok": True, "message": f"Connected to {self.endpoint}"}
        except ERPAuthError as exc:
            return {"ok": False, "message": f"Auth failed: {exc}"}
        except ERPConnectionError as exc:
            return {"ok": False, "message": f"Connection failed: {exc}"}
        except Exception as exc:
            return {"ok": False, "message": f"Unexpected error: {exc}"}


# ==============================================================================
# ERP EXCEPTIONS
# ==============================================================================

class ERPAuthError(Exception):
    """Raised when ERP API returns 401 and token refresh did not help."""

class ERPConnectionError(Exception):
    """Raised when ERP API is unreachable or returns a persistent 5xx error."""


# ==============================================================================
# MOCK ERP CONNECTOR — JSON files + mapping validation (dev / CI use)
# ==============================================================================

class MockERPConnector(ERPMappingMixin, JSONConnector):
    """
    Development connector that reads from local JSON files (like JSONConnector)
    but also loads and validates erp_mapping.json and applies its field/status
    translations — so you can test your mapping config without a live ERP.

    Switch to this by setting config.json → erp.type = "mock_erp".
    """

    def __init__(self, config: dict):
        JSONConnector.__init__(self, config)
        self._load_mapping(config)

    def get_order(self, order_id: str) -> dict | None:
        raw = JSONConnector.get_order(self, order_id)
        if raw is None:
            return None
        # Apply the mapping so the mapping config itself is exercised
        return self._map_to_standard(raw)

    def update_order(self, order_id: str, changes: dict) -> bool:
        # Translate to ERP field names, then back through JSONConnector
        erp_changes = self._map_to_erp(changes)
        # Re-translate to internal for storage (JSON files use internal names)
        internal_changes = self._map_to_standard(erp_changes)
        return JSONConnector.update_order(self, order_id, internal_changes)

    def test_connection(self) -> dict:
        """Always succeeds in mock mode — confirms mapping is valid."""
        try:
            self._validate_mapping(self._mapping)
            ids = self.list_order_ids()
            return {
                "ok":      True,
                "message": (
                    f"Mock mode — mapping validated. "
                    f"{len(ids)} order(s) in local JSON."
                ),
            }
        except Exception as exc:
            return {"ok": False, "message": f"Mapping validation failed: {exc}"}


# ==============================================================================
# CRM CONNECTOR — generic customer communication tool placeholder
# Handles: interaction logs, customer profiles, case history, communication records
# Implement with your company's CRM REST API (e.g. Salesforce, HubSpot, Zendesk…)
# ==============================================================================

class CRMConnector(BaseConnector):
    """
    Generic CRM integration — customer communication and profile management.

    Config fields (config.json → crm):
      endpoint  — base URL of the CRM API  (e.g. https://crm.yourcompany.com/api/v1)
      auth      — authentication config    (e.g. {"type": "oauth2", "token_url": "...", ...})
    """

    def __init__(self, config):
        if not _REQUESTS_AVAILABLE:
            raise ImportError(
                "The 'requests' library is required for CRMConnector. "
                "Install it with: pip install requests"
            )

        crm_cfg = config["crm"]
        self.endpoint = crm_cfg.get("endpoint", "").rstrip("/")
        if not self.endpoint:
            raise ValueError("config.json → crm.endpoint is required for CRMConnector.")

        self._auth_cfg = crm_cfg.get("auth", {})

        self._session = _requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})
        AuthManager.apply_to_session(self._session, self._auth_cfg)

    def get_order(self, order_id):
        # Orders are managed by the ERP connector, not CRM
        return None

    def list_order_ids(self):
        # Orders are managed by the ERP connector, not CRM
        return []

    def update_order(self, order_id, changes):
        # Orders are managed by the ERP connector, not CRM
        return False

    def get_logs(self):
        # TODO: GET {endpoint}/interactions?sort=created_at:desc
        raise NotImplementedError(
            "CRMConnector.get_logs() not implemented. "
            "Connect to your CRM API: GET {endpoint}/interactions"
        )

    def save_log(self, entry):
        # TODO: POST {endpoint}/interactions with entry payload
        raise NotImplementedError("CRMConnector.save_log() not implemented.")

    def get_all_profiles(self):
        # TODO: GET {endpoint}/customers
        raise NotImplementedError("CRMConnector.get_all_profiles() not implemented.")

    def get_customer_profile(self, customer_name):
        # TODO: GET {endpoint}/customers?name={customer_name}
        raise NotImplementedError("CRMConnector.get_customer_profile() not implemented.")

    def update_customer_profile(self, customer_name, data):
        # TODO: PATCH {endpoint}/customers/{customer_id} with data payload
        raise NotImplementedError("CRMConnector.update_customer_profile() not implemented.")


# ==============================================================================
# FACTORY — returns the right connector from config.json
# Change config["erp"]["type"] or config["crm"]["type"] to switch data source.
# No other file needs to change.
# ==============================================================================

def get_action_label(action_type: str, erp_mapping: dict) -> str:
    """
    Return the company-specific display label for an ERP action type.

    Looks up action_type in erp_mapping["action_labels"].
    Falls back to the raw action_type string if the key is absent,
    so existing behaviour is preserved for companies that haven't filled
    in action_labels yet.

    Example
    -------
    get_action_label("UNBLOCK_ORDER", mapping) -> "Release order"
    get_action_label("UNKNOWN_TYPE",  mapping) -> "UNKNOWN_TYPE"
    """
    return erp_mapping.get("action_labels", {}).get(action_type, action_type)


def get_risk_label(risk_level: str, erp_mapping: dict) -> str:
    """
    Return the company-specific description for an ERP action risk level.

    Looks up risk_level in erp_mapping["risk_labels"].
    Falls back to the raw risk_level string.

    Example
    -------
    get_risk_label("High", mapping) -> "Supervisor approval required"
    get_risk_label("Unknown", mapping) -> "Unknown"
    """
    return erp_mapping.get("risk_labels", {}).get(risk_level, risk_level)


def get_connector(config: dict) -> BaseConnector:
    """
    Returns the appropriate connector based on config.json → erp.type.

    Supported values:
      "json_mock"  — local JSON files (default, for development and demos)
      "mock_erp"   — JSON files + erp_mapping.json validation (dev/CI)
      "erp_api"    — generic ERP REST API  → ERPConnector (production)
      "crm_api"    — generic CRM REST API  → CRMConnector

    For erp_api and crm_api, validates that all required ENV vars are present
    before instantiating the connector. Raises a clear error if any are missing.
    """
    erp_type = config.get("erp", {}).get("type", "json_mock")

    if erp_type == "erp_api":
        _validate_auth_env(config["erp"].get("auth", {}), label="ERP")
        return ERPConnector(config)

    elif erp_type == "mock_erp":
        return MockERPConnector(config)

    elif erp_type == "crm_api":
        _validate_auth_env(config["crm"].get("auth", {}), label="CRM")
        return CRMConnector(config)

    else:
        return JSONConnector(config)


def _validate_auth_env(auth_config: dict, label: str) -> None:
    """
    Fail fast if any required environment variable for the selected connector
    is absent from the environment.

    Raises EnvironmentError with a clear, actionable message.
    """
    missing = AuthManager.validate_env_vars(auth_config)
    if missing:
        noun = "variable" if len(missing) == 1 else "variables"
        lines = "\n".join(f"  • {v}" for v in missing)
        raise EnvironmentError(
            f"Missing required environment {noun} for {label} connector:\n"
            f"{lines}\n"
            f"Add them to your .env file."
        )
