"""Database-backed dashboard, scheme finder, and PDF report surface."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from finsight_app.eligibility_engine import check_eligibility
from finsight_app.pdf_generator import generate_report
from finsight_app.scheme_rag import SchemeAssistantError, answer_scheme_question, has_scheme_guide
from services import report_service


def _minor(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _money(value: Any, currency: str) -> str:
    return f"{currency} {_minor(value) / Decimal(100):,.2f}"


def _scheme_profile(st: Any) -> dict[str, Any]:
    st.caption(
        "This is a guide, not an approval decision. Profile details are used only "
        "for scheme screening and are not written to your financial database."
    )
    left, right = st.columns([1, 1])
    with left:
        sector = st.selectbox(
            "Business sector",
            ["Service", "Manufacturing", "Trading", "Healthcare", "Retail", "Other"],
            key="scheme_business_sector",
        )
        category = st.selectbox(
            "Business category", ["Micro", "Small", "Medium", "Startup"],
            key="scheme_business_category",
        )
        owner_age = st.number_input(
            "Owner age", min_value=18, max_value=100, value=30, step=1,
            key="scheme_owner_age",
        )
    with right:
        state = st.selectbox(
            "Business state",
            ["Maharashtra", "Andhra Pradesh", "Delhi", "Gujarat", "Karnataka", "Kerala", "Tamil Nadu", "Telangana", "Uttar Pradesh", "Other"],
            key="scheme_business_state",
        )
        funding_amount = st.number_input(
            "Funding amount you plan to seek (₹)", min_value=0, value=0, step=50000,
            help="Leave this at 0 if you only want to explore schemes without a funding amount.",
            key="scheme_funding_amount",
        )
    with st.expander("Additional eligibility details", expanded=False):
        detail_one, detail_two = st.columns(2)
        has_udyam = detail_one.selectbox("Udyam registration", ["Not sure", "Yes", "No"], key="scheme_udyam")
        is_new_unit = detail_two.selectbox("Is this a new business or project?", ["Not sure", "Yes", "No"], key="scheme_new_unit")
        woman_or_scst = detail_one.selectbox("Woman or SC/ST founder", ["Not sure", "Yes", "No"], key="scheme_founder_group")
        has_dpiit = detail_two.selectbox("DPIIT-recognised startup", ["Not sure", "Yes", "No"], key="scheme_dpiit")
    return {
        "sector": sector,
        "state": state,
        "business_category": category,
        "owner_age": owner_age,
        "funding_amount": funding_amount or None,
        "has_udyam": has_udyam,
        "is_new_unit": is_new_unit,
        "woman_or_scst": woman_or_scst,
        "has_dpiit": has_dpiit,
    }


def _render_summary(st: Any, analytics: dict[str, Any], currency: str) -> None:
    kpis = analytics.get("kpis") if isinstance(analytics.get("kpis"), dict) else {}
    st.subheader("Financial summary")
    metrics = st.columns(4)
    metrics[0].metric("Revenue", _money(kpis.get("total_income_minor"), currency))
    metrics[1].metric("Expenses", _money(kpis.get("total_expense_minor"), currency))
    metrics[2].metric("Net cash flow", _money(kpis.get("net_cash_flow_minor"), currency))
    metrics[3].metric("Transactions", str(kpis.get("transaction_count", 0)))
    if not kpis.get("transaction_count"):
        st.info("No accepted transactions exist for the selected period. Import CSV, JSON, or XML transactions to populate this summary.")
    st.caption("Source: authenticated SQLite data through the FinSight analytics service.")


def _safe_report_error(error: Any) -> str:
    message = str(error).lower()
    if "permission" in message or "access" in message or "business" in message:
        return "You do not have permission to generate this report."
    if "date" in message:
        return "Choose a valid report date range."
    if "currency" in message or "account" in message:
        return "The selected account or currency is unavailable."
    return "The report could not be generated."


def _render_scheme_card(st: Any, item: dict[str, Any]) -> None:
    with st.container(border=True):
        st.markdown(f"#### {item['scheme_name']}")
        st.write(item["benefit_summary"])
        if item.get("application_notes"):
            st.caption(f"Next step: {item['application_notes']}")
        if item.get("source_url"):
            st.markdown(f"[Open official scheme information]({item['source_url']})")
        st.caption(f"Catalogue reviewed: {item.get('last_verified_date', '—')}. Final eligibility is decided by the relevant authority or lender.")


def _render_check_list(st: Any, item: dict[str, Any], wanted_status: bool | None) -> None:
    for check in item.get("checks", []):
        if check.get("status") is wanted_status:
            st.write(f"• {check['label']}: {check['detail']}")


def _render_schemes_and_report(st: Any, session_token: str, scope: dict[str, Any]) -> None:
    st.subheader("Government scheme finder")
    profile = _scheme_profile(st)
    results = check_eligibility(profile)
    matched = [item for item in results if item["match_status"] == "matched"]
    needs_details = [item for item in results if item["match_status"] == "needs_details"]
    not_matched = [item for item in results if item["match_status"] == "not_matched"]

    match_tab, details_tab, explore_tab = st.tabs(
        [f"Likely matches ({len(matched)})", f"Needs details ({len(needs_details)})", "Explore catalogue"]
    )
    with match_tab:
        if not matched:
            st.info("No scheme is fully matched yet. Complete the additional details or adjust the funding amount to refine the results.")
        for item in matched:
            _render_scheme_card(st, item)
    with details_tab:
        if not needs_details:
            st.info("No additional profile details are needed for the current screening.")
        for item in needs_details:
            _render_scheme_card(st, item)
            _render_check_list(st, item, None)
    with explore_tab:
        for item in not_matched:
            with st.expander(item["scheme_name"]):
                st.write(item["benefit_summary"])
                _render_check_list(st, item, False)
                if item.get("source_url"):
                    st.markdown(f"[Open official scheme information]({item['source_url']})")

    guide_items = [item for item in matched + needs_details if has_scheme_guide(item["scheme_name"])]
    if guide_items:
        st.subheader("Ask FinSight Assistant")
        st.caption("Answers use FinSight's local scheme guide, not your transaction data. Confirm final requirements on the official scheme page.")
        selected_scheme = st.selectbox("Scheme guide", [item["scheme_name"] for item in guide_items], key="assistant_scheme")
        question = st.text_input("What would you like to know?", placeholder="Example: Which documents should I prepare?", key="assistant_question")
        if st.button("Ask assistant", type="primary", disabled=not question.strip(), key="ask_scheme_assistant"):
            try:
                response = answer_scheme_question(selected_scheme, question)
                with st.container(border=True):
                    st.write(response.answer)
                    st.caption("Guide response — not an approval or legal advice.")
            except SchemeAssistantError as error:
                st.warning(str(error))
            except Exception:
                st.warning("The assistant is temporarily unavailable. The scheme details above are still available.")

    st.subheader("Download report")
    if st.button("Generate PDF report", key="generate_financial_report"):
        try:
            report = report_service.build_report(
                session_token=session_token,
                business_id=scope["business_id"],
                account_id=scope["account_id"],
                start_date=scope["start_date"],
                end_date=scope["end_date"],
                currency=scope["currency"],
                generated_at=datetime.now(timezone.utc),
            )
            pdf_buffer = generate_report(report, results)
            st.download_button("Download PDF report", data=pdf_buffer.getvalue(), file_name="finsight_report.pdf", mime="application/pdf", key="download_financial_report")
        except report_service.ReportError as error:
            st.error(_safe_report_error(error))
        except Exception:
            st.error("The report could not be generated.")


def render_database_dashboard(st: Any, session_token: Any, scope: Any) -> bool:
    """Render the dashboard from the already-authorized backend scope."""
    if type(session_token) is not str or not session_token:
        st.warning("Sign in to view the financial dashboard.")
        return False
    if not isinstance(scope, dict) or not isinstance(scope.get("analytics"), dict):
        return False
    required = ("business_id", "account_id", "start_date", "end_date", "currency")
    if any(type(scope.get(key)) is not str or not scope[key] for key in required):
        st.error("The selected financial scope is unavailable.")
        return False
    business, account = scope.get("business"), scope.get("account")
    business_name = business.get("business_name") if isinstance(business, dict) else "Selected business"
    account_name = account.get("account_name") if isinstance(account, dict) else "Selected account"
    st.title("FinSight financial dashboard")
    st.caption(f"{business_name} · {account_name} · {scope['start_date']} to {scope['end_date']}")
    _render_summary(st, scope["analytics"], scope["currency"])
    with st.expander("Government scheme finder"):
        _render_schemes_and_report(st, session_token, scope)
    return True


def render_reports_page(st: Any, session_token: Any, scope: Any) -> bool:
    st.title("Reports and schemes")
    if not isinstance(scope, dict) or not isinstance(scope.get("analytics"), dict):
        st.info("Open Dashboard and choose a business, account, and date range first.")
        return False
    business, account = scope.get("business", {}), scope.get("account", {})
    st.caption(f"{business.get('business_name', 'Selected business')} · {account.get('account_name', 'Selected account')} · {scope['start_date']} to {scope['end_date']}")
    _render_schemes_and_report(st, session_token, scope)
    return True


__all__ = ["render_database_dashboard", "render_reports_page"]
