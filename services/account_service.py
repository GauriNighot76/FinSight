import re
import sqlite3
from decimal import Decimal, InvalidOperation
from typing import Optional

from database import queries
from services.business_service import require_business_access

ACCOUNT_TYPES = frozenset({"bank", "cash", "credit_card", "loan", "other"})
MANAGE_ROLES = frozenset({"owner", "manager"})
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
IMMUTABLE_FIELDS = frozenset({
    "account_id", "business_id", "created_at", "account_status",
    "user_id", "owner_user_id", "created_by_user_id", "membership_role",
})
MAX_MINOR_BALANCE = 10**15


def _error(code: str, message: str) -> dict:
    return {"success": False, "error": code, "message": message}


def _minor_units(value) -> int:
    if isinstance(value, bool):
        raise ValueError("Invalid balance")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Invalid balance") from None
    if not amount.is_finite() or amount.as_tuple().exponent < -2:
        raise ValueError("Balance must have at most two decimal places")
    minor = int(amount * 100)
    if abs(minor) > MAX_MINOR_BALANCE:
        raise ValueError("Balance is outside the supported range")
    return minor


def _major_units(minor: int) -> str:
    return f"{Decimal(minor) / Decimal(100):.2f}"


def _masked_identifier(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return value if len(value) <= 4 else f"****{value[-4:]}"


def _safe_account(row) -> dict:
    return {
        "account_id": row["account_id"], "business_id": row["business_id"],
        "account_name": row["account_name"], "account_type": row["account_type"],
        "institution_name": row["institution_name"],
        "account_identifier": _masked_identifier(row["account_identifier"]),
        "currency": row["currency"],
        "opening_balance": _major_units(row["opening_balance_minor"]),
        "account_status": row["account_status"], "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _validate_account_data(data: dict, existing=None) -> tuple:
    if not isinstance(data, dict):
        raise ValueError("Account data must be an object")
    if IMMUTABLE_FIELDS.intersection(data):
        raise ValueError("Immutable account fields cannot be changed")
    def value(name, default=None):
        return data[name] if name in data else (existing[name] if existing is not None else default)
    name = value("account_name", "")
    if not isinstance(name, str) or not 2 <= len(name.strip()) <= 120:
        raise ValueError("Account name must contain 2 to 120 characters")
    account_type = value("account_type", "")
    if account_type not in ACCOUNT_TYPES:
        raise ValueError("Unsupported account type")
    institution = value("institution_name")
    if institution is not None:
        if not isinstance(institution, str) or len(institution.strip()) > 120:
            raise ValueError("Invalid institution name")
        institution = institution.strip() or None
    identifier = value("account_identifier")
    if identifier is not None:
        if not isinstance(identifier, str) or len(identifier.strip()) > 100:
            raise ValueError("Invalid account identifier")
        identifier = identifier.strip() or None
    currency = value("currency", "INR")
    if not isinstance(currency, str) or not CURRENCY_RE.fullmatch(currency.strip().upper()):
        raise ValueError("Currency must be a three-letter code")
    currency = currency.strip().upper()
    balance_source = data.get(
        "opening_balance",
        _major_units(existing["opening_balance_minor"]) if existing is not None else "0.00",
    )
    return name.strip(), account_type, institution, identifier, currency, _minor_units(balance_source)


def create_account(token: str, business_id: str, account_data: dict) -> dict:
    access = require_business_access(token, business_id, set(MANAGE_ROLES))
    if not access["success"]:
        return access
    try:
        values = _validate_account_data(account_data)
        account_id = queries.create_financial_account(business_id, *values)
        return {"success": True, "account": _safe_account(queries.get_financial_account(account_id)),
                "message": "Financial account created successfully."}
    except ValueError as error:
        return _error("INVALID_INPUT", str(error))
    except sqlite3.IntegrityError:
        return _error("DUPLICATE_ACCOUNT", "An account with this identifier already exists for the business.")
    except Exception:
        return _error("ACCOUNT_CREATE_FAILED", "Financial account creation failed.")


def _authorized_account(token: str, account_id: str, roles=None):
    row = queries.get_financial_account((account_id or "").strip())
    if row is None:
        return _error("ACCOUNT_NOT_FOUND", "Financial account was not found."), None
    access = require_business_access(token, row["business_id"], roles)
    if not access["success"]:
        return access, None
    if row["account_status"] != "active":
        return _error("ACCOUNT_DISABLED", "This financial account is disabled."), None
    return {"success": True, "user": access["user"], "business": access["business"],
            "membership": access["membership"], "account": _safe_account(row)}, row


def require_account_access(token: str, account_id: str) -> dict:
    result, _ = _authorized_account(token, account_id)
    return result


def get_account(token: str, account_id: str) -> dict:
    result, _ = _authorized_account(token, account_id)
    if not result["success"]:
        return result
    return {"success": True, "account": result["account"]}


def list_business_accounts(token: str, business_id: str) -> dict:
    access = require_business_access(token, business_id)
    if not access["success"]:
        return access
    return {"success": True, "accounts": [
        _safe_account(row) for row in queries.list_active_financial_accounts(business_id)
    ]}


def update_account(token: str, account_id: str, account_data: dict) -> dict:
    access, row = _authorized_account(token, account_id, set(MANAGE_ROLES))
    if not access["success"]:
        return access
    try:
        values = _validate_account_data(account_data, existing=row)
        if not queries.update_financial_account(account_id, *values):
            return _error("ACCOUNT_UPDATE_FAILED", "Financial account update failed.")
        return {"success": True, "account": _safe_account(queries.get_financial_account(account_id)),
                "message": "Financial account updated successfully."}
    except ValueError as error:
        return _error("INVALID_INPUT", str(error))
    except sqlite3.IntegrityError:
        return _error("DUPLICATE_ACCOUNT", "An account with this identifier already exists for the business.")
    except Exception:
        return _error("ACCOUNT_UPDATE_FAILED", "Financial account update failed.")


def disable_account(token: str, account_id: str) -> dict:
    access, _ = _authorized_account(token, account_id, set(MANAGE_ROLES))
    if not access["success"]:
        return access
    if not queries.disable_financial_account(account_id):
        return _error("ACCOUNT_UPDATE_FAILED", "Financial account could not be disabled.")
    return {"success": True, "message": "Financial account disabled successfully."}
