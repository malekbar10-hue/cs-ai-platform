"""
run.py — Launch the CS AI platform for a specific company.

Usage:
    python run.py --company default
    python run.py --company default --inbox      (launches app_inbox.py instead of app.py)

What it does:
    1. Sets CS_AI_ROOT and CS_AI_COMPANY environment variables
    2. Launches Streamlit with the correct engine app
    3. All engine files read company/data paths from those env vars via paths.py
"""

import argparse
import os
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(
        description="Launch CS AI for a specific company"
    )
    parser.add_argument(
        "--company", default="default",
        help="Company name (must match a folder in cs_ai/companies/). Default: default"
    )
    parser.add_argument(
        "--inbox", action="store_true",
        help="Launch the multi-ticket inbox dashboard (app_inbox.py) instead of app.py"
    )
    args = parser.parse_args()

    root        = os.path.dirname(os.path.abspath(__file__))
    company_dir = os.path.join(root, "cs_ai", "companies", args.company)
    config_file = os.path.join(company_dir, "config.json")

    # Validate company exists
    if not os.path.isdir(company_dir):
        print(f"ERROR: Company folder not found: {company_dir}")
        print(f"       Available companies: {_list_companies(root)}")
        sys.exit(1)

    if not os.path.isfile(config_file):
        print(f"ERROR: config.json not found in {company_dir}")
        print(f"       Run: python setup.py --company {args.company}  to initialise it.")
        sys.exit(1)

    # Set environment variables for all engine components
    env = os.environ.copy()
    env["CS_AI_ROOT"]    = root
    env["CS_AI_COMPANY"] = args.company

    # ------------------------------------------------------------------
    # Config validation
    # ------------------------------------------------------------------
    _validate_config(root, config_file)

    # ------------------------------------------------------------------
    # Pre-launch secrets validation
    # ------------------------------------------------------------------
    _validate_secrets(root, args.company, env)

    app_file = "app_inbox.py" if args.inbox else "app.py"
    app_path = os.path.join(root, "cs_ai", "engine", app_file)

    print(f"Starting CS AI — company: {args.company}")
    print(f"Config : {config_file}")
    print(f"App    : {app_path}")
    print()

    cmd = [sys.executable, "-m", "streamlit", "run", app_path]
    subprocess.run(cmd, env=env, cwd=root)


def _validate_config(root: str, config_file: str) -> None:
    """
    Load config.json, run ConfigValidator, and print results.
    Exits with code 1 if any hard errors are found.
    """
    import json as _json

    _engine_dir = os.path.join(root, "cs_ai", "engine")
    if _engine_dir not in sys.path:
        sys.path.insert(0, _engine_dir)

    from config_validator import ConfigValidator

    with open(config_file, "r", encoding="utf-8") as _f:
        _config = _json.load(_f)

    result = ConfigValidator().validate(_config)

    _RED    = "\033[91m"
    _YELLOW = "\033[93m"
    _GREEN  = "\033[92m"
    _RESET  = "\033[0m"

    if result["warnings"] or result["errors"]:
        print("Config validation:")
        for w in result["warnings"]:
            print(f"  {_YELLOW}[WARN]{_RESET} {w}")
        for e in result["errors"]:
            print(f"  {_RED}[FAIL]{_RESET} {e}")
        print()

    if result["errors"]:
        print(
            f"{_RED}Config validation failed — fix the errors above before starting.{_RESET}"
        )
        sys.exit(1)
    elif not result["warnings"]:
        print(f"{_GREEN}✅ Config valid{_RESET}")
        print()


def _validate_secrets(root: str, company: str, env: dict) -> None:
    """
    Read .env.template, check which required secrets are missing for this company.
    Prints a checklist and exits if any REQUIRED secret is absent.
    Missing optional secrets are shown as warnings but do not block launch.
    """
    template_path = os.path.join(
        root, "cs_ai", "companies", "_template", ".env.template"
    )
    if not os.path.isfile(template_path):
        return  # No template — skip silently

    prefix   = company.upper() + "_"
    failures = []
    warnings = []

    with open(template_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            key = line.split("=", 1)[0].strip()
            if not key:
                continue

            if key.startswith("COMPANY_NAME_"):
                bare_name    = key[len("COMPANY_NAME_"):]
                prefixed_key = prefix + bare_name
                check_keys   = [prefixed_key, bare_name]
                display_key  = prefixed_key
            else:
                check_keys  = [key]
                display_key = key

            comment = raw_line[raw_line.index("#"):].strip() if "#" in raw_line else ""
            value   = next((env.get(k) for k in check_keys if env.get(k)), None)

            if not value:
                if "REQUIRED" in comment:
                    failures.append(f"  [FAIL] {display_key}  {comment}")
                else:
                    warnings.append(f"  [WARN] {display_key} not set (optional)")

    if warnings or failures:
        print("\nSecrets pre-flight check:")
        for w in warnings:
            print(w)
        for f in failures:
            print(f)
        print()

    if failures:
        print(
            f"ERROR: {len(failures)} required secret(s) missing for company '{company}'.\n"
            f"       Add them to your .env file and restart.\n"
            f"       See cs_ai/companies/_template/.env.template for the full list.\n"
        )
        sys.exit(1)


def _list_companies(root: str) -> str:
    companies_dir = os.path.join(root, "cs_ai", "companies")
    if not os.path.isdir(companies_dir):
        return "(none)"
    return ", ".join(
        d for d in os.listdir(companies_dir)
        if os.path.isdir(os.path.join(companies_dir, d)) and not d.startswith("_")
    )


if __name__ == "__main__":
    main()
