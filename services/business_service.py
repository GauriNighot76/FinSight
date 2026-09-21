import re
import sqlite3
from typing import Optional

from database import queries
from services.auth_service import validate_session

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PHONE_RE = re.compile(r"^\+?[0-9]{7,15}$")
MEMBERSHIP_ROLES = frozenset({"owner", "manager", "member", "viewer"})


def _error(code: str, message: str) -> dict:
    return {"success": False, "error": code, "message": message}


def _business(row) -> dict:
    return {key: row[key] for key in (
        "business_id", "business_name", "business_type", "legal_identifier", "contact_email",
        "contact_phone", "business_status", "created_at", "updated_at"
    )}


def _membership(row) -> dict:
    return {key: row[key] for key in (
        "membership_id", "business_id", "user_id", "membership_role",
        "membership_status", "created_at", "updated_at"
    )}


def create_business(token: str, business_data: dict) -> dict:
    auth = validate_session(token)
    if not auth["success"]:
        return auth
    data = business_data if isinstance(business_data, dict) else {}
    name = (data.get("business_name") or "").strip()
    business_type = (data.get("business_type") or "").strip() or None
    legal_id = (data.get("legal_identifier") or "").strip() or None
    email = (data.get("contact_email") or "").strip().lower() or None
    phone = (data.get("contact_phone") or "").strip() or None
    if len(name) < 2 or len(name) > 150:
        return _error("INVALID_INPUT", "Business name must contain 2 to 150 characters.")
    if legal_id and len(legal_id) > 100:
        return _error("INVALID_INPUT", "Legal identifier is too long.")
    if email and not EMAIL_RE.fullmatch(email):
        return _error("INVALID_INPUT", "Enter a valid business contact email.")
    if phone and not PHONE_RE.fullmatch(phone):
        return _error("INVALID_INPUT", "Enter a valid business contact phone.")
    try:
        business_id, membership_id = queries.create_business_with_owner(
            auth["user"]["user_id"], name, legal_id, email, phone, business_type
        )
        business = queries.get_module2_business(business_id)
        membership = queries.get_business_membership(business_id, auth["user"]["user_id"])
        return {"success": True, "business": _business(business),
                "membership": _membership(membership),
                "message": "Business created successfully."}
    except Exception:
        return _error("BUSINESS_CREATE_FAILED", "Business creation failed.")


def require_business_access(token: str, business_id: str,
                            allowed_roles: Optional[set[str]] = None) -> dict:
    auth = validate_session(token)
    if not auth["success"]:
        return auth
    business = queries.get_module2_business((business_id or "").strip())
    if business is None:
        return _error("BUSINESS_NOT_FOUND", "Business was not found.")
    membership = queries.get_business_membership(business["business_id"], auth["user"]["user_id"])
    if membership is None:
        return _error("FORBIDDEN", "You do not have access to this business.")
    if business["business_status"] != "active":
        return _error("BUSINESS_DISABLED", "This business is disabled.")
    if membership["membership_status"] != "active":
        return _error("MEMBERSHIP_DISABLED", "Your business membership is disabled.")
    if allowed_roles is not None and membership["membership_role"] not in allowed_roles:
        return _error("FORBIDDEN", "You do not have permission for this business action.")
    return {"success": True, "user": auth["user"], "business": _business(business),
            "membership": _membership(membership)}



def ensure_business_ready(token: str, business_id: str) -> dict:
    """Ensure an authorized business has its hidden ingestion resources."""
    access = require_business_access(token, business_id, {"owner", "manager"})
    if not access["success"]:
        return access
    try:
        resources = queries.ensure_business_runtime_resources(business_id)
        return {
            "success": True,
            "business": access["business"],
            "membership": access["membership"],
            "account_id": resources["account_id"],
            "message": "Business is ready for transaction ingestion.",
        }
    except (sqlite3.IntegrityError, ValueError):
        return _error(
            "BUSINESS_RUNTIME_SETUP_FAILED",
            "The business could not be prepared for transaction ingestion.",
        )
    except Exception:
        return _error(
            "BUSINESS_RUNTIME_SETUP_FAILED",
            "The business could not be prepared for transaction ingestion.",
        )

def get_business(token: str, business_id: str) -> dict:
    access = require_business_access(token, business_id)
    if not access["success"]:
        return access
    return {"success": True, "business": access["business"],
            "membership": access["membership"]}


def list_user_businesses(token: str) -> dict:
    auth = validate_session(token)
    if not auth["success"]:
        return auth
    rows = queries.list_active_user_businesses(auth["user"]["user_id"])
    businesses = [{**_business(row), "membership": {
        "membership_id": row["membership_id"], "business_id": row["business_id"],
        "user_id": row["user_id"], "membership_role": row["membership_role"],
        "membership_status": row["membership_status"],
        "created_at": row["membership_created_at"],
        "updated_at": row["membership_updated_at"],
    }} for row in rows]
    return {"success": True, "businesses": businesses}


def add_member(token: str, business_id: str, member_email: str,
               membership_role: str) -> dict:
    access = require_business_access(token, business_id, {"owner", "manager"})
    if not access["success"]:
        return access
    role = (membership_role or "").strip().lower()
    email = (member_email or "").strip().lower()
    if role not in MEMBERSHIP_ROLES or role == "owner":
        return _error("INVALID_INPUT", "The requested membership role is not allowed.")
    if access["membership"]["membership_role"] == "manager" and role == "manager":
        return _error("FORBIDDEN", "Managers cannot grant manager or owner access.")
    if not EMAIL_RE.fullmatch(email):
        return _error("INVALID_INPUT", "Enter a valid member email.")
    target = queries.get_user_by_email(email)
    if target is None:
        return _error("USER_NOT_FOUND", "No FinSight user was found for this email.")
    try:
        membership_id = queries.add_business_membership(business_id, target["user_id"], role)
    except sqlite3.IntegrityError:
        return _error("DUPLICATE_MEMBERSHIP", "This user already has a business membership.")
    row = queries.get_business_membership(business_id, target["user_id"])
    return {"success": True, "membership": _membership(row),
            "message": "Member added successfully."}


def list_members(token: str, business_id: str) -> dict:
    access = require_business_access(token, business_id, {"owner", "manager"})
    if not access["success"]:
        return access
    rows = queries.list_business_memberships(business_id)
    members = [{**_membership(row), "username": row["username"], "email": row["email"]}
               for row in rows]
    return {"success": True, "members": members}


def remove_member(token: str, business_id: str, membership_id: str) -> dict:
    access = require_business_access(token, business_id, {"owner", "manager"})
    if not access["success"]:
        return access
    target = next((row for row in queries.list_business_memberships(business_id)
                   if row["membership_id"] == membership_id), None)
    if target is None:
        return _error("MEMBERSHIP_NOT_FOUND", "Membership was not found.")
    if target["membership_role"] == "owner":
        return _error("OWNER_REQUIRED", "The final owner cannot be removed without ownership transfer.")
    actor_role = access["membership"]["membership_role"]
    if actor_role == "manager" and target["membership_role"] in {"owner", "manager"}:
        return _error("FORBIDDEN", "Managers cannot remove owners or managers.")
    if not queries.disable_business_membership(membership_id):
        return _error("MEMBERSHIP_DISABLED", "Membership is already disabled.")
    return {"success": True, "message": "Member removed successfully."}
