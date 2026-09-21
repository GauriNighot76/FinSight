import hashlib
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from database import queries
from security.passwords import hash_password, verify_password

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
CONTACT_RE = re.compile(r"^\+?[0-9]{7,15}$")
ROLES = frozenset({"administrator", "standard_business", "accountant", "auditor"})
DEFAULT_ROLE = "standard_business"


def _result_error(code: str, message: str) -> dict:
    return {"success": False, "error": code, "message": message}


def _safe_user(row) -> dict:
    return {"user_id": row["user_id"], "username": row["username"],
            "email": row["email"], "role": row["role"]}


def _validate_password(password: str) -> Optional[str]:
    if len(password or "") < 8:
        return "Password must contain at least 8 characters."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Password must contain at least one letter and one number."
    return None


def signup(username: str, email: str, contact_number: str, password: str) -> dict:
    username, email, contact_number = (username or "").strip(), (email or "").strip().lower(), (contact_number or "").strip()
    if len(username) < 2 or len(username) > 80:
        return _result_error("INVALID_USERNAME", "Username must contain 2 to 80 characters.")
    if not EMAIL_RE.fullmatch(email):
        return _result_error("INVALID_EMAIL", "Enter a valid email address.")
    if not CONTACT_RE.fullmatch(contact_number):
        return _result_error("INVALID_CONTACT", "Enter a valid contact number.")
    password_error = _validate_password(password)
    if password_error:
        return _result_error("WEAK_PASSWORD", password_error)
    if queries.get_user_by_email(email) is not None:
        return _result_error("EMAIL_ALREADY_EXISTS", "An account with this email already exists.")
    try:
        user_id = queries.create_user(email, contact_number, hash_password(password),
                                      username=username, role=DEFAULT_ROLE)
        user = queries.get_user_by_id(user_id)
        queries.create_authentication_log(user_id, "SIGNUP_SUCCESS")
        return {"success": True, "user": _safe_user(user), "message": "Account created successfully."}
    except sqlite3.IntegrityError:
        return _result_error("EMAIL_ALREADY_EXISTS", "An account with this email already exists.")
    except Exception:
        return _result_error("SIGNUP_FAILED", "Account creation failed. Please try again.")


def provision_demo_administrator(
    username: str, email: str, contact_number: str, password: str
) -> dict:
    """Create the fixed local demo administrator only during explicit demo seeding."""
    if os.getenv("FINSIGHT_ALLOW_DEMO_SEED") != "1":
        return _result_error("DEMO_SEED_DISABLED", "Demo administrator provisioning is disabled.")
    email = (email or "").strip().lower()
    if email != "admin@demo.finsight.local":
        return _result_error("INVALID_EMAIL", "The demo administrator identity is invalid.")
    existing = queries.get_user_by_email(email)
    if existing is not None:
        if existing["role"] != "administrator":
            return _result_error("DEMO_ADMIN_CONFLICT", "The demo administrator identity is unavailable.")
        return {"success": True, "user": _safe_user(existing), "message": "Demo administrator already exists."}
    username = (username or "").strip()
    contact_number = (contact_number or "").strip()
    if not 2 <= len(username) <= 80 or not CONTACT_RE.fullmatch(contact_number):
        return _result_error("INVALID_INPUT", "The demo administrator details are invalid.")
    password_error = _validate_password(password)
    if password_error:
        return _result_error("WEAK_PASSWORD", password_error)
    try:
        user_id = queries.create_user(
            email,
            contact_number,
            hash_password(password),
            username=username,
            role="administrator",
        )
        return {
            "success": True,
            "user": _safe_user(queries.get_user_by_id(user_id)),
            "message": "Demo administrator created.",
        }
    except Exception:
        return _result_error("DEMO_ADMIN_FAILED", "Demo administrator provisioning failed.")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(user_id: str, lifetime_hours: int = 8) -> dict:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=lifetime_hours)
    queries.create_session(user_id, _hash_token(token), expires.isoformat())
    return {"token": token, "expires_at": expires.isoformat()}


