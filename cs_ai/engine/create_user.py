"""
create_user.py — Quick setup: creates users.yaml for the default company.
Run: python cs_ai/engine/create_user.py
"""
import os, sys, yaml, bcrypt, secrets

# ── Paths ──────────────────────────────────────────────────────────────────
_ROOT      = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_COMPANY   = os.environ.get("CS_AI_COMPANY", "default")
_CDIR      = os.path.join(_ROOT, "cs_ai", "companies", _COMPANY)
_OUT       = os.path.join(_CDIR, "users.yaml")

os.makedirs(_CDIR, exist_ok=True)

# ── User input ─────────────────────────────────────────────────────────────
print(f"\nCreating admin user for company: {_COMPANY}")
print(f"Output: {_OUT}\n")

username = input("Username (default: admin): ").strip() or "admin"
name     = input("Display name (default: Admin): ").strip() or "Admin"
email    = input("Email (default: admin@cs.ai): ").strip() or "admin@cs.ai"
password = input("Password (default: admin123): ").strip() or "admin123"

# ── Hash password ──────────────────────────────────────────────────────────
hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

# ── Build YAML ─────────────────────────────────────────────────────────────
data = {
    "credentials": {
        "usernames": {
            username: {
                "name":     name,
                "email":    email,
                "password": hashed,
                "role":     "admin",
            }
        }
    },
    "cookie": {
        "name":        "cs_ai_session",
        "key":         secrets.token_hex(32),
        "expiry_days": 1,
    }
}

with open(_OUT, "w", encoding="utf-8") as f:
    yaml.dump(data, f, allow_unicode=True)

print(f"\n✓ users.yaml created at {_OUT}")
print(f"  Username: {username}")
print(f"  Login at: http://localhost:8501\n")
