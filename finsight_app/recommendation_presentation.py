"""Render structured recommendation evidence without changing stored units."""
from decimal import Decimal

from finsight_app.metric_formatting import format_metric


_MONETARY_ANOMALIES = {
    "large_transaction", "unusually_large_income", "unusually_large_expense",
    "negative_cash_flow", "negative_cash_flow_period", "income_interruption",
}
_PERCENTAGE_ANOMALIES = {
    "income_drop", "sudden_income_drop",
    "expense_explosion", "sudden_expense_spike", "category_spike",
    "recurring_expense_growth", "very_high_recurring_expenses",
}


def format_minor(value, currency="INR"):
    """Minor units to display currency, including signed cash-flow values."""
    try:
        amount = Decimal(str(value)) / Decimal(100)
        if not amount.is_finite():
            return "N/A"
    except (ArithmeticError, TypeError, ValueError):
        return "N/A"
    symbol = "₹" if currency == "INR" else f"{currency} "
    sign = "−" if amount < 0 else ""
    return f"{sign}{symbol}{abs(amount):,.2f}"


def present_recommendation(item, currency="INR"):
    """Copy the card and format known typed evidence, never guess from magnitude."""
    displayed = dict(item)
    metrics = item.get("supporting_metrics") or {}
    action = item.get("recommended_action") or ""
    anomaly = metrics.get("anomaly_type")
    if "net_cash_flow_minor" in metrics:
        explanation = (f"Net cash flow of {format_minor(metrics['net_cash_flow_minor'], currency)} "
                       f"is negative; cash outflows exceed inflows. {action}")
    elif "cash_reserve_estimate_minor" in metrics:
        explanation = (
            f"Cash reserve: {format_minor(metrics['cash_reserve_estimate_minor'], currency)}. "
            f"Expense threshold: {format_minor(metrics.get('expense_threshold_minor'), currency)}. "
            f"The reserve is below one period of recorded expenses. {action}"
        )
    elif anomaly:
        value, threshold = metrics.get("metric_value"), metrics.get("threshold")
        trigger = str(metrics.get("trigger_metric") or "")
        if anomaly in _MONETARY_ANOMALIES or "_minor" in trigger:
            value, threshold = format_minor(value, currency), format_minor(threshold, currency)
        elif anomaly in _PERCENTAGE_ANOMALIES:
            value, threshold = format_metric(value, suffix="%"), format_metric(threshold, suffix="%")
        elif anomaly == "high_expense_ratio":
            value, threshold = format_metric(value), format_metric(threshold)
        else:
            value = "N/A" if value is None else str(value)
            threshold = "N/A" if threshold is None else str(threshold)
        if anomaly == "very_high_recurring_expenses":
            explanation = (f"{value} of recorded expenses fall into categories that appeared "
                           f"in at least two months. Recurring-category threshold: {threshold}. {action}")
        elif anomaly == "recurring_expense_growth":
            explanation = (f"Recurring-category spending changed by {value} compared with its "
                           f"prior active month. Growth threshold: {threshold}. {action}")
        else:
            explanation = (f"The health service detected {anomaly.replace('_', ' ')} "
                           f"with metric value {value} against threshold {threshold}. {action}")
    else:
        return displayed
    displayed["explanation"] = explanation
    return displayed
