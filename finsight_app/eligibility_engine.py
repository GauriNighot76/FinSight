"""Government-scheme screening using the repository's structured scheme data."""

from pathlib import Path
from typing import Any

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SCHEMES_PATH = BASE_DIR / "data" / "schemes.csv"


def _schemes(path: str | Path | None = None) -> pd.DataFrame:
    return pd.read_csv(Path(path) if path else DEFAULT_SCHEMES_PATH)


def _clean(value: Any):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def find_relevant_schemes(
    profile: dict[str, Any],
    schemes_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Screen schemes without turning missing information into assumptions."""
    profile = profile if isinstance(profile, dict) else {}
    schemes = _schemes(schemes_path)
    results: list[dict[str, Any]] = []

    for _, scheme in schemes.iterrows():
        checks: list[dict[str, Any]] = []
        missing: list[str] = []
        failed: list[str] = []

        turnover = _clean(profile.get("annual_turnover"))
        if turnover is None:
            missing.append("Annual turnover")
        else:
            ok = float(scheme["min_turnover"]) <= float(turnover) <= float(scheme["max_turnover"])
            checks.append({"name": "Turnover within scheme range", "passed": ok})
            if not ok:
                failed.append("Turnover is outside the scheme range")

        required_state = str(scheme["applicable_states"])
        state = _clean(profile.get("state"))
        if required_state != "Any":
            if state is None:
                missing.append("State")
            else:
                ok = str(state).casefold() == required_state.casefold()
                checks.append({"name": "State requirement", "passed": ok})
                if not ok:
                    failed.append("State does not match")

        required_sector = str(scheme["sector"])
        sector = _clean(profile.get("sector"))
        if required_sector != "Any":
            if sector is None:
                missing.append("Scheme sector")
            else:
                ok = str(sector).casefold() == required_sector.casefold()
                checks.append({"name": "Sector requirement", "passed": ok})
                if not ok:
                    failed.append("Sector does not match")

        required_category = str(scheme["business_category"])
        category = _clean(profile.get("business_category"))
        if required_category != "Any":
            if category is None:
                missing.append("MSME / business category")
            else:
                ok = str(category).casefold() == required_category.casefold()
                checks.append({"name": "Business category requirement", "passed": ok})
                if not ok:
                    failed.append("Business category does not match")

        min_age = scheme.get("min_age")
        max_age = scheme.get("max_age")
        if pd.notna(min_age) or pd.notna(max_age):
            owner_age = _clean(profile.get("owner_age"))
            if owner_age is None:
                missing.append("Owner age")
            else:
                if pd.notna(min_age):
                    ok = int(owner_age) >= int(min_age)
                    checks.append({"name": f"Owner age at least {int(min_age)}", "passed": ok})
                    if not ok:
                        failed.append("Owner age is below the minimum")
                if pd.notna(max_age):
                    ok = int(owner_age) <= int(max_age)
                    checks.append({"name": f"Owner age at most {int(max_age)}", "passed": ok})
                    if not ok:
                        failed.append("Owner age is above the maximum")

        benefit = str(scheme["benefit_summary"])
        lower = benefit.casefold()

        def special(field: str, label: str, expected: bool = True):
            value = profile.get(field)
            if value is None:
                missing.append(label)
                return
            ok = bool(value) is expected
            checks.append({"name": label, "passed": ok})
            if not ok:
                failed.append(f"{label} requirement is not met")

        if "udyam registration" in lower:
            special("udyam_registered", "Udyam / MSME registration")
        if "dpiit" in lower:
            special("startup_recognized", "DPIIT startup recognition")
        if "repeat borrower" in lower:
            special("prior_tarun_repaid", "Prior Tarun loan repaid")
        if "new units only" in lower or "greenfield" in lower:
            special("new_or_greenfield", "New / greenfield enterprise status")

        if "woman or sc/st" in lower:
            ownership = _clean(profile.get("ownership_category"))
            if ownership in {None, "Prefer not to say"}:
                missing.append("Voluntary ownership category (woman or SC/ST, if applicable)")
            else:
                ok = ownership in {"Woman-owned", "SC/ST-owned"}
                checks.append({"name": "Target ownership category", "passed": ok})
                if not ok:
                    failed.append("Target ownership category requirement is not met")

        if failed:
            relevance = "Not matched based on supplied information"
        elif missing:
            relevance = "Potentially relevant"
        else:
            relevance = "Likely relevant based on supplied information"

        results.append({
            "scheme_name": scheme["scheme_name"],
            "benefit_summary": scheme["benefit_summary"],
            "source_url": scheme["source_url"],
            "last_verified_date": scheme["last_verified_date"],
            "relevance": relevance,
            "checks": checks,
            "failed_reasons": failed,
            "missing_information": missing,
            "information_required": ", ".join(dict.fromkeys(missing)),
            "eligible": relevance == "Likely relevant based on supplied information",
        })
    return results


def check_eligibility(business, data_folder=None):
    """Backward-compatible deterministic matcher used by older demo code/tests."""
    if data_folder is None:
        path = DEFAULT_SCHEMES_PATH
    else:
        path = Path(data_folder) / "schemes.csv"
    schemes = _schemes(path)
    results = []
    for _, scheme in schemes.iterrows():
        checks = []
        passed = True
        turnover_ok = scheme["min_turnover"] <= business["turnover"] <= scheme["max_turnover"]
        checks.append(("Turnover within range", turnover_ok)); passed &= bool(turnover_ok)
        state_ok = scheme["applicable_states"] == "Any" or scheme["applicable_states"] == business["state"]
        checks.append(("State matches", state_ok)); passed &= bool(state_ok)
        sector_ok = scheme["sector"] == "Any" or scheme["sector"] == business["sector"]
        checks.append(("Sector matches", sector_ok)); passed &= bool(sector_ok)
        category_ok = scheme["business_category"] == "Any" or scheme["business_category"] == business["business_category"]
        checks.append(("Business category matches", category_ok)); passed &= bool(category_ok)
        if pd.notna(scheme["min_age"]):
            ok = business["owner_age"] >= scheme["min_age"]
            checks.append((f"Owner age >= {int(scheme['min_age'])}", ok)); passed &= bool(ok)
        if pd.notna(scheme["max_age"]):
            ok = business["owner_age"] <= scheme["max_age"]
            checks.append((f"Owner age <= {int(scheme['max_age'])}", ok)); passed &= bool(ok)
        results.append({
            "scheme_name": scheme["scheme_name"],
            "benefit_summary": scheme["benefit_summary"],
            "source_url": scheme["source_url"],
            "last_verified_date": scheme["last_verified_date"],
            "eligible": bool(passed),
            "checks": checks,
        })
    return results


__all__ = ["check_eligibility", "find_relevant_schemes"]
