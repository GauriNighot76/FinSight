"""Transparent, profile-based government scheme screening.

This module is deliberately a screening tool. It helps a business identify
schemes worth reviewing; it never represents a lender or government approval.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


APP_DATA_DIR = Path(__file__).resolve().parent / "data"


def _data_path(data_folder: str | Path | None) -> Path:
    if data_folder is None or str(data_folder) == "data":
        return APP_DATA_DIR
    return Path(data_folder).expanduser().resolve()


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _number(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value) or _text(value).lower() in {"", "any", "not sure"}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> bool | None:
    text = _text(value).lower()
    if text in {"yes", "true", "1"}:
        return True
    if text in {"no", "false", "0"}:
        return False
    return None


def _is_any(value: Any) -> bool:
    return _text(value).lower() in {"", "any", "all", "nan"}


def _choice_check(label: str, requirement: Any, supplied: Any) -> dict[str, Any]:
    if _is_any(requirement):
        return {"label": label, "status": True, "detail": "Open to this profile"}
    if _is_any(supplied):
        return {"label": label, "status": None, "detail": "Add this detail to confirm"}
    passed = _text(requirement).lower() == _text(supplied).lower()
    return {
        "label": label,
        "status": passed,
        "detail": "Matches" if passed else f"Designed for {_text(requirement)} businesses",
    }


def _requirement_check(label: str, required: Any, supplied: Any) -> dict[str, Any]:
    required_value = _bool(required)
    if required_value is not True:
        return {"label": label, "status": True, "detail": "Not required for screening"}
    supplied_value = _bool(supplied)
    if supplied_value is None:
        return {"label": label, "status": None, "detail": "Confirm this detail"}
    return {
        "label": label,
        "status": supplied_value,
        "detail": "Confirmed" if supplied_value else "Required by this scheme",
    }


def _funding_check(scheme: pd.Series, requested_amount: Any) -> dict[str, Any]:
    minimum = _number(scheme.get("min_funding_amount"))
    maximum = _number(scheme.get("max_funding_amount"))
    requested = _number(requested_amount)
    if minimum is None and maximum is None:
        return {"label": "Funding range", "status": True, "detail": "No funding range used"}
    if requested is None:
        return {"label": "Funding range", "status": None, "detail": "Enter the amount you plan to seek"}
    passed = (minimum is None or requested >= minimum) and (maximum is None or requested <= maximum)
    if minimum is not None and maximum is not None:
        range_text = f"₹{minimum:,.0f} to ₹{maximum:,.0f}"
    elif maximum is not None:
        range_text = f"up to ₹{maximum:,.0f}"
    else:
        range_text = f"from ₹{minimum:,.0f}"
    return {"label": "Funding range", "status": passed, "detail": "Matches requested amount" if passed else f"Scheme range: {range_text}"}


def _age_checks(scheme: pd.Series, owner_age: Any) -> list[dict[str, Any]]:
    minimum, maximum, age = _number(scheme.get("min_age")), _number(scheme.get("max_age")), _number(owner_age)
    if minimum is None and maximum is None:
        return []
    if age is None:
        return [{"label": "Owner age", "status": None, "detail": "Add owner age to confirm"}]
    passed = (minimum is None or age >= minimum) and (maximum is None or age <= maximum)
    if minimum is not None and maximum is not None:
        range_text = f"{minimum:.0f}–{maximum:.0f} years"
    elif minimum is not None:
        range_text = f"{minimum:.0f}+ years"
    else:
        range_text = f"up to {maximum:.0f} years"
    return [{"label": "Owner age", "status": passed, "detail": "Within range" if passed else f"Required age: {range_text}"}]


def check_eligibility(business: dict[str, Any], data_folder: str | Path | None = None) -> list[dict[str, Any]]:
    """Return matched, needs-details, and not-matched scheme screenings."""
    schemes = pd.read_csv(_data_path(data_folder) / "schemes.csv").fillna("")
    results: list[dict[str, Any]] = []

    for _, scheme in schemes.iterrows():
        checks = [
            _choice_check("Business sector", scheme.get("sector"), business.get("sector")),
            _choice_check("Business state", scheme.get("applicable_states"), business.get("state")),
            _choice_check("Business category", scheme.get("business_category"), business.get("business_category")),
            _funding_check(scheme, business.get("funding_amount")),
            *_age_checks(scheme, business.get("owner_age")),
            _requirement_check("Udyam registration", scheme.get("requires_udyam"), business.get("has_udyam")),
            _requirement_check("New business / project", scheme.get("requires_new_unit"), business.get("is_new_unit")),
            _requirement_check("Woman or SC/ST founder", scheme.get("requires_woman_or_scst"), business.get("woman_or_scst")),
            _requirement_check("DPIIT recognition", scheme.get("requires_dpiit"), business.get("has_dpiit")),
        ]
        statuses = [check["status"] for check in checks]
        if any(status is False for status in statuses):
            match_status = "not_matched"
        elif any(status is None for status in statuses):
            match_status = "needs_details"
        else:
            match_status = "matched"
        results.append(
            {
                "scheme_id": _text(scheme.get("scheme_id")),
                "scheme_name": _text(scheme.get("scheme_name")),
                "benefit_summary": _text(scheme.get("benefit_summary")),
                "application_notes": _text(scheme.get("application_notes")),
                "source_url": _text(scheme.get("source_url")),
                "last_verified_date": _text(scheme.get("last_verified_date")),
                "match_status": match_status,
                "eligible": match_status == "matched",
                "checks": checks,
            }
        )
    return results


__all__ = ["check_eligibility"]
