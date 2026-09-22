from decimal import Decimal
import inspect

from services import business_health_service as service


def _transaction(
    direction,
    amount,
    index,
    *,
    date="2026-06-01",
    category="Sales",
    payment_mode="UPI",
    description=None,
):
    return {
        "transaction_date": date,
        "amount_minor": amount,
        "direction": direction,
        "category": category,
        "payment_mode": payment_mode,
        "description": description or f"{direction.title()} {index}",
    }


def _old_mean_flag_count(transactions, direction):
    amounts = [
        Decimal(str(row["amount_minor"]))
        for row in transactions
        if row["direction"] == direction
    ]
    average = sum(amounts, Decimal("0")) / Decimal(len(amounts))
    threshold = average * Decimal(2)
    return sum(amount > threshold for amount in amounts)


def _realistic_skewed_population():
    incomes = [
        _transaction("income", 100 + index * 5, index, date=f"2026-01-{index % 28 + 1:02d}")
        for index in range(70)
    ]
    incomes.extend(
        _transaction(
            "income",
            1000 + index * 30,
            70 + index,
            date=f"2026-02-{index % 28 + 1:02d}",
        )
        for index in range(28)
    )
    incomes.extend(
        [
            _transaction("income", 8000, 98, date="2026-03-03", description="Exceptional Sale A"),
            _transaction("income", 12000, 99, date="2026-03-17", description="Exceptional Sale B"),
        ]
    )

    expenses = [
        _transaction(
            "expense",
            150 + index * 7,
            index,
            date=f"2026-04-{index % 28 + 1:02d}",
            category="Inventory",
            payment_mode="Bank",
        )
        for index in range(60)
    ]
    expenses.extend(
        _transaction(
            "expense",
            1200 + index * 45,
            60 + index,
            date=f"2026-05-{index % 28 + 1:02d}",
            category="Inventory",
            payment_mode="Bank",
        )
        for index in range(18)
    )
    expenses.extend(
        [
            _transaction(
                "expense",
                9000,
                78,
                date="2026-06-05",
                category="Inventory",
                payment_mode="Bank",
                description="Exceptional Purchase A",
            ),
            _transaction(
                "expense",
                15000,
                79,
                date="2026-06-20",
                category="Inventory",
                payment_mode="Bank",
                description="Exceptional Purchase B",
            ),
        ]
    )
    return incomes + expenses


def test_robust_outlier_rule_reduces_false_high_rate_on_skewed_msme_population():
    transactions = _realistic_skewed_population()

    assert _old_mean_flag_count(transactions, "income") == 11
    assert _old_mean_flag_count(transactions, "expense") == 5

    anomalies = service._detect_transaction_anomalies(transactions)
    large_income = [row for row in anomalies if row["type"] == "unusually_large_income"]
    large_expense = [row for row in anomalies if row["type"] == "unusually_large_expense"]

    assert len(large_income) == 2
    assert len(large_expense) == 2
    assert Decimal(len(large_income)) / Decimal(100) == Decimal("0.02")
    assert Decimal(len(large_expense)) / Decimal(80) == Decimal("0.025")
    assert {row["metric_value"] for row in large_income} == {Decimal("8000"), Decimal("12000")}
    assert {row["metric_value"] for row in large_expense} == {Decimal("9000"), Decimal("15000")}
    assert all(row["severity"] == "HIGH" for row in large_income + large_expense)


def test_true_large_outlier_is_detected_with_documented_outer_fence():
    transactions = [
        _transaction("income", amount, index)
        for index, amount in enumerate([100, 110, 120, 130, 140, 150, 160, 1000])
    ]

    anomalies = service._detect_transaction_anomalies(transactions)
    large = [row for row in anomalies if row["type"] == "unusually_large_income"]

    assert len(large) == 1
    assert large[0]["metric_value"] == Decimal("1000")
    assert large[0]["detection_context"]["sample_size"] == 8
    assert large[0]["detection_context"]["iqr_multiplier"] == Decimal("3")
    assert large[0]["threshold"] == Decimal("275")


def test_income_and_expense_outlier_baselines_are_independent():
    incomes = [
        _transaction("income", amount, index)
        for index, amount in enumerate([100, 110, 120, 130, 140, 150, 160, 1000])
    ]
    expenses = [
        _transaction("expense", amount, index, category="Inventory", payment_mode="Bank")
        for index, amount in enumerate([10000, 11000, 12000, 13000, 14000, 15000, 16000, 17000])
    ]

    income_only = service._detect_transaction_anomalies(incomes)
    combined = service._detect_transaction_anomalies(incomes + expenses)
    first = next(row for row in income_only if row["type"] == "unusually_large_income")
    second = next(row for row in combined if row["type"] == "unusually_large_income")

    assert first["threshold"] == second["threshold"] == Decimal("275")
    assert not any(row["type"] == "unusually_large_expense" for row in combined)


def test_small_sample_does_not_make_statistical_high_outlier_claim():
    transactions = [
        _transaction("income", amount, index)
        for index, amount in enumerate([100, 110, 120, 130, 140, 150, 10000])
    ]

    anomalies = service._detect_transaction_anomalies(transactions)

    assert not any(row["type"].startswith("unusually_large_") for row in anomalies)


def test_zero_iqr_population_does_not_generate_large_transaction_anomalies():
    transactions = [
        _transaction("income", 500, index, date=f"2026-01-{index + 1:02d}")
        for index in range(12)
    ]

    anomalies = service._detect_transaction_anomalies(transactions)

    assert not any(row["type"].startswith("unusually_large_") for row in anomalies)


