"""PDF presentation for database-backed FinSight reports.

The reporting service remains responsible for loading and calculating data.
This module only formats an already-authorized report dictionary for PDF
download.  A small legacy-compatible path is retained for older callers, but
the Streamlit application uses :func:`generate_database_report`.
"""

from datetime import date
import io
from decimal import Decimal, InvalidOperation
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from services import report_service


def _text(value: Any) -> str:
    return escape("" if value is None else str(value))


def _minor_money(value: Any, currency: str) -> str:
    if value is None:
        return "—"
    try:
        amount = Decimal(str(value)) / Decimal(100)
    except (InvalidOperation, TypeError, ValueError):
        return "—"
    return f"{_text(currency)} {amount:,.2f}"


def _table(data: list[list[Any]], widths: list[float]) -> Table:
    wrapped = [
        [item if isinstance(item, Paragraph) else Paragraph(_text(item), _TABLE_STYLE) for item in row]
        for row in data
    ]
    table = Table(wrapped, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a2b4c")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("LEADING", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


_STYLES = getSampleStyleSheet()
_TABLE_STYLE = ParagraphStyle(
    "FinSightTable", parent=_STYLES["Normal"], fontSize=8, leading=10
)
_SMALL_STYLE = ParagraphStyle(
    "FinSightSmall", parent=_STYLES["Normal"], fontSize=8, leading=10, textColor=colors.grey
)

_FINDING_LABELS = {
    "amount_outside_usual_range": "Amount outside the usual range",
    "monthly_expenses_doubled": "Monthly expenses doubled",
    "monthly_expense_increase": "Monthly expenses increased",
    "sudden_income_drop": "Monthly income decreased",
    "negative_cash_flow_period": "Loss-making month",
    "category_spike": "Category spending increased",
    "inactive_period": "Long period without transactions",
}


def _finding_label(value: Any) -> str:
    key = str(value or "review_item")
    return _FINDING_LABELS.get(key, key.replace("_", " ").title())


def _backend_pdf(report: dict[str, Any], eligibility_results: list[dict[str, Any]] | None) -> io.BytesIO:
    safe_report = report_service.report_to_json(report)
    business_name = safe_report.get("business", {}).get("name", "FinSight business")
    currency = safe_report.get("currency", "INR")
    date_range = safe_report.get("date_range", {})
    sections = safe_report.get("sections", {})
    kpis = sections.get("financial_summary", {})
    health = sections.get("business_health_report", {})
    anomalies = sections.get("anomaly_report", [])
    categories = sections.get("category_report", [])
    payment_modes = sections.get("payment_mode_report", [])

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="FinSight Financial Report",
        author="FinSight",
    )
    title_style = ParagraphStyle(
        "FinSightTitle", parent=_STYLES["Title"], fontSize=18, leading=22
    )
    story: list[Any] = [
        Paragraph("FinSight Financial Report", title_style),
        Paragraph(_text(business_name), _STYLES["Heading2"]),
        Paragraph(
            f"Period: {_text(date_range.get('start_date'))} to {_text(date_range.get('end_date'))} · "
            f"Currency: {_text(currency)}",
            _STYLES["Normal"],
        ),
        Spacer(1, 10),
        Paragraph("Financial Summary", _STYLES["Heading2"]),
    ]

    kpi_rows = [
        ["Metric", "Value"],
        ["Total income", _minor_money(kpis.get("total_income_minor"), currency)],
        ["Total expense", _minor_money(kpis.get("total_expense_minor"), currency)],
        ["Net cash flow", _minor_money(kpis.get("net_cash_flow_minor"), currency)],
        ["Transaction count", kpis.get("transaction_count", 0)],
        ["Average transaction", _minor_money(kpis.get("average_transaction_minor"), currency)],
        ["Opening balance", _minor_money(kpis.get("opening_balance_minor"), currency)],
        ["Closing balance", _minor_money(kpis.get("closing_balance_minor"), currency)],
        ["Savings rate", f"{_text(kpis.get('savings_rate'))}%" if kpis.get("savings_rate") is not None else "—"],
    ]
    story.append(_table(kpi_rows, [250, 220]))

    if health:
        story.extend([Spacer(1, 12), Paragraph("Business Health", _STYLES["Heading2"])])
        health_rows = [["Metric", "Value"]]
        for key in (
            "overall_financial_health_score",
            "health_level",
            "health_rating",
            "cash_flow_stability",
            "expense_to_income_ratio",
            "savings_rate",
            "monthly_growth",
            "monthly_decline",
        ):
            if key in health:
                value = health[key]
                if key.endswith("rate") or key.endswith("stability") or key.endswith("growth") or key.endswith("decline"):
                    value = f"{value}%"
                health_rows.append([key.replace("_", " ").title(), value])
        story.append(_table(health_rows, [250, 220]))

    if categories:
        story.extend([Spacer(1, 12), Paragraph("Category Summary", _STYLES["Heading2"])])
        category_rows = [["Category", "Income", "Expense", "Count"]]
        for row in categories:
            category_rows.append(
                [
                    row.get("category", "Uncategorized"),
                    _minor_money(row.get("income_minor"), currency),
                    _minor_money(row.get("expense_minor"), currency),
                    row.get("count", 0),
                ]
            )
        story.append(_table(category_rows, [170, 105, 105, 90]))

    if payment_modes:
        story.extend([Spacer(1, 12), Paragraph("Payment Mode Summary", _STYLES["Heading2"])])
        payment_rows = [["Payment mode", "Income", "Expense", "Count"]]
        for row in payment_modes:
            payment_rows.append(
                [
                    row.get("payment_mode", "Other"),
                    _minor_money(row.get("income_minor"), currency),
                    _minor_money(row.get("expense_minor"), currency),
                    row.get("count", 0),
                ]
            )
        story.append(_table(payment_rows, [170, 105, 105, 90]))

    story.extend([Spacer(1, 12), Paragraph("Transactions to Review", _STYLES["Heading2"])])
    if anomalies:
        story.append(Paragraph(
            "These items differ from the usual pattern and may still be valid. They are not proof of fraud or error.",
            _SMALL_STYLE,
        ))
        story.append(Spacer(1, 5))
        anomaly_rows = [["Finding", "Priority", "Date", "Why it was flagged"]]
        for row in anomalies[:20]:
            anomaly_rows.append(
                [
                    _finding_label(row.get("type")),
                    row.get("severity", "—"),
                    row.get("date", row.get("date_detected", "—")),
                    row.get("reason", row.get("explanation", "—")),
                ]
            )
        story.append(_table(anomaly_rows, [105, 70, 90, 215]))
        if len(anomalies) > 20:
            story.append(Paragraph(
                f"Showing the 20 highest-priority items out of {len(anomalies)}.",
                _SMALL_STYLE,
            ))
    else:
        story.append(Paragraph("No material review items were found for this period.", _STYLES["Normal"]))

    if eligibility_results is not None:
        story.extend([Spacer(1, 12), Paragraph("Government Scheme Matching", _STYLES["Heading2"])])
        eligible = [item for item in eligibility_results if item.get("eligible")]
        if not eligible:
            story.append(Paragraph("No schemes matched the selected profile.", _STYLES["Normal"]))
        else:
            for item in eligible:
                story.append(Paragraph(f"<b>{_text(item.get('scheme_name'))}</b>", _STYLES["Heading3"]))
                story.append(Paragraph(_text(item.get("benefit_summary")), _STYLES["Normal"]))
                story.append(Spacer(1, 5))

    story.extend(
        [
            Spacer(1, 14),
            Paragraph(
                "This report was generated from authenticated FinSight analytics "
                "and accepted financial records stored by the application. "
                "Government scheme eligibility is rule-based and should be "
                "confirmed on the official scheme portal before applying.",
                _SMALL_STYLE,
            ),
        ]
    )
    document.build(story)
    buffer.seek(0)
    return buffer


