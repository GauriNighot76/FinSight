"""Ledger-link setup plus legacy administrator-review compatibility."""

from database import queries
from services import auth_service, business_service


def _error(code: str, message: str) -> dict:
    return {"success": False, "error": code, "message": message}


def bridge_status(token: str, business_id: str) -> dict:
    access = business_service.require_business_access(token, business_id)
    if not access.get("success"):
        return access
    row = queries.get_latest_bridge(business_id)
    return {
        "success": True,
        "status": "not_requested" if row is None else row["bridge_status"],
    }


def request_approval(token: str, business_id: str) -> dict:
    access = business_service.require_business_access(token, business_id, {"owner"})
    if not access.get("success"):
        return access
    current = queries.get_latest_bridge(business_id)
    if current and current["bridge_status"] in {"pending", "active"}:
        return {"success": True, "status": current["bridge_status"]}
    try:
        queries.create_registry_bridge_proposal(
            business_id,
            access["user"]["user_id"],
            access["business"]["business_name"],
        )
    except Exception:
        return _error("REQUEST_FAILED", "Approval could not be requested.")
    return {"success": True, "status": "pending"}


def activate_imports(token: str, business_id: str) -> dict:
    """Complete ordinary owner onboarding without an administrator queue."""
    access = business_service.require_business_access(token, business_id, {"owner"})
    if not access.get("success"):
        return access
    try:
        queries.create_active_registry_bridge(
            business_id,
            access["user"]["user_id"],
            access["business"]["business_name"],
        )
    except Exception:
        return _error("REQUEST_FAILED", "Setup could not be completed.")
    return {"success": True, "status": "active"}


def list_pending(token: str) -> dict:
    auth = auth_service.require_role(token, {"administrator"})
    if not auth.get("success"):
        return auth
    rows = queries.list_pending_registry_bridges()
    return {
        "success": True,
        "requests": [
            {
                "bridge_id": row["bridge_id"],
                "business_name": row["business_name"],
                "legal_identifier": row["legal_identifier"],
                "proposer_name": row["proposer_name"],
                "proposer_email": row["proposer_email"],
                "proposed_at": row["proposed_at"],
            }
            for row in rows
        ],
    }


def review(token: str, bridge_id: str, decision: str) -> dict:
    auth = auth_service.require_role(token, {"administrator"})
    if not auth.get("success"):
        return auth
    if decision not in {"approve", "reject"}:
        return _error("INVALID_DECISION", "Choose approve or reject.")
    if not queries.review_registry_bridge(
        bridge_id, auth["user"]["user_id"], decision
    ):
        return _error("REVIEW_FAILED", "This request cannot be reviewed.")
    return {"success": True, "status": "active" if decision == "approve" else "rejected"}


__all__ = ["activate_imports", "bridge_status", "list_pending", "request_approval", "review"]
