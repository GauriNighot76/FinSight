from decimal import Decimal
import re

from database import queries
from finsight_app.business_ui import BUSINESS_TYPES
from finsight_app.eligibility_engine import find_relevant_schemes
from finsight_app.pdf_generator import generate_business_report
from services import (
    account_service,
    analytics_service,
    auth_service,
    business_service,
    business_health_service,
    csv_normalizer,
    decision_support_service,
    ingestion_service,
    report_service,
)


CONTROLLED_CSV = b"""Date,Description,Amount,Direction,Category,Payment Mode
2026-08-01,Cash Sale,10000,income,Sales,Cash
2026-08-02,UPI Sale,5000,income,Sales,UPI
2026-08-03,Rent,4000,expense,Rent,Bank
2026-08-04,Electricity,1000,expense,Utilities,UPI
"""

NONSTANDARD_CSV = b"""Txn Date,Narration,Value,Type,Classification,Channel
2026-08-01,Cash Sale,10000,income,Sales,Cash
2026-08-02,UPI Sale,5000,income,Sales,UPI
2026-08-03,Rent,4000,expense,Rent,Bank
2026-08-04,Electricity,1000,expense,Utilities,UPI
"""


def _user():
    signup = auth_service.signup(
        "Final User", "final@example.com", "9000000011", "StrongPass1"
    )
    assert signup["success"]
    login = auth_service.login("final@example.com", "StrongPass1")
    assert login["success"]
    return signup["user"], login["session"]["token"]


def _business(token, name):
    created = business_service.create_business(
        token,
        {"business_name": name, "business_type": "Retail"},
    )
    assert created["success"]
    ready = business_service.ensure_business_ready(
        token, created["business"]["business_id"]
    )
    assert ready["success"]
    return created["business"], ready["account_id"]


def _analytics(token, business_id, account_id):
    return analytics_service.get_financial_analytics(
        session_token=token,
        business_id=business_id,
        account_id=account_id,
        start_date="2026-08-01",
        end_date="2026-08-04",
        currency="INR",
    )


