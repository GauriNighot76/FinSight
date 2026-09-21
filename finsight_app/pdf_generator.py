"""Professional FinSight PDF rendering for sanitized backend report data."""

from __future__ import annotations

import io
import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Iterable

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

NAVY = colors.HexColor("#173B57")
BABY_BLUE = colors.HexColor("#DFF3FF")
ACCENT = colors.HexColor("#4EA5D9")
BORDER = colors.HexColor("#D7E9F4")
MUTED = colors.HexColor("#66788A")
POSITIVE = colors.HexColor("#2F9E72")
WARNING = colors.HexColor("#E5A93D")
CRITICAL = colors.HexColor("#D95C5C")
WHITE = colors.white

DEFAULT_SECTIONS = {
    "executive_summary",
    "business_profile",
    "financial_performance",
    "cash_flow",
    "income_analysis",
    "expense_analysis",
    "payment_mode",
    "business_health",
    "anomalies",
    "recommendations",
    "government_schemes",
    "methodology",
    "disclaimer",
}

DEFAULT_LABELS = {
    "total_income": "Total Income",
    "total_expenses": "Total Expenses",
    "net_cash_flow": "Net Cash Flow",
}


def _money(minor: Any, currency: str) -> str:
    if minor is None:
        return "N/A"
    try:
        major = Decimal(str(minor)) / Decimal(100)
    except Exception:
        return "N/A"
    return f"{currency} {major:,.2f}"


def _text(value: Any, default: str = "N/A") -> str:
    if value is None or value == "":
        return default
    return str(value)


def _styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            "FS_CoverTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=25,
            leading=30,
            textColor=NAVY,
            alignment=TA_CENTER,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            "FS_CoverSubtitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=12,
            leading=17,
            textColor=MUTED,
            alignment=TA_CENTER,
        )
    )
    styles.add(
        ParagraphStyle(
            "FS_H1",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=17,
            leading=21,
            textColor=NAVY,
            spaceBefore=8,
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            "FS_H2",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=NAVY,
            spaceBefore=7,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            "FS_Body",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=14,
            textColor=colors.HexColor("#263B4D"),
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            "FS_Small",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=MUTED,
        )
    )
    styles.add(
        ParagraphStyle(
            "FS_Metric",
            parent=styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=NAVY,
        )
    )
    return styles


