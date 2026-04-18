"""
auth.py — Reusable authentication manager for all external API connections.

Used by: ERPConnector, CRMConnector, and any future REST client.

Rules (non-negotiable):
  - ALL credentials come from environment variables, never from config files.
  - Config files only store the ENV VAR NAMES, not the values.
  - OAuth2 tokens are cached at the module level and refreshed 60s before expiry.

Supported auth types and their config shape:
  bearer:
    {"type": "bearer", "token_env_var": "ERP_TOKEN"}

  basic:
    {"type": "basic", "username_env_var": "ERP_USER", "password_env_var": "ERP_PASS"}

  api_key:
    {"type": "api_key", "header": "X-API-Key", "key_env_var": "ERP_API_KEY"}

  oauth2_client_credentials:
    {"type": "oauth2_client_credentials",
     "token_url_env_var":    "OAUTH_TOKEN_URL",
     "client_id_env_var":    "OAUTH_CLIENT_ID",
     "client_secret_env_var":"OAUTH_SECRET",
     "scope":                "orders:read orders:write"}   ← optional, not an env var
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level OAuth2 token cache
# key  : (token_url, client_id) — uniquely identifies a credential pair
# value: {"token": str, "expiry": float}  — expiry = Unix timestamp
# ---------------------------------------------------------------------------
_token_cache: dict[tuple[str, str], dict] = {}

# How many seconds before actual expiry we proactively refresh
_EXPIRY_BUFFER_SECONDS = 60


# ==============================================================================
# ENV VAR REGISTRY — maps auth type → list of required config keys
# Each key's value in the auth_config is the name of an environment variable.
# ==============================================================================

_REQUIRED_ENV_KEYS: dict[str, list[str]] = {
    "bearer":                    ["token_env_var"],
    "basic":                     ["username_env_var", "password_env_var"],
    "api_key":                   ["key_env_var"],
    "oauth2_client_credentials": ["token_url_env_var", "client_id_env_var", "client_secret_env_var"],
}


# ==============================================================================
# AuthManager
# ==============================================================================

class AuthManager:
    """
    Static utility class.  No instance needed — call methods directly:
        AuthManager.apply_to_session(session, auth_config)
        AuthManager.validate_env_vars(auth_config)
    """

    # --------------------------------------------------------------------------
    # Public API
    # --------------------------------------------------------------------------

    @staticmethod
    def apply_to_session(session, auth_config: dict) -> None:
        """
        Configure a requests.Session with the appropriate auth headers / credentials.

        Parameters
        ----------
        session     : requests.Session (or any object with .headers / .auth attributes)
        auth_config : dict from config.json → <connector>.auth
        """
        auth_type = auth_config.get("type", "").lower()

        if auth_type == "bearer":
            token = AuthManager._read_env(auth_config, "token_env_var")
            session.headers["Authorization"] = f"Bearer {token}"
            log.debug("AuthManager: bearer token applied.")

        elif auth_type == "basic":
            username = AuthManager._read_env(auth_config, "username_env_var")
            password = AuthManager._read_env(auth_config, "password_env_var")
            session.auth = (username, password)
            log.debug("AuthManager: basic auth applied (user=%s).", username)

        elif auth_type == "api_key":
            header = auth_config.get("header", "X-API-Key")
            key    = AuthManager._read_env(auth_config, "key_env_var")
            session.headers[header] = key
            log.debug("AuthManager: api_key applied to header '%s'.", header)

        elif auth_type == "oauth2_client_credentials":
            token, expiry = AuthManager._get_or_refresh_oauth2(auth_config)
            session.headers["Authorization"] = f"Bearer {token}"
            log.debug("AuthManager: OAuth2 token applied (expires in %.0fs).", expiry - time.time())

        elif auth_type:
            log.warning(
                "AuthManager: unknown auth type '%s' — no auth applied. "
                "Supported: bearer, basic, api_key, oauth2_client_credentials.",
                auth_type,
            )
        # auth_type == "" → no auth, silently skip

    @staticmethod
    def refresh_if_expired(session, auth_config: dict, force: bool = False) -> bool:
        """
        For OAuth2 only: refresh the cached token if it is expired (or force=True).
        Applies the new token to the session.

        Returns True if a refresh was performed, False otherwise.
        Use force=True after a 401 response to recover from a surprise expiry.
        """
        if auth_config.get("type", "").lower() != "oauth2_client_credentials":
            return False

        token_url  = AuthManager._read_env(auth_config, "token_url_env_var")
        client_id  = AuthManager._read_env(auth_config, "client_id_env_var")
        cache_key  = (token_url, client_id)
        cached     = _token_cache.get(cache_key)
        now        = time.time()

        needs_refresh = force or (cached is None) or (now >= cached["expiry"])

        if not needs_refresh:
            return False

        log.debug("AuthManager: refreshing OAuth2 token (force=%s).", force)
        token, expiry = AuthManager._get_or_refresh_oauth2(auth_config, force=True)
        session.headers["Authorization"] = f"Bearer {token}"
        return True

    @staticmethod
    def get_token_oauth2(
        token_url: str,
        client_id: str,
        client_secret: str,
        scope: str = "",
    ) -> tuple[str, float]:
        """
        Request a fresh OAuth2 client_credentials token.

        Returns
        -------
        (access_token, expiry_timestamp)
            access_token   : the token string
            expiry_timestamp: Unix time at which the token should be considered expired
                             (actual expiry minus _EXPIRY_BUFFER_SECONDS)
        """
        try:
            import requests as _requests
        except ImportError:
            raise ImportError(
                "The 'requests' library is required for OAuth2. "
                "Install it with: pip install requests"
            )

        payload: dict = {
            "grant_type":    "client_credentials",
            "client_id":     client_id,
            "client_secret": client_secret,
        }
        if scope:
            payload["scope"] = scope

        resp = _requests.post(token_url, data=payload, timeout=15)

        if resp.status_code == 401:
            raise AuthError(
                f"OAuth2 token request rejected (401) at {token_url}. "
                "Check client_id and client_secret."
            )
        if not resp.ok:
            raise AuthError(
                f"OAuth2 token request failed ({resp.status_code}) at {token_url}: "
                f"{resp.text[:300]}"
            )

        data       = resp.json()
        token      = data.get("access_token")
        if not token:
            raise AuthError(
                f"OAuth2 response from {token_url} did not contain 'access_token'. "
                f"Response keys: {list(data.keys())}"
            )

        expires_in = int(data.get("expires_in", 3600))
        expiry     = time.time() + expires_in - _EXPIRY_BUFFER_SECONDS

        log.debug(
            "AuthManager: OAuth2 token obtained (expires_in=%ds, effective_ttl=%ds).",
            expires_in, expires_in - _EXPIRY_BUFFER_SECONDS,
        )
        return token, expiry

    @staticmethod
    def validate_env_vars(auth_config: dict) -> list[str]:
        """
        Return a list of environment variable names that are required by the given
        auth config but are currently missing from the environment.

        An empty list means all required variables are present.

        Usage
        -----
        missing = AuthManager.validate_env_vars(config["erp"]["auth"])
        if missing:
            raise EnvironmentError(f"Missing: {missing}")
        """
        auth_type    = auth_config.get("type", "").lower()
        required_keys = _REQUIRED_ENV_KEYS.get(auth_type, [])

        missing: list[str] = []
        for config_key in required_keys:
            env_var_name = auth_config.get(config_key)
            if not env_var_name:
                missing.append(f"<{config_key} not set in auth config>")
                continue
            if not os.environ.get(env_var_name):
                missing.append(env_var_name)

        return missing

    # --------------------------------------------------------------------------
    # Internal helpers
    # --------------------------------------------------------------------------

    @staticmethod
    def _read_env(auth_config: dict, config_key: str) -> str:
        """
        Read the env var whose *name* is stored in auth_config[config_key].

        Example:
            auth_config = {"token_env_var": "ERP_TOKEN"}
            _read_env(auth_config, "token_env_var")  →  os.environ["ERP_TOKEN"]
        """
        env_var_name = auth_config.get(config_key, "")
        if not env_var_name:
            raise AuthConfigError(
                f"auth config is missing '{config_key}'. "
                f"Expected a key like: \"{config_key}\": \"YOUR_ENV_VAR_NAME\""
            )
        value = os.environ.get(env_var_name, "")
        if not value:
            raise MissingEnvVarError(
                f"Missing required environment variable: {env_var_name} — "
                f"add it to your .env file."
            )
        return value

    @staticmethod
    def _get_or_refresh_oauth2(
        auth_config: dict,
        force: bool = False,
    ) -> tuple[str, float]:
        """
        Return a valid OAuth2 token from cache, refreshing if expired or forced.
        Updates the module-level cache.
        """
        token_url     = AuthManager._read_env(auth_config, "token_url_env_var")
        client_id     = AuthManager._read_env(auth_config, "client_id_env_var")
        client_secret = AuthManager._read_env(auth_config, "client_secret_env_var")
        scope         = auth_config.get("scope", "")
        cache_key     = (token_url, client_id)

        cached = _token_cache.get(cache_key)
        now    = time.time()

        if not force and cached and now < cached["expiry"]:
            return cached["token"], cached["expiry"]

        # Fetch a new token
        token, expiry = AuthManager.get_token_oauth2(
            token_url, client_id, client_secret, scope
        )
        _token_cache[cache_key] = {"token": token, "expiry": expiry}
        return token, expiry


# ==============================================================================
# Exceptions
# ==============================================================================

class AuthError(Exception):
    """Raised when authentication against an external API fails."""

class AuthConfigError(Exception):
    """Raised when the auth_config dict is missing required keys."""

class MissingEnvVarError(EnvironmentError):
    """Raised when a required environment variable is not set."""