def test_same_date_genuine_outliers_remain_separate_with_human_context():
    transactions = [
        _transaction("expense", amount, index, date=f"2026-03-{index + 1:02d}", category="Inventory", payment_mode="Bank")
        for index, amount in enumerate([100, 110, 120, 130, 140, 150, 160, 170])
    ]
    transactions.extend(
        [
            _transaction(
                "expense",
                1000,
                8,
                date="2026-03-19",
                category="Inventory",
                payment_mode="Bank",
                description="Bulk antibiotic purchase",
            ),
            _transaction(
                "expense",
                1200,
                9,
                date="2026-03-19",
                category="Cold Chain",
                payment_mode="UPI",
                description="Cold storage repair",
            ),
        ]
    )

    raw = service._detect_transaction_anomalies(transactions)
    final = service._finalize_anomalies(
        raw,
        business_id="business-1",
        account_id="account-1",
    )
    large = [row for row in final if row["type"] == "unusually_large_expense"]

    assert len(large) == 2
    assert len({row["anomaly_id"] for row in large}) == 2
    assert {row["affected_transaction"]["description"] for row in large} == {
        "Bulk antibiotic purchase",
        "Cold storage repair",
    }
    assert {row["affected_transaction"]["category"] for row in large} == {
        "Inventory",
        "Cold Chain",
    }


def test_category_and_recurring_same_movement_emit_only_specific_recurring_finding():
    analysis = {
        "trends": {"daily": [], "weekly": [], "monthly": []},
        "payment_modes": [],
        "transactions": [
            _transaction("expense", 100, 1, date="2026-06-05", category="Inventory", payment_mode="Bank"),
            _transaction("expense", 100, 2, date="2026-06-06", category="Utilities", payment_mode="UPI"),
            _transaction("expense", 250, 3, date="2026-07-05", category="Inventory", payment_mode="Bank"),
            _transaction("expense", 200, 4, date="2026-07-06", category="Utilities", payment_mode="UPI"),
        ],
    }
    metrics = {
        "expense_to_income_ratio": Decimal("0.50"),
        "cash_flow_stability": Decimal("100.00"),
        "recurring_expense_burden": Decimal("0.00"),
    }

    raw = service._detect_period_anomalies(analysis, metrics)
    assert sum(row["type"] == "category_spike" for row in raw) == 2
    assert sum(row["type"] == "recurring_expense_growth" for row in raw) == 2

    final = service._finalize_anomalies(
        raw,
        business_id="business-1",
        account_id="account-1",
    )
    recurring = [
        row for row in final
        if row["type"] == "recurring_expense_growth"
    ]

    assert not any(row["type"] == "category_spike" for row in final)
    assert len(recurring) == 2
    assert {row["detection_context"]["category"] for row in recurring} == {
        "Inventory",
        "Utilities",
    }
    assert len({row["anomaly_id"] for row in recurring}) == 2

    duplicated = service._finalize_anomalies(
        raw + [dict(next(row for row in raw if row["type"] == "recurring_expense_growth"))],
        business_id="business-1",
        account_id="account-1",
    )
    assert sum(row["type"] == "recurring_expense_growth" for row in duplicated) == 2


def test_canonical_anomaly_engine_has_no_legacy_two_mean_path():
    source = inspect.getsource(service._detect_transaction_anomalies).lower()

    assert service.ANOMALY_ENGINE_VERSION == "finsight_tukey_outer_v1"
    assert "twice the average" not in source
    assert "average * decimal(2)" not in source
    assert "_tukey_outer_fence" in source


def test_repeated_amount_pair_is_not_called_duplicate_but_stronger_pattern_is_review_signal():
    pair = [
        _transaction("income", 500, 1, date="2026-01-01", category="Sales", payment_mode="Cash"),
        _transaction("income", 500, 2, date="2026-01-02", category="Sales", payment_mode="Cash"),
    ]
    assert not any(
        row["type"] == "repeated_identical_transactions"
        for row in service._detect_transaction_anomalies(pair)
    )

    repeated = pair + [
        _transaction("income", 500, 3, date="2026-01-03", category="Sales", payment_mode="Cash"),
        _transaction("income", 500, 4, date="2026-01-04", category="Sales", payment_mode="Cash"),
    ]
    findings = service._detect_transaction_anomalies(repeated)
    pattern = next(row for row in findings if row["type"] == "repeated_identical_transactions")

    assert pattern["severity"] == "LOW"
    assert pattern["detection_context"]["occurrence_count"] == 4
    assert pattern["detection_context"]["distinct_date_count"] == 4
    assert "not proof of duplicate" in pattern["reason"].lower()


def test_negative_cash_flow_period_is_explicitly_daily_and_low_severity():
    analysis = {
        "trends": {
            "daily": [
                {
                    "period": "2026-07-04",
                    "income_minor": 100,
                    "expense_minor": 300,
                    "net_cash_flow_minor": -200,
                }
            ],
            "weekly": [],
            "monthly": [],
        },
        "transactions": [],
        "payment_modes": [],
    }
    metrics = {
        "expense_to_income_ratio": Decimal("0.50"),
        "cash_flow_stability": Decimal("100.00"),
        "recurring_expense_burden": Decimal("0.00"),
    }

    finding = next(
        row
        for row in service._detect_period_anomalies(analysis, metrics)
        if row["type"] == "negative_cash_flow_period"
    )

    assert finding["severity"] == "LOW"
    assert finding["affected_period"] if "affected_period" in finding else finding["date"] == "2026-07-04"
    assert finding["detection_context"]["period_kind"] == "daily"
    assert "on this day" in finding["reason"].lower()
