from pathlib import Path

import pandas as pd


APP_DATA_DIR = Path(__file__).resolve().parent / "data"


def _data_path(data_folder: str | Path | None) -> Path:
    if data_folder is None or str(data_folder) == "data":
        return APP_DATA_DIR
    return Path(data_folder).expanduser().resolve()


def check_eligibility(business, data_folder=None):
    schemes = pd.read_csv(_data_path(data_folder) / "schemes.csv")
    results = []

    for _, scheme in schemes.iterrows():
        checks = []
        passed = True

        turnover_ok = scheme["min_turnover"] <= business["turnover"] <= scheme["max_turnover"]
        checks.append(("Turnover within range", turnover_ok))
        if not turnover_ok:
            passed = False

        state_ok = scheme["applicable_states"] == "Any" or scheme["applicable_states"] == business["state"]
        checks.append(("State matches", state_ok))
        if not state_ok:
            passed = False

        sector_ok = scheme["sector"] == "Any" or scheme["sector"] == business["sector"]
        checks.append(("Sector matches", sector_ok))
        if not sector_ok:
            passed = False

        category_ok = scheme["business_category"] == "Any" or scheme["business_category"] == business["business_category"]
        checks.append(("Business category matches", category_ok))
        if not category_ok:
            passed = False

        if pd.notna(scheme["min_age"]):
            age_min_ok = business["owner_age"] >= scheme["min_age"]
            checks.append((f"Owner age >= {int(scheme['min_age'])}", age_min_ok))
            if not age_min_ok:
                passed = False

        if pd.notna(scheme["max_age"]):
            age_max_ok = business["owner_age"] <= scheme["max_age"]
            checks.append((f"Owner age <= {int(scheme['max_age'])}", age_max_ok))
            if not age_max_ok:
                passed = False

        results.append({
            "scheme_name": scheme["scheme_name"],
            "benefit_summary": scheme["benefit_summary"],
            "source_url": scheme["source_url"],
            "last_verified_date": scheme["last_verified_date"],
            "eligible": passed,
            "checks": checks,
        })

    return results
