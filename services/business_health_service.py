"""Read-only business health metrics and deterministic anomaly detection."""

from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

from database import queries
from services import analytics_service, auth_service


class BusinessHealthError(ValueError):
    """Safe error raised for invalid or unavailable health requests."""


def _decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (ArithmeticError, TypeError, ValueError):
        return default


def _percentage(numerator: Any, denominator: Any) -> Decimal:
    denominator_decimal = _decimal(denominator)
    if denominator_decimal == 0:
        return Decimal("0.00")
    return (
        _decimal(numerator) * Decimal(100) / denominator_decimal
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _signed_change(current: Any, previous: Any) -> Decimal:
    previous_decimal = _decimal(previous)
    if previous_decimal == 0:
        return Decimal("0.00")
    return (
        (_decimal(current) - previous_decimal) * Decimal(100) / previous_decimal
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _require_access(session_token: Any, business_id: Any) -> None:
    if type(session_token) is not str or not session_token:
        raise BusinessHealthError("Authentication is required for business health.")
    try:
        session = auth_service.validate_session(session_token)
    except Exception as error:
        raise BusinessHealthError(
            "Authentication is required for business health."
        ) from error
    if not isinstance(session, dict) or session.get("success") is not True:
        raise BusinessHealthError("Authentication is required for business health.")
    if type(business_id) is not str or not business_id:
        raise BusinessHealthError("The selected business is unavailable.")
    try:
        membership = queries.get_business_membership(
            business_id, session["user"]["user_id"]
        )
    except Exception as error:
        raise BusinessHealthError("The selected business is unavailable.") from error
    if (
        membership is None
        or not isinstance(membership, dict)
        or membership.get("business_status") != "active"
        or membership.get("membership_status") != "active"
    ):
        raise BusinessHealthError("The selected business is unavailable.")


def _safe_analytics_error(error: Any) -> str:
    message = str(error).lower()
    if "currency" in message:
        return "The selected analytics currency is inconsistent."
    if "account" in message:
        return "The selected financial account is unavailable."
    if "date" in message:
        return "The selected analytics date range is invalid."
    if "authentication" in message or "business" in message:
        return "The selected business is unavailable."
    return "Business health could not be loaded."


def _period_value(row: Any, key: str) -> Decimal:
    if key in row:
        return _decimal(row[key])
    if key == "net_cash_flow_minor":
        return _decimal(row.get("cashflow_minor"))
    return Decimal("0")


def _periods(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    trends = analysis.get("trends")
    if not isinstance(trends, dict):
        return []
    for name in ("daily", "weekly", "monthly"):
        values = trends.get(name)
        if isinstance(values, list) and values:
            return [row for row in values if isinstance(row, dict)]
    return []


def _transactions(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    values = analysis.get("transactions", [])
    if not isinstance(values, list):
        return []
    transactions = [row for row in values if isinstance(row, dict)]
    return sorted(
        transactions,
        key=lambda row: (
            str(row.get("transaction_date") or ""),
            str(row.get("direction") or ""),
            str(row.get("amount_minor") or ""),
            str(row.get("category") or ""),
            str(row.get("payment_mode") or ""),
        ),
    )


def _category_values(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    values = analysis.get("categories", [])
    if not isinstance(values, list):
        return []
    return [row for row in values if isinstance(row, dict)]


def _payment_values(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    values = analysis.get("payment_modes", [])
    if not isinstance(values, list):
        return []
    return [row for row in values if isinstance(row, dict)]


def _trend_values(analysis: dict[str, Any], name: str) -> list[dict[str, Any]]:
    """Return one well-formed trend series from an analytics response."""
    trends = analysis.get("trends")
    if not isinstance(trends, dict):
        return []
    values = trends.get(name)
    if not isinstance(values, list):
        return []
    return [row for row in values if isinstance(row, dict)]


def _cash_flow_stability(periods: list[dict[str, Any]]) -> Decimal:
    if not periods:
        return Decimal("0.00")
    positive = sum(_period_value(row, "net_cash_flow_minor") >= 0 for row in periods)
    return _percentage(positive, len(periods))


def _recurring_expense_burden(transactions: list[dict[str, Any]], total_expense: Any) -> Decimal:
    category_months: dict[str, set[str]] = defaultdict(set)
    category_expenses: dict[str, Decimal] = defaultdict(Decimal)
    for row in transactions:
        if row.get("direction") != "expense":
            continue
        category = str(row.get("category") or "Uncategorized")
        transaction_date = str(row.get("transaction_date") or "")
        month = transaction_date[:7]
        category_months[category].add(month)
        category_expenses[category] += _decimal(row.get("amount_minor"))
    recurring = sum(
        amount
        for category, amount in category_expenses.items()
        if len(category_months[category]) >= 2
    )
    return _percentage(recurring, total_expense)


def _health_score(metrics: dict[str, Any]) -> tuple[int, str]:
    if _decimal(metrics.get("transaction_count")) == 0:
        return 0, "Critical"
    score = 100
    ratio = _decimal(metrics["expense_to_income_ratio"])
    savings = _decimal(metrics["savings_rate"])
    stability = _decimal(metrics["cash_flow_stability"])
    concentration = _decimal(metrics["category_concentration"])
    recurring = _decimal(metrics["recurring_expense_burden"])

    if ratio > Decimal("1.00"):
        score -= 35
    elif ratio > Decimal("0.75"):
        score -= 20
    elif ratio > Decimal("0.50"):
        score -= 10
    if savings < 0:
        score -= 25
    elif savings < 10:
        score -= 15
    elif savings < 25:
        score -= 5
    if stability < 50:
        score -= 25
    elif stability < 75:
        score -= 15
    elif stability < 100:
        score -= 5
    if concentration > 60:
        score -= 10
    elif concentration > 40:
        score -= 5
    if recurring > 50:
        score -= 10
    elif recurring > 30:
        score -= 5
    if _decimal(metrics["monthly_decline"]) > 20:
        score -= 10

    score = max(0, min(100, score))
    if score >= 85:
        level = "Excellent"
    elif score >= 70:
        level = "Good"
    elif score >= 50:
        level = "Moderate"
    elif score >= 25:
        level = "Poor"
    else:
        level = "Critical"
    return score, level


def _affected_transaction(row: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if row is None:
        return None
    return {
        "date": row.get("transaction_date"),
        "direction": row.get("direction"),
        "amount_minor": row.get("amount_minor"),
        "category": row.get("category") or "Uncategorized",
        "payment_mode": row.get("payment_mode") or "Other",
    }


def _anomaly(
    anomaly_type: str,
    severity: str,
    row: Optional[dict[str, Any]],
    reason: str,
    trigger_metric: str,
    threshold: Any,
    *,
    period: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "type": anomaly_type,
        "severity": severity,
        "date": period or (row or {}).get("transaction_date"),
        "affected_transaction": _affected_transaction(row),
        "reason": reason,
        "trigger_metric": trigger_metric,
        "threshold": threshold,
    }


def _detect_transaction_anomalies(
    transactions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    anomalies: list[dict[str, Any]] = []
    by_direction: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in transactions:
        if row.get("direction") in {"income", "expense"}:
            by_direction[row["direction"]].append(row)

    for direction, rows in by_direction.items():
        average = (
            sum(_decimal(row.get("amount_minor")) for row in rows) / len(rows)
            if rows
            else Decimal("0")
        )
        threshold = average * Decimal(2)
        for row in rows:
            amount = _decimal(row.get("amount_minor"))
            if amount > threshold and threshold > 0:
                label = "income" if direction == "income" else "expense"
                anomalies.append(
                    _anomaly(
                        f"unusually_large_{label}",
                        "High",
                        row,
                        f"The {label} is more than twice the average {label} amount.",
                        "amount_minor",
                        threshold,
                    )
                )

    identical: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in transactions:
        key = (
            row.get("amount_minor"),
            row.get("direction"),
            row.get("category") or "Uncategorized",
            row.get("payment_mode") or "Other",
        )
        identical[key].append(row)
    for rows in identical.values():
        if len(rows) >= 2:
            anomalies.append(
                _anomaly(
                    "repeated_identical_transactions",
                    "Medium",
                    rows[0],
                    "The same amount, direction, category, and payment mode repeat.",
                    "identical_transaction_count",
                    2,
                )
            )
    return anomalies


def _detect_period_anomalies(
    analysis: dict[str, Any],
    metrics: dict[str, Any],
) -> list[dict[str, Any]]:
    anomalies: list[dict[str, Any]] = []
    monthly = sorted(
        _trend_values(analysis, "monthly"),
        key=lambda row: str(row.get("period") or ""),
    )
    if len(monthly) >= 2:
        previous, current = monthly[-2], monthly[-1]
        previous_expense = _decimal(previous.get("expense_minor"))
        current_expense = _decimal(current.get("expense_minor"))
        previous_income = _decimal(previous.get("income_minor"))
        current_income = _decimal(current.get("income_minor"))
        if previous_expense > 0 and current_expense >= previous_expense * Decimal("1.5"):
            anomalies.append(
                _anomaly(
                    "sudden_expense_spike",
                    "High",
                    None,
                    "Monthly expenses increased sharply compared with the prior period.",
                    "monthly_expense_growth",
                    Decimal("50.00"),
                    period=current.get("period"),
                )
            )
        if previous_expense > 0 and current_expense >= previous_expense * Decimal("2"):
            anomalies.append(
                _anomaly(
                    "expense_explosion",
                    "Critical",
                    None,
                    "Monthly expenses doubled or more compared with the prior period.",
                    "monthly_expense_growth",
                    Decimal("100.00"),
                    period=current.get("period"),
                )
            )
        if previous_income > 0 and current_income <= previous_income * Decimal("0.5"):
            anomalies.append(
                _anomaly(
                    "sudden_income_drop",
                    "High",
                    None,
                    "Monthly income fell to half or less of the prior period.",
                    "monthly_income_change",
                    Decimal("-50.00"),
                    period=current.get("period"),
                )
            )
        if previous_income > 0 and current_income == 0:
            anomalies.append(
                _anomaly(
                    "income_interruption",
                    "Critical",
                    None,
                    "No income was recorded after income in the prior period.",
                    "monthly_income_minor",
                    0,
                    period=current.get("period"),
                )
            )

    daily = _trend_values(analysis, "daily")
    parsed_daily: list[tuple[date, dict[str, Any]]] = []
    for period in daily:
        try:
            parsed_daily.append((date.fromisoformat(str(period.get("period"))), period))
        except (TypeError, ValueError):
            continue
    parsed_daily.sort(key=lambda item: item[0])
    for previous_day, current_day in zip(parsed_daily, parsed_daily[1:]):
        gap_days = (current_day[0] - previous_day[0]).days
        if gap_days > 7:
            anomalies.append(
                _anomaly(
                    "inactive_period",
                    "Low",
                    None,
                    "No transaction activity was recorded for more than a week.",
                    "inactive_days",
                    7,
                    period=current_day[0].isoformat(),
                )
            )

    for period in _periods(analysis):
        net = _period_value(period, "net_cash_flow_minor")
        if net < 0:
            anomalies.append(
                _anomaly(
                    "negative_cash_flow_period",
                    "Medium",
                    None,
                    "The selected period has negative net cash flow.",
                    "net_cash_flow_minor",
                    0,
                    period=period.get("period"),
                )
            )

    category_months: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: defaultdict(Decimal)
    )
    category_rows: dict[tuple[str, str], dict[str, Any]] = {}
    for row in _transactions(analysis):
        if row.get("direction") != "expense":
            continue
        category = str(row.get("category") or "Uncategorized")
        transaction_month = str(row.get("transaction_date") or "")[:7]
        if len(transaction_month) != 7:
            continue
        category_months[category][transaction_month] += _decimal(
            row.get("amount_minor")
        )
        key = (category, transaction_month)
        previous_row = category_rows.get(key)
        if previous_row is None or str(row.get("transaction_date") or "") >= str(
            previous_row.get("transaction_date") or ""
        ):
            category_rows[key] = row
    for category, month_values in category_months.items():
        months = sorted(month_values)
        if len(months) < 2:
            continue
        previous_month, current_month = months[-2], months[-1]
        previous_amount = month_values[previous_month]
        current_amount = month_values[current_month]
        if previous_amount > 0 and current_amount >= previous_amount * Decimal("1.5"):
            anomalies.append(
                _anomaly(
                    "category_spike",
                    "High",
                    category_rows.get((category, current_month)),
                    "Expense spending in a category increased sharply compared with the prior month.",
                    "category_monthly_growth",
                    Decimal("50.00"),
                    period=current_month,
                )
            )

    payment_modes = _payment_values(analysis)
    total_count = sum(int(_decimal(row.get("count"))) for row in payment_modes)
    if total_count >= 3:
        for row in payment_modes:
            if int(_decimal(row.get("count"))) == 1:
                anomalies.append(
                    _anomaly(
                        "unexpected_payment_mode",
                        "Medium",
                        None,
                        "This payment mode appears only once in the selected period.",
                        "payment_mode_count",
                        1,
                        period=None,
                    )
                )

    if _decimal(metrics["recurring_expense_burden"]) > 50:
        anomalies.append(
            _anomaly(
                "very_high_recurring_expenses",
                "High",
                None,
                "Recurring expenses consume more than half of total expenses.",
                "recurring_expense_burden",
                Decimal("50.00"),
            )
        )
    return anomalies


def _sort_anomalies(anomalies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        anomalies,
        key=lambda row: (
            str(row.get("date") or ""),
            str(row.get("type") or ""),
            str(row.get("severity") or ""),
        ),
    )


def get_business_health(
    *,
    session_token: str,
    business_id: str,
    account_id: str,
    start_date: str,
    end_date: str,
    currency: str,
) -> dict[str, Any]:
    """Return deterministic, read-only health metrics for one authorized account."""
    _require_access(session_token, business_id)
    try:
        analysis = analytics_service.get_financial_analytics(
            session_token=session_token,
            business_id=business_id,
            account_id=account_id,
            start_date=start_date,
            end_date=end_date,
            currency=currency,
        )
    except analytics_service.AnalyticsError as error:
        raise BusinessHealthError(_safe_analytics_error(error)) from error
    except Exception as error:
        raise BusinessHealthError("Business health could not be loaded.") from error

    if not isinstance(analysis, dict):
        raise BusinessHealthError("Business health could not be loaded.")
    kpis = analysis.get("kpis") if isinstance(analysis.get("kpis"), dict) else {}
    periods = _periods(analysis)
    categories = _category_values(analysis)
    transactions = _transactions(analysis)
    total_income = _decimal(kpis.get("total_income_minor"))
    total_expense = _decimal(kpis.get("total_expense_minor"))
    net_cash_flow = _decimal(kpis.get("net_cash_flow_minor"))

    monthly = sorted(
        _trend_values(analysis, "monthly"),
        key=lambda row: str(row.get("period") or ""),
    )
    previous_income = monthly[-2].get("income_minor") if len(monthly) >= 2 else 0
    current_income = monthly[-1].get("income_minor") if monthly else total_income
    previous_expense = monthly[-2].get("expense_minor") if len(monthly) >= 2 else 0
    current_expense = monthly[-1].get("expense_minor") if monthly else total_expense

    category_total = sum(_decimal(row.get("amount_minor")) for row in categories)
    largest_category = max(
        (_decimal(row.get("amount_minor")) for row in categories), default=Decimal("0")
    )
    largest_expense = max(
        (_decimal(row.get("expense_minor")) for row in categories), default=Decimal("0")
    )
    largest_income = max(
        (_decimal(row.get("income_minor")) for row in categories), default=Decimal("0")
    )
    metrics: dict[str, Any] = {
        "cash_flow_stability": _cash_flow_stability(periods),
        "income_trend": _signed_change(current_income, previous_income),
        "expense_trend": _signed_change(current_expense, previous_expense),
        "expense_to_income_ratio": (
            (total_expense / total_income).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if total_income
            else Decimal("0.00")
        ),
        "savings_rate": _decimal(kpis.get("savings_rate")),
        "recurring_expense_burden": _recurring_expense_burden(
            transactions, total_expense
        ),
        "category_concentration": _percentage(largest_category, category_total),
        "largest_expense_percentage": _percentage(largest_expense, total_expense),
        "largest_income_percentage": _percentage(largest_income, total_income),
        "monthly_growth": _percentage(
            _decimal(current_income) - _decimal(previous_income), previous_income
        )
        if _decimal(current_income) > _decimal(previous_income)
        else Decimal("0.00"),
        "monthly_decline": _percentage(
            _decimal(previous_income) - _decimal(current_income), previous_income
        )
        if _decimal(current_income) < _decimal(previous_income)
        else Decimal("0.00"),
        "cash_reserve_estimate_minor": kpis.get("closing_balance_minor"),
        "total_income_minor": kpis.get("total_income_minor", 0),
        "total_expense_minor": kpis.get("total_expense_minor", 0),
        "net_cash_flow_minor": kpis.get("net_cash_flow_minor", 0),
        "transaction_count": kpis.get("transaction_count", 0),
    }
    score, health_level = _health_score(metrics)
    metrics["overall_financial_health_score"] = score
    metrics["health_level"] = health_level

    anomalies = _detect_transaction_anomalies(transactions)
    anomalies.extend(_detect_period_anomalies(analysis, metrics))
    return {"metrics": metrics, "anomalies": _sort_anomalies(anomalies)}


analyze_business_health = get_business_health


__all__ = [
    "BusinessHealthError",
    "analyze_business_health",
    "get_business_health",
]
