"""Presentation of deterministic ratios and percentage-unit metrics."""

from decimal import Decimal


METRIC_LABELS = {
    "income_expense_ratio": "Income-to-Expense Ratio",
    "income_ratio": "Income-to-Expense Ratio",
    "expense_to_income_ratio": "Expense-to-Income Ratio",
    "savings_rate": "Savings Rate",
}


def format_metric(value, *, suffix=""):
    """Round only for display; unavailable/non-finite metrics have no ratio."""
    try:
        number = Decimal(str(value))
        if number.is_finite():
            return f"{number:.2f}{suffix}"
    except (ArithmeticError, TypeError, ValueError):
        pass
    return "N/A"


def present_report_rows(rows):
    """Label display/export rows without changing backend report contracts."""
    result = []
    for row in rows:
        displayed = dict(row)
        field = row.get("field")
        if field in METRIC_LABELS:
            displayed["field"] = METRIC_LABELS[field]
            displayed["value"] = format_metric(
                row.get("value"), suffix="%" if field == "savings_rate" else "×"
            )
        result.append(displayed)
    return result