def generate_database_report(
    report: dict[str, Any], eligibility_results: list[dict[str, Any]] | None = None
) -> io.BytesIO:
    """Render a report returned by ``services.report_service.build_report``."""
    if not isinstance(report, dict) or not isinstance(report.get("sections"), dict):
        raise ValueError("A valid backend report is required.")
    return _backend_pdf(report, eligibility_results)


def _legacy_pdf(business_name: str, kpis: dict[str, Any], eligibility_results: list[dict[str, Any]]) -> io.BytesIO:
    """Compatibility output for older callers; the app no longer uses it."""
    report = {
        "business": {"name": business_name},
        "date_range": {"start_date": "legacy", "end_date": "legacy"},
        "currency": "INR",
        "sections": {
            "financial_summary": {
                "total_income_minor": int(Decimal(str(kpis.get("revenue_total", 0))) * 100),
                "total_expense_minor": int(Decimal(str(kpis.get("total_expenses", 0))) * 100),
                "net_cash_flow_minor": int(Decimal(str(kpis.get("net_profit", 0))) * 100),
                "transaction_count": 0,
                "average_transaction_minor": None,
                "opening_balance_minor": None,
                "closing_balance_minor": None,
                "savings_rate": kpis.get("net_profit_margin"),
            },
            "business_health_report": {},
            "category_report": [],
            "payment_mode_report": [],
            "anomaly_report": [],
        },
    }
    return _backend_pdf(report, eligibility_results)


def generate_report(
    report_or_business_name: dict[str, Any] | str,
    kpis: Any = None,
    eligibility_results: list[dict[str, Any]] | None = None,
) -> io.BytesIO:
    """Generate a PDF from a backend report or legacy KPI arguments."""
    if isinstance(report_or_business_name, dict):
        selected_eligibility = kpis if isinstance(kpis, list) and eligibility_results is None else eligibility_results
        return generate_database_report(report_or_business_name, selected_eligibility)
    if not isinstance(kpis, dict) or eligibility_results is None:
        raise ValueError("Legacy PDF generation requires business, KPI, and scheme data.")
    return _legacy_pdf(report_or_business_name, kpis, eligibility_results)


__all__ = ["generate_database_report", "generate_report"]
