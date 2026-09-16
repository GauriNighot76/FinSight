"""Read-only business health metrics and deterministic anomaly detection."""

from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from statistics import median
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
    if isinstance(membership, dict):
        business_status = membership.get("business_status")
        membership_status = membership.get("membership_status")
        membership_role = membership.get("membership_role")
    else:
        try:
            business_status = membership["business_status"]
            membership_status = membership["membership_status"]
            membership_role = membership["membership_role"]
        except (KeyError, TypeError):
            business_status = membership_status = membership_role = None
    if (
        membership is None
        or business_status != "active"
        or membership_status != "active"
        or membership_role not in {"owner", "manager"}
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
        if "cashflow_minor" in row:
            return _decimal(row.get("cashflow_minor"))
        return _decimal(row.get("income_minor")) - _decimal(
            row.get("expense_minor")
        )
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
    metric_value: Any = None,
) -> dict[str, Any]:
    transaction_reference = None
    if isinstance(row, dict):
        transaction_reference = row.get("transaction_reference") or row.get(
            "source_transaction_id"
        )
    return {
        "type": anomaly_type,
        "severity": severity,
        "date": period or (row or {}).get("transaction_date"),
        "affected_transaction": _affected_transaction(row),
        "reason": reason,
        "trigger_metric": trigger_metric,
        "threshold": threshold,
        "metric_value": threshold if metric_value is None else metric_value,
        "transaction_reference": transaction_reference,
    }


def _detect_transaction_anomalies(
    transactions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Find a small set of material, explainable transaction exceptions.

    Values are compared with transactions of the same direction and category.
    Median absolute deviation is deliberately used instead of a global average:
    regular rent and payroll must not become suspicious merely because most
    day-to-day receipts are smaller.
    """
    anomalies: list[dict[str, Any]] = []
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in transactions:
        direction = row.get("direction")
        if direction in {"income", "expense"}:
            category = str(row.get("category") or "Uncategorized")
            groups[(direction, category)].append(row)

    for (direction, category), rows in groups.items():
        if len(rows) < 8:
            continue
        amounts = [_decimal(row.get("amount_minor")) for row in rows]
        centre = Decimal(str(median(amounts)))
        deviations = [abs(value - centre) for value in amounts]
        mad = Decimal(str(median(deviations)))
        # Six MADs is intentionally conservative.  The percentage floor avoids
        # noisy flags where a category normally contains near-identical prices.
        threshold = centre + max(mad * Decimal(6), centre * Decimal("1.5"))
        for row in rows:
            amount = _decimal(row.get("amount_minor"))
            if amount > threshold and threshold > 0:
                label = "income" if direction == "income" else "expense"
                anomalies.append(
                    _anomaly(
                        "amount_outside_usual_range",
                        "Medium",
                        row,
                        f"This {label} is above the usual range for {category}.",
                        "amount_minor",
                        threshold,
                        metric_value=amount,
                    )
                )
    return sorted(
        anomalies,
        key=lambda item: _decimal(item.get("metric_value")),
        reverse=True,
    )[:20]


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
        if previous_expense > 0 and current_expense >= previous_expense * Decimal("2"):
            anomalies.append(
                _anomaly(
                    "monthly_expenses_doubled",
                    "Critical",
                    None,
                    "Monthly expenses doubled compared with the previous month.",
                    "monthly_expense_growth",
                    Decimal("100.00"),
                    period=current.get("period"),
                )
            )
        elif previous_expense > 0 and current_expense >= previous_expense * Decimal("1.5"):
            anomalies.append(
                _anomaly(
                    "monthly_expense_increase",
                    "High",
                    None,
                    "Monthly expenses increased by at least 50% compared with the previous month.",
                    "monthly_expense_growth",
                    Decimal("50.00"),
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

    expense_ratio = _decimal(metrics.get("expense_to_income_ratio"))
    if expense_ratio > Decimal("1.00"):
        anomalies.append(
            _anomaly(
                "high_expense_ratio",
                "HIGH",
                None,
                "Expenses exceed recorded income in the selected period.",
                "expense_to_income_ratio",
                Decimal("1.00"),
                metric_value=expense_ratio,
            )
        )

    cash_flow_stability = _decimal(metrics.get("cash_flow_stability"))
    if cash_flow_stability < Decimal("50.00") and _periods(analysis):
        anomalies.append(
            _anomaly(
                "cash_flow_instability",
                "HIGH",
                None,
                "Fewer than half of the observed periods had non-negative cash flow.",
                "cash_flow_stability",
                Decimal("50.00"),
                metric_value=cash_flow_stability,
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

    # Daily losses are normal for many businesses.  Flag only loss-making
    # months so the review list remains actionable.
    for period in monthly:
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
    return anomalies


def _phase2_severity(value: Any) -> str:
    normalized = str(value or "MEDIUM").upper()
    if normalized in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
        return normalized
    return "MEDIUM"


def _finalize_anomalies(
    anomalies: list[dict[str, Any]],
    *,
    business_id: str,
    account_id: str,
) -> list[dict[str, Any]]:
    finalized: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for anomaly in anomalies:
        base = dict(anomaly)
        anomaly_type = base.get("type")
        base["business_id"] = business_id
        base["account_id"] = account_id
        base["date_detected"] = base.get("date")
        base["metric_value"] = base.get("metric_value", base.get("threshold"))
        base["explanation"] = base.get("explanation") or base.get("reason")
        base["affected_period"] = base.get("affected_period", base.get("date"))
        base.setdefault("transaction_reference", None)
        base["severity"] = _phase2_severity(base.get("severity"))
        identity = (
            anomaly_type,
            base.get("date"),
            base.get("transaction_reference"),
            str(base.get("metric_value")),
        )
        if identity in seen:
            continue
        seen.add(identity)
        finalized.append(base)
    return finalized[:25]


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
    metrics["health_score"] = score
    metrics["health_rating"] = {
        "Excellent": "Excellent",
        "Good": "Good",
        "Moderate": "Stable",
        "Poor": "Warning",
        "Critical": "Critical",
    }[health_level]
    metrics["income_growth"] = metrics["income_trend"]
    metrics["expense_growth"] = metrics["expense_trend"]
    metrics["income_ratio"] = (
        (total_income / total_expense).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if total_expense
        else Decimal("0.00")
    )

    anomalies = _detect_transaction_anomalies(transactions)
    anomalies.extend(_detect_period_anomalies(analysis, metrics))
    finalized = _finalize_anomalies(
        anomalies,
        business_id=business_id,
        account_id=account_id,
    )
    return {"metrics": metrics, "anomalies": _sort_anomalies(finalized)}


analyze_business_health = get_business_health


__all__ = [
    "BusinessHealthError",
    "analyze_business_health",
    "get_business_health",
]
