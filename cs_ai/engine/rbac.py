"""
rbac.py — Role-based access control for the CS AI dashboards.

Usage:
    from rbac import can
    if can(st.session_state["role"], "view_audit_trail"):
        ...

Permission keys
---------------
view_status_panel   — see the live connection status sidebar panel
refresh_status      — use the ↻ Refresh button in the status panel
view_audit_trail    — see the Audit Trail section in ticket detail
export_audit_csv    — use the Export CSV button in the audit trail
reassign_ticket     — assign/change the agent on a ticket
view_config_summary — see the read-only Config Summary sidebar panel
manage_users        — access the Users admin tab (add/remove/reset pw)
erp_low_risk        — execute ERP actions with risk level "Low"
erp_medium_risk     — execute ERP actions with risk level "Medium"
erp_high_risk       — execute ERP actions with risk level "High"
"""

from __future__ import annotations

_PERMISSIONS: dict[str, dict[str, bool]] = {
    "agent": {
        "view_status_panel":   False,
        "refresh_status":      False,
        "view_audit_trail":    False,
        "export_audit_csv":    False,
        "reassign_ticket":     False,
        "view_config_summary": False,
        "manage_users":        False,
        "erp_low_risk":        True,
        "erp_medium_risk":     False,
        "erp_high_risk":       False,
    },
    "supervisor": {
        "view_status_panel":   True,
        "refresh_status":      False,   # read-only — no cache refresh
        "view_audit_trail":    True,
        "export_audit_csv":    False,
        "reassign_ticket":     True,
        "view_config_summary": False,
        "manage_users":        False,
        "erp_low_risk":        True,
        "erp_medium_risk":     True,
        "erp_high_risk":       False,
    },
    "admin": {
        "view_status_panel":   True,
        "refresh_status":      True,
        "view_audit_trail":    True,
        "export_audit_csv":    True,
        "reassign_ticket":     True,
        "view_config_summary": True,
        "manage_users":        True,
        "erp_low_risk":        True,
        "erp_medium_risk":     True,
        "erp_high_risk":       False,   # High-risk requires out-of-band approval
    },
}


def can(role: str, action: str) -> bool:
    """
    Return True if *role* is permitted to perform *action*.

    Unknown roles default to agent-level permissions (most restrictive).
    Unknown action keys return False (deny by default).
    """
    return _PERMISSIONS.get(role, _PERMISSIONS["agent"]).get(action, False)
