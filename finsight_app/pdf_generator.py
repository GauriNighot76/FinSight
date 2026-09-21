from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from datetime import date
import io


def _money_minor(value, currency):
    return f"{currency} {(value or 0) / 100:,.2f}"


def generate_authenticated_report(report):
    """Render a selected-business backend report as a downloadable PDF."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
    styles = getSampleStyleSheet()
    sections = report.get("sections", {})
    summary = sections.get("financial_summary", {})
    currency = report.get("currency", "INR")
    business_name = report.get("business", {}).get("name", "Selected business")
    date_range = report.get("date_range", {})
    rows = [
        ["Metric", "Value"],
        ["Total income", _money_minor(summary.get("total_income_minor"), currency)],
        ["Total expense", _money_minor(summary.get("total_expense_minor"), currency)],
        ["Net cash flow", _money_minor(summary.get("net_cash_flow_minor"), currency)],
        ["Transactions", str(summary.get("transaction_count", 0))],
        ["Savings rate", str(summary.get("savings_rate") or "Not available")],
    ]
    table = Table(rows, colWidths=[250, 150])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a2b4c")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
            ]
        )
    )
    story = [
        Paragraph("FinSight Financial Report", styles["Title"]),
        Paragraph(business_name, styles["Heading2"]),
        Paragraph(
            f"Period: {date_range.get('start_date', '')} to {date_range.get('end_date', '')}",
            styles["Normal"],
        ),
        Spacer(1, 12),
        table,
        Spacer(1, 16),
        Paragraph(
            "This report is derived from the selected authenticated business, account, "
            "date range, and accepted transactions.",
            styles["Normal"],
        ),
    ]
    doc.build(story)
    buffer.seek(0)
    return buffer


def generate_report(business_name, kpis, eligibility_results):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleStyle", parent=styles["Title"], fontSize=18)
    story = []

    story.append(Paragraph("FinSight Financial Report Card", title_style))
    story.append(Paragraph(f"{business_name}", styles["Heading2"]))
    story.append(Paragraph(f"Generated on {date.today().strftime('%d %B %Y')}", styles["Normal"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Financial Summary", styles["Heading2"]))
    kpi_table_data = [
        ["Metric", "Amount (Rs)"],
        ["Total Revenue", f"{kpis['revenue_total']:,.0f}"],
        ["Total Expenses", f"{kpis['total_expenses']:,.0f}"],
        ["Net Profit", f"{kpis['net_profit']:,.0f}"],
        ["Net Profit Margin", f"{kpis['net_profit_margin']:.1f}%"],
        ["Estimated Annual Turnover", f"{kpis['annual_turnover']:,.0f}"],
    ]
    kpi_table = Table(kpi_table_data, colWidths=[250, 150])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a2b4c")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 20))

    story.append(Paragraph("Government Schemes You May Qualify For", styles["Heading2"]))
    eligible = [r for r in eligibility_results if r["eligible"]]

    if not eligible:
        story.append(Paragraph("No schemes matched based on current data.", styles["Normal"]))
    else:
        for r in eligible:
            story.append(Paragraph(f"<b>{r['scheme_name']}</b>", styles["Heading3"]))
            story.append(Paragraph(r["benefit_summary"], styles["Normal"]))
            story.append(Paragraph(
                f"<font size=8 color='grey'>Source: {r['source_url']} | Verified: {r['last_verified_date']}</font>",
                styles["Normal"]
            ))
            story.append(Spacer(1, 10))

    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "<font size=8 color='grey'>This report is generated from a synthetic demo dataset for academic purposes. "
        "Scheme eligibility is based on rule-based matching against publicly available scheme criteria. "
        "Please verify current scheme details on official government portals before applying.</font>",
        styles["Normal"]
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer
