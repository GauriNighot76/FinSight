import pandas as pd

schemes = pd.read_csv("data/schemes.csv")

# ---- BUSINESS PROFILE ----
# revenue and expenses came from step 2 (real, computed from actual transactions).
# turnover here is ANNUAL, not the 2-year total -- schemes define limits per year.
annual_turnover = 582807 / 2   # = 291,403.5

# these fields don't exist anywhere in the coffee shop dataset, since it's just
# bank/payroll records -- they are ASSUMPTIONS we're making for this demo,
# and must be said out loud as assumptions, not presented as real data
business = {
    "business_name": "Demo Coffee Shop (synthetic dataset)",
    "turnover": annual_turnover,
    "sector": "Service",
    "state": "Maharashtra",          # ASSUMED -- not in source data
    "business_category": "Micro",    # ASSUMED -- inferred from turnover size
    "owner_age": 30,                 # ASSUMED -- not in source data
}


def check_eligibility(business, schemes_df):
    matches = []
    for _, scheme in schemes_df.iterrows():
        if business["turnover"] < scheme["min_turnover"]:
            continue
        if business["turnover"] > scheme["max_turnover"]:
            continue
        if scheme["applicable_states"] != "Any" and scheme["applicable_states"] != business["state"]:
            continue
        if scheme["sector"] != "Any" and scheme["sector"] != business["sector"]:
            continue
        if scheme["business_category"] != "Any" and scheme["business_category"] != business["business_category"]:
            continue
        if pd.notna(scheme["min_age"]) and business["owner_age"] < scheme["min_age"]:
            continue
        if pd.notna(scheme["max_age"]) and business["owner_age"] > scheme["max_age"]:
            continue
        # NOTE: new-business-only check removed to match simplified schemes.csv.
        # PMEGP in particular excludes businesses that already got a prior govt
        # subsidy -- without this column, that rule isn't being enforced here.
        matches.append(scheme["scheme_name"])
    return matches


matches = check_eligibility(business, schemes)

print(f"Business: {business['business_name']}")
print(f"Annual turnover (computed): Rs {annual_turnover:,.0f}")
print(f"Sector: {business['sector']} | State: {business['state']} (assumed) | Category: {business['business_category']} (assumed)")
print()
if matches:
    print("Matched schemes:")
    for m in matches:
        print(f"  -> {m}")
else:
    print("No schemes matched.")
