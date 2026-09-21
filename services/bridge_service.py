"""Bridge status and legacy exceptional-maintenance APIs.

Normal business creation establishes its mapping atomically; these proposal and
approval APIs are not part of onboarding. Existing blocked mappings are preserved.
"""

from typing import Any

from database import queries
from services import auth_service, business_service


def _error(code: str, message: str) -> dict[str, Any]:
    return {"success": False, "error": code, "message": message}


def _safe_bridge(row: Any) -> dict[str, Any]:
    return {
        "bridge_id": row["bridge_id"],
        "business_id": row["business_id"],
        "bridge_status": row["bridge_status"],
        "proposed_at": row["proposed_at"],
        "verified_at": row["verified_at"],
    }


def get_bridge_status(token: str, business_id: str) -> dict[str, Any]:
    access = business_service.require_business_access(token, business_id, {"owner", "manager"})
    if not access.get("success"):
        return access
    row = queries.get_business_bridge(business_id)
    return {
        "success": True,
        "bridge": _safe_bridge(row) if row is not None else None,
    }


def propose_bridge(token: str, business_id: str) -> dict[str, Any]:
    access = business_service.require_business_access(token, business_id, {"owner"})
    if not access.get("success"):
        return access
    existing = queries.get_business_bridge(business_id)
    if existing is not None:
        return _error(
            "BRIDGE_ALREADY_EXISTS",
            "This business already has a registry relationship; maintenance is required to change it.",
        )
    try:
        bridge_id = queries.create_registry_bridge_proposal(
            business_id=business_id,
            owner_user_id=access["user"]["user_id"],
            business_name=access["business"]["business_name"],
        )
        return {
            "success": True,
            "bridge": _safe_bridge(queries.get_bridge_by_id(bridge_id)),
            "message": "Registry verification requested.",
        }
    except Exception:
        return _error("BRIDGE_CREATE_FAILED", "Registry verification could not be requested.")


def list_pending(token: str) -> dict[str, Any]:
    auth = auth_service.require_role(token, {"administrator"})
    if not auth.get("success"):
        return auth
    return {
        "success": True,
        "bridges": [
            {**_safe_bridge(row), "business_name": row["business_name"]}
            for row in queries.list_pending_bridges()
        ],
    }


def approve_bridge(token: str, bridge_id: str) -> dict[str, Any]:
    auth = auth_service.require_role(token, {"administrator"})
    if not auth.get("success"):
        return auth
    row = queries.get_bridge_by_id((bridge_id or "").strip())
    if row is None or row["bridge_status"] != "pending":
        return _error("BRIDGE_NOT_PENDING", "The registry request is unavailable.")
    if row["proposed_by_user_id"] == auth["user"]["user_id"]:
        return _error("INDEPENDENT_VERIFIER_REQUIRED", "A different administrator must approve this request.")
    try:
        if not queries.activate_registry_bridge(row["bridge_id"], auth["user"]["user_id"]):
            return _error("BRIDGE_NOT_PENDING", "The registry request is unavailable.")
    except Exception:
        return _error("BRIDGE_APPROVAL_FAILED", "Registry verification could not be completed.")
    return {
        "success": True,
        "bridge": _safe_bridge(queries.get_bridge_by_id(row["bridge_id"])),
        "message": "Registry relationship approved.",
    }


__all__ = ["approve_bridge", "get_bridge_status", "list_pending", "propose_bridge"]
