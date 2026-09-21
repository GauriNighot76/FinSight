"""Professional PDF report configuration and download UI."""

import csv
import io
from datetime import date
from typing import Any

from finsight_app.pdf_generator import (
    DEFAULT_SECTIONS,
    generate_business_report,
    safe_report_filename,
)
from services import (
    account_service,
    analytics_service,
    business_service,
    decision_support_service,
    report_service,
)

SECTION_OPTIONS = [
    ("executive_summary", "Executive Summary"),
    ("business_profile", "Business Profile"),
    ("financial_performance", "Financial Performance"),
    ("cash_flow", "Cash Flow"),
    ("income_analysis", "Income Analysis"),
    ("expense_analysis", "Expense Analysis"),
    ("payment_mode", "Payment Mode Analysis"),
    ("business_health", "Business Health"),
    ("anomalies", "Anomalies / Risk Observations"),
    ("recommendations", "Recommendations"),
    ("government_schemes", "Government Schemes"),
    ("methodology", "Methodology / Data Quality"),
    ("disclaimer", "Disclaimer"),
]


def _account(st: Any, token: str, business_id: str):
    ready = business_service.ensure_business_ready(token, business_id)
    if not ready.get("success"):
        st.error(ready.get("message", "The business could not be prepared for reporting."))
        return None
    accounts_result = account_service.list_business_accounts(token, business_id)
    accounts = accounts_result.get("accounts", []) if accounts_result.get("success") else []
    return next(
        (item for item in accounts if item.get("account_id") == ready.get("account_id")),
        None,
    )


def render_reports(st: Any, token: str, business: dict[str, Any]) -> bool:
    business_id = business["business_id"]
    account = _account(st, token, business_id)
    if account is None:
        st.error("The internal business account is unavailable.")
        return False

    try:
        bounds = analytics_service.get_transaction_date_bounds(
            session_token=token,
            business_id=business_id,
            account_id=account["account_id"],
            currency=account["currency"],
        )
    except Exception:
        bounds = {"start_date": None, "end_date": None}

    default_start = date.fromisoformat(bounds["start_date"]) if bounds.get("start_date") else date.today()
    default_end = date.fromisoformat(bounds["end_date"]) if bounds.get("end_date") else date.today()

    st.subheader("Reports")
    st.caption(
        "Generate a FinSight PDF from the same accepted transaction data used by "
        "Overview, Analytics and Business Health."
    )
    report_title = st.text_input(
        "Report Title",
        value="Financial Performance & Business Intelligence Report",
        key=f"report_title_{business_id}",
    )
    start_date, end_date = st.date_input(
        "Reporting Period",
        value=(default_start, default_end),
        key=f"report_period_{business_id}",
    )

    st.markdown("#### Include Sections")
    included = set()
    columns = st.columns(2)
    for index, (key, label) in enumerate(SECTION_OPTIONS):
        checked = columns[index % 2].checkbox(
            label,
            value=key in DEFAULT_SECTIONS,
            key=f"report_section_{business_id}_{key}",
        )
        if checked:
            included.add(key)

    st.markdown("#### Display Labels")
    st.caption("These names affect PDF presentation only; calculations and stored fields do not change.")
    l1, l2, l3 = st.columns(3)
    income_label = l1.text_input(
        "Total Income label",
        value="Total Income",
        key=f"report_income_label_{business_id}",
    )
    expense_label = l2.text_input(
        "Total Expenses label",
        value="Total Expenses",
        key=f"report_expense_label_{business_id}",
    )
    net_label = l3.text_input(
        "Net Cash Flow label",
        value="Net Cash Flow",
        key=f"report_net_label_{business_id}",
    )

    if st.button("Generate PDF Report", type="primary"):
        if start_date > end_date:
            st.error("Choose a valid reporting period.")
            return False
        args = {
            "session_token": token,
            "business_id": business_id,
            "account_id": account["account_id"],
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "currency": account["currency"],
        }
        try:
            report = report_service.build_report(**args)
            decision_support = decision_support_service.get_decision_support(**args)
            schemes = (
                st.session_state.get(f"scheme_results_{business_id}", [])
                if "government_schemes" in included
                else []
            )
            pdf = generate_business_report(
                business=business,
                report=report,
                decision_support=decision_support,
                scheme_results=schemes,
                report_title=report_title.strip() or "Financial Performance & Business Intelligence Report",
                included_sections=included,
                labels={
                    "total_income": income_label.strip() or "Total Income",
                    "total_expenses": expense_label.strip() or "Total Expenses",
                    "net_cash_flow": net_label.strip() or "Net Cash Flow",
                },
            )
        except Exception:
            st.error(
                "The PDF report could not be generated. Verify the reporting "
                "period and transaction data, then try again."
            )
            return False
        raw_pdf = pdf.getvalue()
        if not raw_pdf.startswith(b"%PDF") or len(raw_pdf) < 1000:
            st.error("The generated PDF failed validation.")
            return False
        filename = safe_report_filename(business["business_name"], date.today().isoformat())
        st.session_state[f"report_pdf_{business_id}"] = raw_pdf
        st.session_state[f"report_pdf_name_{business_id}"] = filename
        st.success("PDF report generated successfully.")

    raw_pdf = st.session_state.get(f"report_pdf_{business_id}")
    if isinstance(raw_pdf, bytes):
        st.download_button(
            "Download PDF",
            data=raw_pdf,
            file_name=st.session_state.get(
                f"report_pdf_name_{business_id}",
                safe_report_filename(business["business_name"], date.today().isoformat()),
            ),
            mime="application/pdf",
            type="primary",
        )

    with st.expander("Optional raw report export"):
        if st.button("Prepare CSV Export", key=f"prepare_csv_{business_id}"):
            args = {
                "session_token": token,
                "business_id": business_id,
                "account_id": account["account_id"],
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "currency": account["currency"],
            }
            try:
                report = report_service.build_report(**args)
                rows = report_service.report_to_csv_rows(report)
            except Exception:
                st.error("Raw report export could not be prepared.")
                return False
            output = io.StringIO()
            if rows:
                fields = sorted({key for row in rows for key in row})
                writer = csv.DictWriter(output, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            st.session_state[f"report_csv_{business_id}"] = output.getvalue()
        raw_csv = st.session_state.get(f"report_csv_{business_id}")
        if isinstance(raw_csv, str):
            st.download_button(
                "Download Raw CSV",
                raw_csv,
                file_name="finsight_report_data.csv",
                mime="text/csv",
            )
    return True