def test_final_controlled_workflow_multi_business_isolation_duplicates_and_pdf():
    _user_row, token = _user()
    business_a, account_a = _business(token, "Business A")
    business_b, account_b = _business(token, "Business B")

    listed = business_service.list_user_businesses(token)["businesses"]
    assert {row["business_id"] for row in listed} == {
        business_a["business_id"], business_b["business_id"]
    }

    mapping = csv_normalizer.suggest_column_mapping(NONSTANDARD_CSV)
    assert mapping["Txn Date"] == "transaction_date"
    assert mapping["Narration"] == "description"
    assert mapping["Value"] == "amount"
    assert mapping["Type"] == "direction"
    assert mapping["Classification"] == "category"
    assert mapping["Channel"] == "payment_method"

    payload = csv_normalizer.normalize_csv_with_mapping(NONSTANDARD_CSV, mapping)
    assert len(payload["records"]) == 4
    preview = csv_normalizer.preview_rows_from_payload(payload)
    validation = csv_normalizer.validate_preview_rows(preview)
    assert validation["valid"] is True
    assert validation["invalid_count"] == 0

    source_records = validation["payload"]["records"]
    source_income = sum(
        row["amount_minor"] for row in source_records
        if row["direction"] == "income"
    )
    source_expense = sum(
        row["amount_minor"] for row in source_records
        if row["direction"] == "expense"
    )
    source_count = len(source_records)

    first = ingestion_service.ingest(
        session_token=token,
        business_id=business_a["business_id"],
        account_id=account_a,
        payload=validation["payload"],
    )
    assert (first.inserted_count, first.duplicate_count) == (4, 0)

    again = ingestion_service.ingest(
        session_token=token,
        business_id=business_a["business_id"],
        account_id=account_a,
        payload=validation["payload"],
    )
    assert (again.inserted_count, again.duplicate_count) == (0, 4)

    a = _analytics(token, business_a["business_id"], account_a)
    b = _analytics(token, business_b["business_id"], account_b)

    with queries.get_connection() as connection:
        db_totals = connection.execute(
            """SELECT
                   COUNT(*) AS transaction_count,
                   COALESCE(SUM(CASE WHEN direction='income' THEN amount_minor ELSE 0 END), 0)
                     AS total_income_minor,
                   COALESCE(SUM(CASE WHEN direction='expense' THEN amount_minor ELSE 0 END), 0)
                     AS total_expense_minor
               FROM ingested_transaction_identities
               WHERE business_id=? AND account_id=?
                 AND transaction_date BETWEEN ? AND ?""",
            (
                business_a["business_id"],
                account_a,
                "2026-08-01",
                "2026-08-04",
            ),
        ).fetchone()

    assert source_income == db_totals["total_income_minor"] == a["kpis"]["total_income_minor"]
    assert source_expense == db_totals["total_expense_minor"] == a["kpis"]["total_expense_minor"]
    assert source_count == db_totals["transaction_count"] == a["kpis"]["transaction_count"]
    assert a["kpis"]["total_income_minor"] == 1_500_000
    assert a["kpis"]["total_expense_minor"] == 500_000
    assert a["kpis"]["net_cash_flow_minor"] == 1_000_000
    assert a["kpis"]["transaction_count"] == 4
    assert b["kpis"]["total_income_minor"] == 0
    assert b["kpis"]["total_expense_minor"] == 0
    assert b["kpis"]["net_cash_flow_minor"] == 0
    assert b["kpis"]["transaction_count"] == 0

    assert {row["category"] for row in a["categories"]} == {
        "Sales", "Rent", "Utilities"
    }
    assert {row["payment_mode"] for row in a["payment_modes"]} == {
        "Cash", "UPI", "Bank"
    }
    assert {row["description"] for row in a["transactions"]} == {
        "Cash Sale", "UPI Sale", "Rent", "Electricity"
    }

    sales = next(row for row in a["categories"] if row["category"] == "Sales")
    rent = next(row for row in a["categories"] if row["category"] == "Rent")
    utilities = next(row for row in a["categories"] if row["category"] == "Utilities")
    assert sales["income_minor"] == 1_500_000
    assert sales["expense_minor"] == 0
    assert sales["income_count"] == 2
    assert sales["income_percentage"] == Decimal("100.00")
    assert rent["expense_minor"] == 400_000
    assert rent["expense_percentage"] == Decimal("80.00")
    assert utilities["expense_minor"] == 100_000
    assert utilities["expense_percentage"] == Decimal("20.00")

    cash = next(row for row in a["payment_modes"] if row["payment_mode"] == "Cash")
    upi = next(row for row in a["payment_modes"] if row["payment_mode"] == "UPI")
    bank = next(row for row in a["payment_modes"] if row["payment_mode"] == "Bank")
    assert (cash["income_minor"], cash["expense_minor"]) == (1_000_000, 0)
    assert (upi["income_minor"], upi["expense_minor"]) == (500_000, 100_000)
    assert (bank["income_minor"], bank["expense_minor"]) == (0, 400_000)

    report_args = dict(
        session_token=token,
        business_id=business_a["business_id"],
        account_id=account_a,
        start_date="2026-08-01",
        end_date="2026-08-04",
        currency="INR",
    )
    report = report_service.build_report(**report_args)
    support = decision_support_service.get_decision_support(**report_args)
    health = business_health_service.get_business_health(**report_args)

    summary = report["sections"]["financial_summary"]
    assert summary["total_income_minor"] == a["kpis"]["total_income_minor"]
    assert summary["total_expense_minor"] == a["kpis"]["total_expense_minor"]
    assert summary["net_cash_flow_minor"] == a["kpis"]["net_cash_flow_minor"]
    assert summary["transaction_count"] == a["kpis"]["transaction_count"]
    assert report["sections"]["category_report"] == a["categories"]
    assert report["sections"]["payment_mode_report"] == a["payment_modes"]

    health_ids = [item["anomaly_id"] for item in health["anomalies"]]
    report_ids = [
        item["anomaly_id"]
        for item in report["sections"]["anomaly_report"]
    ]
    assert len(health_ids) == len(set(health_ids))
    assert report_ids == health_ids

    pdf = generate_business_report(
        business=business_a,
        report=report,
        decision_support=support,
        scheme_results=[],
    ).getvalue()
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000
    assert b"FinSight" in pdf
    assert b"Business A" in pdf
    assert b"2026-08-01 to 2026-08-04" in pdf
    assert b"INR 15,000.00" in pdf
    assert b"INR 5,000.00" in pdf
    assert b"INR 10,000.00" in pdf
    assert b"Sales" in pdf
    assert b"Rent" in pdf
    assert b"Utilities" in pdf
    page_count = len(re.findall(rb"/Type\s*/Page\b", pdf))
    assert 3 <= page_count <= 6
    assert b"EBITDA" not in pdf
    assert b"Net income:" not in pdf
    assert b"Cash runway:" not in pdf
    assert b"Gross margin" in pdf
    assert b"Not available from supplied data" in pdf

    assert auth_service.logout(token)["success"] is True
    relogin = auth_service.login("final@example.com", "StrongPass1")
    assert relogin["success"] is True
    new_token = relogin["session"]["token"]
    restored = business_service.list_user_businesses(new_token)["businesses"]
    assert {row["business_id"] for row in restored} == {
        business_a["business_id"], business_b["business_id"]
    }
    persisted = _analytics(new_token, business_a["business_id"], account_a)
    assert persisted["kpis"]["transaction_count"] == 4
    assert persisted["kpis"]["net_cash_flow_minor"] == 1_000_000