def login(email: str, password: str) -> dict:
    email = (email or "").strip().lower()
    user = queries.get_user_by_email(email) if EMAIL_RE.fullmatch(email) else None
    if user is None or not user["password_hash"] or not verify_password(password or "", user["password_hash"]):
        queries.create_authentication_log(user["user_id"] if user else None, "LOGIN_FAILURE")
        return _result_error("INVALID_CREDENTIALS", "Invalid email or password.")
    if user["account_status"] != "active":
        queries.create_authentication_log(user["user_id"], "LOGIN_FAILURE_DISABLED")
        return _result_error("ACCOUNT_DISABLED", "This account is disabled.")
    session = create_session(user["user_id"])
    queries.create_authentication_log(user["user_id"], "LOGIN_SUCCESS")
    return {"success": True, "user": _safe_user(user), "session": session,
            "message": "Login successful."}


def validate_session(token: str) -> dict:
    if not token:
        return _result_error("SESSION_INVALID", "Authentication is required.")
    row = queries.get_active_session(_hash_token(token))
    if row is None or row["account_status"] != "active":
        return _result_error("SESSION_INVALID", "Session is invalid or expired.")
    return {"success": True, "user": _safe_user(row), "expires_at": row["expires_at"]}


def logout(token: str) -> dict:
    if not token or not queries.revoke_session(_hash_token(token)):
        return _result_error("SESSION_INVALID", "Session is invalid or already logged out.")
    return {"success": True, "message": "Logged out successfully."}


def require_role(token: str, allowed_roles) -> dict:
    session = validate_session(token)
    if not session["success"]:
        return session
    allowed = set(allowed_roles)
    if session["user"]["role"] not in allowed:
        queries.create_authentication_log(session["user"]["user_id"], "AUTHORIZATION_DENIED")
        return _result_error("FORBIDDEN", "You do not have permission to perform this action.")
    return session


def verify_google_id_token(id_token_value: str) -> dict:
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        raise RuntimeError("GOOGLE_CLIENT_ID is not configured")
    from google.auth.transport import requests
    from google.oauth2 import id_token
    return id_token.verify_oauth2_token(id_token_value, requests.Request(), client_id)


def google_sign_in(id_token_value: str, verifier: Callable[[str], dict] = verify_google_id_token) -> dict:
    try:
        identity = verifier(id_token_value)
    except Exception:
        return _result_error("GOOGLE_AUTH_FAILED", "Google authentication failed.")
    subject, email = identity.get("sub"), (identity.get("email") or "").strip().lower()
    if not subject or not EMAIL_RE.fullmatch(email) or identity.get("email_verified") is not True:
        return _result_error("GOOGLE_AUTH_FAILED", "Google authentication failed.")
    mapped = queries.get_provider_identity("google", subject)
    if mapped:
        user = queries.get_user_by_id(mapped["user_id"])
    else:
        user = queries.get_user_by_email(email)
        if user is None:
            username = (identity.get("name") or email.split("@", 1)[0]).strip()[:80]
            # Google-only accounts receive an unknown random bcrypt credential so
            # legacy Module 0 databases with password_hash NOT NULL remain valid.
            unusable_password = hash_password(secrets.token_urlsafe(32))
            user_id = queries.create_user(email, "google", unusable_password,
                                          username=username, role=DEFAULT_ROLE)
            user = queries.get_user_by_id(user_id)
        try:
            queries.create_provider_identity(user["user_id"], "google", subject, email)
        except sqlite3.IntegrityError:
            return _result_error("GOOGLE_AUTH_FAILED", "Google authentication failed.")
    if user["account_status"] != "active":
        return _result_error("ACCOUNT_DISABLED", "This account is disabled.")
    session = create_session(user["user_id"])
    queries.create_authentication_log(user["user_id"], "GOOGLE_LOGIN")
    return {"success": True, "user": _safe_user(user), "session": session,
            "message": "Google login successful."}
