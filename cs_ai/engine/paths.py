"""
paths.py — Single source of truth for all file paths in the CS AI platform.

How paths are resolved:
  CS_AI_ROOT    env var  → project root  (set by run.py before launching Streamlit)
  CS_AI_COMPANY env var  → active company name (default: "default")

All engine files import from here instead of hardcoding paths.
Never import this in config files or data files — engine only.
"""

from __future__ import annotations
import os

# ---------------------------------------------------------------------------
# Root + company resolution
# ---------------------------------------------------------------------------

def get_root() -> str:
    """
    Project root directory.
    Reads CS_AI_ROOT env var (set by run.py).
    Falls back to three levels up from this file: cs_ai/engine/paths.py → root.
    """
    env = os.environ.get("CS_AI_ROOT")
    if env:
        return env
    # cs_ai/engine/paths.py  →  cs_ai/engine/  →  cs_ai/  →  root
    return os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )


def get_company() -> str:
    """Active company name. Reads CS_AI_COMPANY env var, defaults to 'default'."""
    return os.environ.get("CS_AI_COMPANY", "default")


# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------

def company_dir(company: str | None = None) -> str:
    """cs_ai/companies/{company}/ — config files, KB, ERP mapping."""
    return os.path.join(get_root(), "cs_ai", "companies", company or get_company())


def data_dir(company: str | None = None) -> str:
    """
    cs_ai/data/{company}/ — runtime data: logs, profiles, tickets.db, chroma_db.
    Created automatically if it does not exist.
    """
    d = os.path.join(get_root(), "cs_ai", "data", company or get_company())
    os.makedirs(d, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Specific path helpers
# ---------------------------------------------------------------------------

def config_path(company: str | None = None) -> str:
    """Full path to the company config.json."""
    return os.path.join(company_dir(company), "config.json")


def chroma_db_path(company: str | None = None) -> str:
    """Full path to the company chroma_db directory."""
    return os.path.join(data_dir(company), "chroma_db")


def tickets_db_path(company: str | None = None) -> str:
    """Full path to the company tickets.db SQLite file."""
    return os.path.join(data_dir(company), "tickets.db")


def resolve_company_file(filename: str, company: str | None = None) -> str:
    """
    Resolve a filename relative to the company config directory.
    Use for: knowledge_base.json, orders_mock.json, erp_mapping.json, escalation_rules.json
    """
    return os.path.join(company_dir(company), filename)


def resolve_data_file(filename: str, company: str | None = None) -> str:
    """
    Resolve a filename relative to the company data directory.
    Use for: logs.json, customer_profiles.json
    """
    return os.path.join(data_dir(company), filename)
