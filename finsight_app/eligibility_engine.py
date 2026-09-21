from pathlib import Path

import pandas as pd


DATA_FOLDER = Path(__file__).resolve().parent / "data"


def check_eligibility(business, data_folder=DATA_FOLDER):
    data_folder = Path(data_folder)
    schemes = pd.read_csv(f"{data_folder}/schemes.csv")
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
