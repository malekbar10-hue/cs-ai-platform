"""
setup.py — Validate and initialise a company configuration.

Usage:
    python setup.py --company default

What it checks:
    1. Company folder and config.json exist
    2. Required config fields are filled (not placeholder values)
    3. OPENAI_API_KEY is set
    4. ERP/CRM auth ENV vars are set (if using API connectors)
    5. Knowledge base file exists and has entries
    6. Data directory is writable
    7. Builds NLP embeddings for this company's knowledge base

Prints a readiness checklist with green (OK) / yellow (WARN) / red (FAIL) per item.
"""

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys


# ---------------------------------------------------------------------------
# Symbols (ASCII-safe for Windows terminals)
# ---------------------------------------------------------------------------
_OK   = "[OK]  "
_WARN = "[WARN]"
_FAIL = "[FAIL]"


def main():
    parser = argparse.ArgumentParser(description="Set up and validate a company config")
    parser.add_argument("--company", default="default")
    parser.add_argument("--skip-embeddings", action="store_true",
                        help="Skip NLP embedding build step")
    parser.add_argument("--skip-auth", action="store_true",
                        help="Skip interactive user authentication setup")
    args = parser.parse_args()

    root    = os.path.dirname(os.path.abspath(__file__))
    company = args.company

    # Make paths.py importable
    engine_dir = os.path.join(root, "cs_ai", "engine")
    sys.path.insert(0, engine_dir)

    # Set env vars so paths.py resolves correctly
    os.environ["CS_AI_ROOT"]    = root
    os.environ["CS_AI_COMPANY"] = company

    from paths import (
        company_dir, data_dir, config_path,
        resolve_company_file, resolve_data_file,
    )

    print(f"\n{'='*56}")
    print(f"  CS AI Setup — company: {company}")
    print(f"{'='*56}\n")

    checks: list[tuple[str, str]] = []

    # ------------------------------------------------------------------
    # 1. Company folder
    # ------------------------------------------------------------------
    c_dir = company_dir(company)
    if os.path.isdir(c_dir):
        checks.append((_OK,   f"Company folder:   {c_dir}"))
    else:
        checks.append((_FAIL, f"Company folder not found: {c_dir}"))
        checks.append((_WARN, f"  -> Copy cs_ai/companies/_template/ to cs_ai/companies/{company}/"))
        _print_checks(checks)
        sys.exit(1)

    # ------------------------------------------------------------------
    # 2. config.json
    # ------------------------------------------------------------------
    cfg_file = config_path(company)
    if not os.path.isfile(cfg_file):
        checks.append((_FAIL, f"config.json not found: {cfg_file}"))
        _print_checks(checks)
        sys.exit(1)

    with open(cfg_file, "r", encoding="utf-8") as f:
        config = json.load(f)
    checks.append((_OK, f"config.json found: {cfg_file}"))

    # ------------------------------------------------------------------
    # 3. Required config fields (placeholder check)
    # ------------------------------------------------------------------
    placeholders = {"YourCompany", "", None}
    fields = [
        ("company.name",        config.get("company", {}).get("name")),
        ("company.agent_role",  config.get("company", {}).get("agent_role")),
        ("ai.model",            config.get("ai", {}).get("model")),
    ]
    for field, val in fields:
        if val and val not in placeholders:
            checks.append((_OK,   f"config.{field} = {val}"))
        else:
            checks.append((_WARN, f"config.{field} is placeholder or missing — edit config.json"))

    # ------------------------------------------------------------------
    # 3b. ConfigValidator — deep structural + type + value checks
    # ------------------------------------------------------------------
    from config_validator import ConfigValidator
    _cv_result = ConfigValidator().validate(config)

    print("Config validation (structural):")
    for _w in _cv_result["warnings"]:
        checks.append((_WARN, _w))
        print(f"  {_WARN} {_w}")
    for _e in _cv_result["errors"]:
        checks.append((_FAIL, _e))
        print(f"  {_FAIL} {_e}")
    if not _cv_result["errors"] and not _cv_result["warnings"]:
        checks.append((_OK, "Config structure, types, and values all valid"))
        print(f"  {_OK}   Config structure, types, and values all valid")
    print()

    # ------------------------------------------------------------------
    # 4. OPENAI_API_KEY
    # ------------------------------------------------------------------
    if os.environ.get("OPENAI_API_KEY"):
        checks.append((_OK,   "OPENAI_API_KEY is set"))
    else:
        # Try loading from .env
        env_path = os.path.join(root, ".env")
        if os.path.isfile(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("OPENAI_API_KEY="):
                        os.environ["OPENAI_API_KEY"] = line.split("=", 1)[1].strip()
                        break
        if os.environ.get("OPENAI_API_KEY"):
            checks.append((_OK,   "OPENAI_API_KEY loaded from .env"))
        else:
            checks.append((_FAIL, "OPENAI_API_KEY not set — add it to your .env file"))

    # ------------------------------------------------------------------
    # 5. ERP/CRM auth ENV vars
    # ------------------------------------------------------------------
    erp_type = config.get("erp", {}).get("type", "json_mock")
    if erp_type in ("json_mock", "mock_erp"):
        checks.append((_OK, f"ERP connector: {erp_type} (no API credentials needed)"))
    else:
        try:
            from auth import AuthManager
            missing = AuthManager.validate_env_vars(config["erp"].get("auth", {}))
            if missing:
                for m in missing:
                    checks.append((_FAIL, f"Missing ERP env var: {m}"))
            else:
                checks.append((_OK, "ERP auth env vars all set"))
        except Exception as e:
            checks.append((_WARN, f"Could not validate ERP auth: {e}"))

    # ------------------------------------------------------------------
    # 6. Knowledge base
    # ------------------------------------------------------------------
    kb_file = resolve_company_file("knowledge_base.json", company)
    if os.path.isfile(kb_file):
        with open(kb_file, "r", encoding="utf-8") as f:
            try:
                kb = json.load(f)
                entries = kb.get("entries", [])
                checks.append((_OK, f"knowledge_base.json: {len(entries)} entries"))
            except Exception:
                checks.append((_WARN, "knowledge_base.json exists but could not be parsed"))
    else:
        checks.append((_WARN, f"knowledge_base.json not found: {kb_file}"))

    # ------------------------------------------------------------------
    # 7. Data directory
    # ------------------------------------------------------------------
    d_dir = data_dir(company)
    if os.path.isdir(d_dir):
        checks.append((_OK,   f"Data directory:   {d_dir}"))
    else:
        os.makedirs(d_dir, exist_ok=True)
        checks.append((_OK,   f"Data directory created: {d_dir}"))

    # Test write permission
    test_file = os.path.join(d_dir, ".write_test")
    try:
        with open(test_file, "w") as f:
            f.write("ok")
        os.remove(test_file)
        checks.append((_OK, "Data directory is writable"))
    except Exception:
        checks.append((_FAIL, f"Data directory is NOT writable: {d_dir}"))

    # ------------------------------------------------------------------
    # Print results so far
    # ------------------------------------------------------------------
    _print_checks(checks)

    # ------------------------------------------------------------------
    # 8. Secrets checklist (per-company env vars)
    # ------------------------------------------------------------------
    print(f"Secrets checklist for company '{company}':")
    secret_checks = _check_secrets(root, company)
    _print_checks(secret_checks)
    checks.extend(secret_checks)

    # ------------------------------------------------------------------
    # Build NLP embeddings
    # ------------------------------------------------------------------
    critical_fails = [c for c in checks if c[0] == _FAIL]
    if critical_fails:
        print(f"\n{len(critical_fails)} critical issue(s) — fix them before building embeddings.\n")
        sys.exit(1)

    if args.skip_embeddings:
        print("\n[--skip-embeddings] NLP build skipped.\n")
    else:
        print("\nBuilding NLP embeddings for this company's knowledge base...")
        nlp_script = os.path.join(engine_dir, "nlp.py")
        env = os.environ.copy()
        result = subprocess.run(
            [sys.executable, nlp_script, "--build"],
            env=env,
            cwd=root,
        )
        if result.returncode == 0:
            print(f"{_OK} NLP embeddings built successfully\n")
        else:
            print(f"{_WARN} NLP build completed with warnings\n"
                  "      (This is OK if sentence-transformers is not installed — "
                  "keyword fallback will be used.)\n")

    # ------------------------------------------------------------------
    # 9. User authentication setup
    # ------------------------------------------------------------------
    if args.skip_auth:
        print("[--skip-auth] Authentication setup skipped.\n")
    else:
        _setup_users(root, company)

    print("="*56)
    print(f"  Setup complete — company: {company}")
    print(f"  Start the app: python run.py --company {company}")
    print("="*56 + "\n")


def _check_secrets(root: str, company: str) -> list[tuple[str, str]]:
    """
    Read .env.template for the company (or the shared _template if missing),
    substitute COMPANY_NAME_ with the actual prefix, and verify each variable
    is present in the environment.

    Returns a list of (status, message) tuples, same format as the main checklist.
    """
    template_path = os.path.join(
        root, "cs_ai", "companies", "_template", ".env.template"
    )
    if not os.path.isfile(template_path):
        return [(_WARN, ".env.template not found — skipping secrets check")]

    prefix = company.upper() + "_"
    results: list[tuple[str, str]] = []

    with open(template_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            # Skip blank lines, comment-only lines, and the header block
            if not line or line.startswith("#"):
                continue
            # Extract the key (everything before =)
            key = line.split("=", 1)[0].strip()
            if not key:
                continue

            # Determine whether this var uses the company prefix
            if key.startswith("COMPANY_NAME_"):
                bare_name    = key[len("COMPANY_NAME_"):]
                prefixed_key = prefix + bare_name
                check_keys   = [prefixed_key, bare_name]
                display_key  = prefixed_key
            else:
                # Global key (e.g. OPENAI_API_KEY) — no prefix
                check_keys  = [key]
                display_key = key

            # Extract the inline comment to show the REQUIRED / optional annotation
            comment = ""
            if "#" in raw_line:
                comment = raw_line[raw_line.index("#"):].strip()

            value = next((os.environ.get(k) for k in check_keys if os.environ.get(k)), None)
            if value:
                results.append((_OK, f"{display_key} is set"))
            elif "REQUIRED" in comment:
                results.append((_FAIL, f"Missing secret: {display_key}  {comment}"))
            else:
                results.append((_WARN, f"Optional secret not set: {display_key}  {comment}"))

    if not results:
        results.append((_WARN, "No secret variables found in .env.template"))

    return results


def _setup_users(root: str, company: str) -> None:
    """
    Interactive step: create users.yaml for the company if missing,
    generate a cookie secret, and prompt for passwords.
    Passwords are hashed with bcrypt (via streamlit-authenticator.Hasher).
    Plaintext passwords are never written to disk.
    """
    print(f"\n{'='*56}")
    print("  Authentication setup")
    print(f"{'='*56}")

    try:
        import yaml
        from streamlit_authenticator import Hasher
    except ImportError:
        print(f"  {_WARN} streamlit-authenticator not installed.")
        print("        Run: pip install streamlit-authenticator")
        print("        Then re-run setup.py to configure users.\n")
        return

    company_folder  = os.path.join(root, "cs_ai", "companies", company)
    users_path      = os.path.join(company_folder, "users.yaml")
    template_path   = os.path.join(root, "cs_ai", "companies", "_template", "users.yaml")

    # ── Create from template if missing ───────────────────────────────────
    if not os.path.isfile(users_path):
        if os.path.isfile(template_path):
            shutil.copy(template_path, users_path)
            print(f"  {_OK}   users.yaml created from template: {users_path}")
        else:
            print(f"  {_FAIL} Template not found: {template_path}")
            return

    with open(users_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    changed = False

    # ── Generate cookie key if missing ────────────────────────────────────
    cookie = config.setdefault("cookie", {})
    if not cookie.get("key"):
        cookie["key"]  = secrets.token_hex(32)
        cookie.setdefault("name",        "cs_ai_session")
        cookie.setdefault("expiry_days", 1)
        changed = True
        print(f"  {_OK}   Cookie secret generated.")
    else:
        print(f"  {_OK}   Cookie secret already set.")

    # ── Prompt for passwords ──────────────────────────────────────────────
    credentials   = config.setdefault("credentials", {})
    usernames_cfg = credentials.setdefault("usernames", {})

    users_needing_pw = [
        u for u, d in usernames_cfg.items()
        if not d.get("password")
    ]

    if not users_needing_pw:
        print(f"  {_OK}   All user passwords already set.")
    else:
        print(f"\n  Setting passwords for: {', '.join(users_needing_pw)}")
        print("  (input is hidden — press Enter after typing each password)\n")
        for uname in users_needing_pw:
            while True:
                try:
                    import getpass
                    pw1 = getpass.getpass(f"  Password for '{uname}': ")
                    pw2 = getpass.getpass(f"  Confirm password  : ")
                except Exception:
                    pw1 = input(f"  Password for '{uname}': ")
                    pw2 = input(f"  Confirm password  : ")

                if not pw1:
                    print("    Password cannot be empty. Try again.\n")
                    continue
                if pw1 != pw2:
                    print("    Passwords do not match. Try again.\n")
                    continue

                usernames_cfg[uname]["password"] = Hasher.hash(pw1)
                print(f"    {_OK} Password set for '{uname}'.\n")
                changed = True
                break

    # ── Write back if changed ─────────────────────────────────────────────
    if changed:
        with open(users_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, default_flow_style=False, allow_unicode=True)
        print(f"  {_OK}   users.yaml saved: {users_path}")
    else:
        print(f"  {_OK}   users.yaml unchanged.")

    print()


def _print_checks(checks: list) -> None:
    for status, message in checks:
        print(f"  {status} {message}")
    print()


if __name__ == "__main__":
    main()