def test_realistic_large_csv_over_old_limit_ingests_all_rows():
    _user_row, token = _user()
    business, account_id = _business(token, "Large Import Retail")
    record_count = 1200
    rows = ["Date,Description,Amount,Direction,Category,Payment Mode"] + [
        f"2026-08-01,Sale {index},{index}.00,income,Sales,UPI"
        for index in range(1, record_count + 1)
    ]
    payload = csv_normalizer.normalize_csv("\n".join(rows).encode("utf-8"))

    assert len(payload["records"]) == record_count

    result = ingestion_service.ingest(
        session_token=token,
        business_id=business["business_id"],
        account_id=account_id,
        payload=payload,
    )

    assert result.record_count == record_count
    assert result.inserted_count == record_count
    assert result.duplicate_count == 0
    analytics = _analytics(token, business["business_id"], account_id)
    assert analytics["kpis"]["transaction_count"] == record_count
    assert analytics["kpis"]["total_income_minor"] == sum(
        index * 100 for index in range(1, record_count + 1)
    )


def test_duplicate_business_display_names_keep_distinct_scopes():
    _user_row, token = _user()
    first, first_account = _business(token, "Same Name")
    second, second_account = _business(token, "Same Name")
    assert first["business_id"] != second["business_id"]
    listed = business_service.list_user_businesses(token)["businesses"]
    assert len([row for row in listed if row["business_name"] == "Same Name"]) == 2
    assert first_account != second_account
    first_result = _analytics(token, first["business_id"], first_account)
    second_result = _analytics(token, second["business_id"], second_account)
    assert first_result["kpis"]["transaction_count"] == 0
    assert second_result["kpis"]["transaction_count"] == 0


def test_existing_business_is_repaired_idempotently_without_admin_bridge(
    isolated_test_database,
):
    user, token = _user()
    business_id = "biz_pre_runtime"
    membership_id = "mem_pre_runtime"
    with isolated_test_database() as connection:
        connection.execute(
            """INSERT INTO businesses
               (business_id,business_name,business_type)
               VALUES (?,?,?)""",
            (business_id, "Older Retail", "Retail"),
        )
        connection.execute(
            """INSERT INTO business_memberships
               (membership_id,business_id,user_id,membership_role)
               VALUES (?,?,?,'owner')""",
            (membership_id, business_id, user["user_id"]),
        )

    first = business_service.ensure_business_ready(token, business_id)
    second = business_service.ensure_business_ready(token, business_id)
    assert first["success"] and second["success"]
    assert first["account_id"] == second["account_id"]

    with isolated_test_database() as connection:
        registry = connection.execute(
            "SELECT * FROM business_registry WHERE business_id=?", (business_id,)
        ).fetchone()
        accounts = connection.execute(
            "SELECT COUNT(*) FROM financial_accounts WHERE business_id=?",
            (business_id,),
        ).fetchone()[0]
        bridges = connection.execute(
            "SELECT COUNT(*) FROM business_registry_bridges WHERE business_id=?",
            (business_id,),
        ).fetchone()[0]
        linked = connection.execute(
            "SELECT ledger_registry_business_id FROM businesses WHERE business_id=?",
            (business_id,),
        ).fetchone()[0]
    assert registry is not None
    assert registry["user_id"] == user["user_id"]
    assert accounts == 1
    assert bridges == 0
    assert linked == business_id


def test_preview_validation_reports_invalid_rows_without_payload():
    raw = b"""Date,Description,Amount,Direction,Category,Payment Mode
2026-08-01,Sale,100.00,income,Sales,Cash
2026-08-02,Rent,not-a-number,expense,Rent,Bank
"""
    mapping = csv_normalizer.suggest_column_mapping(raw)
    rows = csv_normalizer.preview_csv_with_mapping(raw, mapping)
    assert rows[1]["Amount"] == "not-a-number"
    result = csv_normalizer.validate_preview_rows(rows)
    assert result["valid"] is False
    assert result["invalid_count"] == 1
    assert result["errors"][0]["row"] == 2
    assert result["payload"] is None


def test_minor_units_and_business_type_default_are_submission_safe():
    payload = csv_normalizer.normalize_csv(
        b"Date,Amount,Direction\n2026-08-01,1234.50,income\n"
    )
    assert payload["records"][0]["amount_minor"] == 123450
    assert BUSINESS_TYPES[0] == "Select business type"
    assert BUSINESS_TYPES[0] != "Medical / Pharmacy"


def test_scheme_engine_invoked_with_real_repository_rules_and_missing_information():
    results = find_relevant_schemes({
        "state": "Maharashtra",
        "sector": "Service",
        "business_category": "Micro",
        "annual_turnover": 250000,
        "owner_age": 30,
        "udyam_registered": None,
        "startup_recognized": None,
        "new_or_greenfield": None,
        "prior_tarun_repaid": None,
        "ownership_category": "Prefer not to say",
    })
    assert results
    cgtmse = next(
        row for row in results if row["scheme_name"] == "CGTMSE Collateral-Free Loan"
    )
    assert cgtmse["relevance"] in {
        "Potentially relevant",
        "Likely relevant based on supplied information",
    }
    assert "Udyam / MSME registration" in cgtmse["missing_information"]
    assert cgtmse["source_url"]
