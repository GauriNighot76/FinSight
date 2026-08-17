import hashlib
from datetime import datetime, timedelta, timezone

from database import queries
from security.passwords import hash_password, verify_password
from services import auth_service


def test_password_hash_and_verify():
    hashed = hash_password("StrongPass1")
    assert hashed != "StrongPass1"
    assert hashed.startswith("$2")
    assert verify_password("StrongPass1", hashed)
    assert not verify_password("WrongPass1", hashed)


def test_signup_stores_hash_and_safe_result():
    result = auth_service.signup("Gauri", "GAURI@example.com", "9876543210", "StrongPass1")
    stored = queries.get_user_by_email("gauri@example.com")
    assert result["success"] is True
    assert result["user"]["role"] == "standard_business"
    assert "password_hash" not in result["user"]
    assert stored["password_hash"] != "StrongPass1"
    assert verify_password("StrongPass1", stored["password_hash"])


def test_signup_validation_and_duplicate():
    assert auth_service.signup("G", "bad", "123", "weak")["success"] is False
    assert auth_service.signup("Gauri", "g@example.com", "9876543210", "StrongPass1")["success"]
    duplicate = auth_service.signup("Other", "G@EXAMPLE.COM", "9876543211", "StrongPass1")
    assert duplicate["error"] == "EMAIL_ALREADY_EXISTS"


def test_login_session_logout_cycle():
    auth_service.signup("Gauri", "g@example.com", "9876543210", "StrongPass1")
    login = auth_service.login("G@EXAMPLE.COM", "StrongPass1")
    assert login["success"]
    assert "password_hash" not in login["user"]
    token = login["session"]["token"]
    assert auth_service.validate_session(token)["success"]
    assert auth_service.logout(token)["success"]
    assert not auth_service.validate_session(token)["success"]
    assert not auth_service.logout(token)["success"]


def test_login_failures_and_disabled_account(isolated_test_database):
    auth_service.signup("Gauri", "g@example.com", "9876543210", "StrongPass1")
    assert auth_service.login("g@example.com", "WrongPass1")["error"] == "INVALID_CREDENTIALS"
    assert auth_service.login("unknown@example.com", "WrongPass1")["error"] == "INVALID_CREDENTIALS"
    with isolated_test_database() as connection:
        connection.execute("UPDATE users SET account_status='disabled' WHERE email='g@example.com'")
    assert auth_service.login("g@example.com", "StrongPass1")["error"] == "ACCOUNT_DISABLED"


def test_invalid_and_expired_session():
    assert auth_service.validate_session("invalid")["error"] == "SESSION_INVALID"
    user_id = queries.create_user("g@example.com", "9876543210", hash_password("StrongPass1"), username="G")
    token = "temporary-token"
    queries.create_session(user_id, hashlib.sha256(token.encode()).hexdigest(),
                           (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat())
    assert auth_service.validate_session(token)["error"] == "SESSION_INVALID"


def test_role_authorization_and_no_frontend_elevation():
    result = auth_service.signup("Gauri", "g@example.com", "9876543210", "StrongPass1")
    assert result["user"]["role"] == "standard_business"
    token = auth_service.login("g@example.com", "StrongPass1")["session"]["token"]
    assert auth_service.require_role(token, {"standard_business"})["success"]
    assert auth_service.require_role(token, {"administrator"})["error"] == "FORBIDDEN"


def test_google_new_existing_and_mapping():
    identity = {"sub": "google-123", "email": "g@example.com", "email_verified": True, "name": "Gauri"}
    first = auth_service.google_sign_in("token", verifier=lambda _: identity)
    second = auth_service.google_sign_in("token", verifier=lambda _: identity)
    assert first["success"] and second["success"]
    assert first["user"]["user_id"] == second["user"]["user_id"]
    assert queries.get_provider_identity("google", "google-123")["user_id"] == first["user"]["user_id"]


def test_google_links_existing_email_without_duplicate():
    existing = auth_service.signup("Gauri", "g@example.com", "9876543210", "StrongPass1")
    identity = {"sub": "google-456", "email": "g@example.com", "email_verified": True}
    google = auth_service.google_sign_in("token", verifier=lambda _: identity)
    assert google["user"]["user_id"] == existing["user"]["user_id"]


def test_google_rejects_invalid_identity():
    assert auth_service.google_sign_in("bad", verifier=lambda _: {"sub": "x", "email": "g@example.com"})["error"] == "GOOGLE_AUTH_FAILED"
    def failing(_):
        raise ValueError("invalid token")
    assert auth_service.google_sign_in("bad", verifier=failing)["error"] == "GOOGLE_AUTH_FAILED"


def test_raw_session_token_not_stored(isolated_test_database):
    auth_service.signup("Gauri", "g@example.com", "9876543210", "StrongPass1")
    token = auth_service.login("g@example.com", "StrongPass1")["session"]["token"]
    with isolated_test_database() as connection:
        row = connection.execute("SELECT token_hash FROM auth_sessions").fetchone()
    assert row["token_hash"] != token
    assert row["token_hash"] == hashlib.sha256(token.encode()).hexdigest()