def _header_footer(canvas, doc):
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, 14 * mm, width - 18 * mm, 14 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 9 * mm, "FinSight — Financial Analytics for MSMEs")
    canvas.drawRightString(width - 18 * mm, 9 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _section_title(number: int, title: str, styles) -> Paragraph:
    return Paragraph(f"{number}. {title}", styles["FS_H1"])


def _metric_table(rows: Iterable[tuple[str, str]], styles) -> Table:
    data = []
    for label, value in rows:
        data.append(
            [
                Paragraph(label, styles["FS_Small"]),
                Paragraph(value, styles["FS_Metric"]),
            ]
        )
    table = Table(data, colWidths=[70 * mm, 85 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), WHITE),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def _data_table(headers: list[str], rows: list[list[Any]], widths=None) -> Table:
    data = [headers] + [[_text(value, "") for value in row] for row in rows]
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, BABY_BLUE]),
                ("GRID", (0, 0), (-1, -1), 0.35, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _bar_chart(
    title: str,
    categories: list[str],
    series: list[list[float]],
    legends: list[str],
) -> Drawing | None:
    if not categories or not series or not any(any(v != 0 for v in s) for s in series):
        return None
    categories = categories[-8:]
    series = [values[-8:] for values in series]
    drawing = Drawing(470, 220)
    drawing.add(String(10, 202, title, fontName="Helvetica-Bold", fontSize=10, fillColor=NAVY))
    chart = VerticalBarChart()
    chart.x = 45
    chart.y = 40
    chart.height = 140
    chart.width = 395
    chart.data = series
    chart.categoryAxis.categoryNames = categories
    chart.categoryAxis.labels.fontName = "Helvetica"
    chart.categoryAxis.labels.fontSize = 6.5
    chart.categoryAxis.labels.angle = 20
    chart.valueAxis.labels.fontSize = 7
    chart.valueAxis.valueMin = 0
    chart.barWidth = 8
    chart.groupSpacing = 5
    palette = [ACCENT, WARNING, POSITIVE]
    for index in range(min(len(series), len(palette))):
        chart.bars[index].fillColor = palette[index]
    drawing.add(chart)
    x = 48
    for index, legend in enumerate(legends):
        drawing.add(
            String(
                x,
                18,
                legend,
                fontName="Helvetica",
                fontSize=7,
                fillColor=palette[index % len(palette)],
            )
        )
        x += 95
    return drawing


def _executive_summary(
    summary: dict[str, Any],
    anomalies: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
    currency: str,
) -> list[str]:
    count = int(summary.get("transaction_count", 0) or 0)
    if count == 0:
        return [
            "No accepted transactions were available for the selected reporting period. "
            "Financial conclusions are therefore limited until transaction data is imported."
        ]
    income = summary.get("total_income_minor", 0) or 0
    expense = summary.get("total_expense_minor", 0) or 0
    net = summary.get("net_cash_flow_minor", 0) or 0
    direction = "positive" if Decimal(str(net)) >= 0 else "negative"
    lines = [
        f"FinSight analyzed {count} accepted transactions. Recorded income was "
        f"{_money(income, currency)}, recorded expenses were {_money(expense, currency)}, "
        f"and net cash flow was {_money(net, currency)} ({direction})."
    ]
    if anomalies:
        lines.append(
            f"The deterministic health engine identified {len(anomalies)} anomaly "
            "observation(s) that warrant review; these observations are not findings of fraud."
        )
    if recommendations:
        lines.append(
            f"The decision-support engine generated {len(recommendations)} data-backed "
            "recommendation(s) for management consideration."
        )
    return lines


def safe_report_filename(business_name: str, report_date: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", business_name.strip()).strip("_")
    base = base[:80] or "Business"
    return f"FinSight_{base}_{report_date}.pdf"


def generate_business_report(
    *,
    business: dict[str, Any],
    report: dict[str, Any],
    decision_support: dict[str, Any] | None = None,
    scheme_results: list[dict[str, Any]] | None = None,
    report_title: str = "Financial Performance & Business Intelligence Report",
    included_sections: set[str] | None = None,
    labels: dict[str, str] | None = None,
) -> io.BytesIO:
    """Render a consulting-style PDF from sanitized FinSight service outputs."""
    included = set(included_sections or DEFAULT_SECTIONS)
    display_labels = {**DEFAULT_LABELS, **(labels or {})}
    sections = report.get("sections", {}) if isinstance(report, dict) else {}
    summary = sections.get("financial_summary", {}) if isinstance(sections, dict) else {}
    cash_flow = sections.get("cash_flow_summary", {}) if isinstance(sections, dict) else {}
    categories = sections.get("category_report", []) if isinstance(sections, dict) else []
    payment_modes = sections.get("payment_mode_report", []) if isinstance(sections, dict) else []
    health = sections.get("business_health_report", {}) if isinstance(sections, dict) else {}
    anomalies = sections.get("anomaly_report", []) if isinstance(sections, dict) else []
    recommendations = (
        decision_support.get("recommendations", [])
        if isinstance(decision_support, dict)
        else []
    )
    schemes = scheme_results if isinstance(scheme_results, list) else []

    currency = _text(report.get("currency"), "INR")
    date_range = report.get("date_range", {}) if isinstance(report, dict) else {}
    generated = _text(report.get("generated_at"), datetime.utcnow().isoformat())
    generated_date = generated[:10]
    business_name = _text(business.get("business_name"), _text(report.get("business", {}).get("name"), "Business"))
    business_type = _text(business.get("business_type"), "Not specified")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=20 * mm,
        title=f"FinSight — {business_name}",
        author="FinSight",
    )
    styles = _styles()
    story = []

    # Cover
    story.extend(
        [
            Spacer(1, 38 * mm),
            Paragraph("FinSight", styles["FS_CoverTitle"]),
            Paragraph(report_title, styles["FS_CoverSubtitle"]),
            Spacer(1, 14 * mm),
            Table(
                [["Business", business_name], ["Business Type", business_type],
                 ["Reporting Period", f"{_text(date_range.get('start_date'))} to {_text(date_range.get('end_date'))}"],
                 ["Generated Date", generated_date]],
                colWidths=[45 * mm, 105 * mm],
                style=TableStyle([
                    ("BACKGROUND", (0, 0), (0, -1), BABY_BLUE),
                    ("TEXTCOLOR", (0, 0), (-1, -1), NAVY),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                    ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
                    ("PADDING", (0, 0), (-1, -1), 8),
                ]),
            ),
            Spacer(1, 22 * mm),
            Paragraph("Prepared by FinSight", styles["FS_CoverSubtitle"]),
            PageBreak(),
        ]
    )

    section_no = 1

    if "executive_summary" in included:
        story.append(_section_title(section_no, "Executive Summary", styles)); section_no += 1
        for line in _executive_summary(summary, anomalies, recommendations, currency):
            story.append(Paragraph(line, styles["FS_Body"]))
        story.append(Spacer(1, 4 * mm))

    if "business_profile" in included:
        story.append(_section_title(section_no, "Business Profile", styles)); section_no += 1
        profile_rows = [
            ["Business Name", business_name],
            ["Business Type", business_type],
            ["Reporting Period", f"{_text(date_range.get('start_date'))} to {_text(date_range.get('end_date'))}"],
        ]
        if business.get("legal_identifier"):
            profile_rows.append(["Registration Identifier", business["legal_identifier"]])
        if business.get("contact_email"):
            profile_rows.append(["Contact Email", business["contact_email"]])
        if business.get("contact_phone"):
            profile_rows.append(["Contact Phone", business["contact_phone"]])
        story.append(_data_table(["Field", "Value"], profile_rows, [55 * mm, 100 * mm]))
        story.append(Spacer(1, 4 * mm))

    if "financial_performance" in included:
        story.append(_section_title(section_no, "Financial Performance", styles)); section_no += 1
        story.append(_metric_table([
            (display_labels["total_income"], _money(summary.get("total_income_minor", 0), currency)),
            (display_labels["total_expenses"], _money(summary.get("total_expense_minor", 0), currency)),
            (display_labels["net_cash_flow"], _money(summary.get("net_cash_flow_minor", 0), currency)),
            ("Transaction Count", _text(summary.get("transaction_count"), "0")),
            ("Average Transaction", _money(summary.get("average_transaction_minor"), currency)),
            ("Savings Rate", "N/A" if summary.get("savings_rate") is None else f"{summary.get('savings_rate')}%"),
            ("Income / Expense Ratio", _text(summary.get("income_expense_ratio"))),
        ], styles))
        story.append(Spacer(1, 4 * mm))

    if "cash_flow" in included:
        story.append(_section_title(section_no, "Cash Flow Analysis", styles)); section_no += 1
        trends = cash_flow.get("trends", {}) if isinstance(cash_flow, dict) else {}
        monthly = trends.get("monthly", []) if isinstance(trends, dict) else []
        chart = _bar_chart(
            "Monthly Income vs Expenses",
            [str(row.get("period")) for row in monthly],
            [
                [float(Decimal(str(row.get("income_minor", 0))) / 100) for row in monthly],
                [float(Decimal(str(row.get("expense_minor", 0))) / 100) for row in monthly],
            ],
            ["Income", "Expenses"],
        )
        if chart:
            story.append(chart)
        else:
            story.append(Paragraph("No monthly cash-flow chart is available for this period.", styles["FS_Body"]))
        story.append(Paragraph(
            f"Net cash flow for the reporting period was {_money(summary.get('net_cash_flow_minor', 0), currency)}.",
            styles["FS_Body"],
        ))

    if "income_analysis" in included:
        story.append(_section_title(section_no, "Income Analysis", styles)); section_no += 1
        income_rows = [
            [row.get("category"), _money(row.get("income_minor", 0), currency), row.get("count", 0)]
            for row in categories if row.get("income_minor", 0)
        ]
        if income_rows:
            story.append(_data_table(["Category", "Income", "Transactions"], income_rows))
        else:
            story.append(Paragraph("No categorized income was available.", styles["FS_Body"]))

    if "expense_analysis" in included:
        story.append(_section_title(section_no, "Expense Analysis", styles)); section_no += 1
        expense_rows = [
            [row.get("category"), _money(row.get("expense_minor", 0), currency), row.get("count", 0)]
            for row in categories if row.get("expense_minor", 0)
        ]
        if expense_rows:
            story.append(_data_table(["Category", "Expenses", "Transactions"], expense_rows))
            chart = _bar_chart(
                "Largest Expense Categories",
                [str(row[0]) for row in expense_rows[:8]],
                [[float(str(row[1]).replace(currency, "").replace(",", "").strip()) if row[1] != "N/A" else 0 for row in expense_rows[:8]]],
                ["Expenses"],
            )
            if chart:
                story.append(chart)
        else:
            story.append(Paragraph("No categorized expenses were available.", styles["FS_Body"]))

    if "payment_mode" in included:
        story.append(_section_title(section_no, "Payment Mode Analysis", styles)); section_no += 1
        mode_rows = [
            [row.get("payment_mode"), _money(row.get("amount_minor", 0), currency), row.get("count", 0)]
            for row in payment_modes
        ]
        if mode_rows:
            story.append(_data_table(["Payment Mode", "Recorded Amount", "Transactions"], mode_rows))
        else:
            story.append(Paragraph("No payment-mode data was available.", styles["FS_Body"]))

    if "business_health" in included:
        story.append(_section_title(section_no, "Business Health", styles)); section_no += 1
        health_rows = [
            ["Health Score", health.get("health_score")],
            ["Health Level", health.get("health_level")],
            ["Savings Rate", health.get("savings_rate")],
            ["Expense-to-Income Ratio", health.get("expense_to_income_ratio")],
            ["Cash Flow Stability", health.get("cash_flow_stability")],
            ["Category Concentration", health.get("category_concentration")],
            ["Recurring Expense Burden", health.get("recurring_expense_burden")],
        ]
        story.append(_data_table(["Indicator", "Value"], health_rows, [80 * mm, 75 * mm]))
        story.append(Paragraph(
            "Health indicators are deterministic summaries of the uploaded transaction dataset. "
            "They should be interpreted together with the underlying records and business context.",
            styles["FS_Body"],
        ))

    if "anomalies" in included:
        story.append(_section_title(section_no, "Anomaly / Risk Observations", styles)); section_no += 1
        if not anomalies:
            story.append(Paragraph("No significant deterministic anomalies were detected.", styles["FS_Body"]))
        else:
            for anomaly in anomalies:
                story.append(KeepTogether([
                    Paragraph(
                        f"<b>{_text(anomaly.get('type')).replace('_', ' ').title()}</b> "
                        f"— Severity: {_text(anomaly.get('severity'))}",
                        styles["FS_Body"],
                    ),
                    Paragraph(
                        _text(anomaly.get("explanation") or anomaly.get("reason"), "This pattern requires review.")
                        + " This is an analytical risk indicator, not a finding of fraud.",
                        styles["FS_Small"],
                    ),
                    Spacer(1, 2 * mm),
                ]))

    if "recommendations" in included:
        story.append(_section_title(section_no, "Recommendations", styles)); section_no += 1
        if not recommendations:
            story.append(Paragraph("No specific recommendations were generated for this period.", styles["FS_Body"]))
        else:
            for item in recommendations:
                story.append(KeepTogether([
                    Paragraph(
                        f"<b>{_text(item.get('title'), 'Recommendation')}</b> "
                        f"— Priority: {_text(item.get('priority'))}",
                        styles["FS_Body"],
                    ),
                    Paragraph(_text(item.get("explanation") or item.get("reason"), ""), styles["FS_Small"]),
                    Paragraph(
                        f"<b>Suggested action:</b> {_text(item.get('recommended_action'), 'Review the underlying financial records.')}",
                        styles["FS_Small"],
                    ),
                    Spacer(1, 2 * mm),
                ]))

    if "government_schemes" in included:
        story.append(_section_title(section_no, "Government Scheme Opportunities", styles)); section_no += 1
        if not schemes:
            story.append(Paragraph(
                "No scheme results were included. Scheme relevance depends on business-profile information supplied by the user.",
                styles["FS_Body"],
            ))
        else:
            scheme_rows = []
            for item in schemes:
                scheme_rows.append([
                    item.get("scheme_name"),
                    item.get("relevance", "Potentially relevant"),
                    item.get("benefit_summary", ""),
                    item.get("information_required", ""),
                ])
            story.append(_data_table(
                ["Scheme", "Relevance", "Potential Benefit", "Information Still Required"],
                scheme_rows,
                [37 * mm, 30 * mm, 48 * mm, 45 * mm],
            ))

    if "methodology" in included:
        story.append(_section_title(section_no, "Data Quality & Methodology", styles)); section_no += 1
        story.append(Paragraph(
            f"This report analyzes {summary.get('transaction_count', 0) or 0} accepted transaction(s) "
            f"for the period {_text(date_range.get('start_date'))} to {_text(date_range.get('end_date'))}. "
            "Financial values originate from transaction data uploaded for the selected authenticated business. "
            "Duplicate identities are excluded by FinSight's ingestion rules. Missing category, payment-mode or "
            "business-profile fields can limit the corresponding analysis.",
            styles["FS_Body"],
        ))

    if "disclaimer" in included:
        story.append(_section_title(section_no, "Disclaimer", styles)); section_no += 1
        story.append(Paragraph(
            "FinSight provides analytical decision support for educational and business-review purposes. "
            "It does not replace professional accounting, tax, audit, legal, lending, investment or regulatory advice. "
            "Government scheme criteria and availability should be verified against the current official source before applying.",
            styles["FS_Body"],
        ))

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    buffer.seek(0)
    return buffer


generate_report = generate_business_report

__all__ = [
    "DEFAULT_LABELS",
    "DEFAULT_SECTIONS",
    "generate_business_report",
    "generate_report",
    "safe_report_filename",
]
