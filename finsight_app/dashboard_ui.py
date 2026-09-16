"""Database-backed Streamlit dashboard and report download surface."""

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from finsight_app.eligibility_engine import check_eligibility
from finsight_app.pdf_generator import generate_report
from finsight_app.scheme_rag import SchemeAssistantError, answer_scheme_question
from services import report_service


def _minor(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _money(value: Any, currency: str) -> str:
    return f"{currency} {_minor(value) / Decimal(100):,.2f}"


def _annual_turnover(analytics: dict[str, Any], start_date: str, end_date: str) -> float:
    """Estimate annual turnover from the selected backend date range."""
    kpis = analytics.get("kpis") if isinstance(analytics.get("kpis"), dict) else {}
    income = _minor(kpis.get("total_income_minor")) / Decimal(100)
    try:
        days = (date.fromisoformat(end_date) - date.fromisoformat(start_date)).days + 1
    except ValueError:
        days = 1
    years = max(Decimal(days) / Decimal(365), Decimal(1))
    return float(income / years)


def _scheme_profile(
    st: Any, analytics: dict[str, Any], start_date: str, end_date: str
) -> dict[str, Any]:
    st.caption(
        "These profile fields are used only for scheme matching and are not "
        "written to the financial database."
    )
    sector = st.selectbox(
        "Business sector",
        ["Service", "Manufacturing", "Trading"],
        key="scheme_business_sector",
    )
    state = st.selectbox(
        "Business state", ["Maharashtra", "Any"], key="scheme_business_state"
    )
    category = st.selectbox(
        "Business category",
        ["Micro", "Small", "Medium"],
        key="scheme_business_category",
    )
    owner_age = st.number_input(
        "Owner age",
        min_value=18,
        max_value=100,
        value=30,
        step=1,
        key="scheme_owner_age",
    )
    return {
        "turnover": _annual_turnover(analytics, start_date, end_date),
        "sector": sector,
        "state": state,
        "business_category": category,
        "owner_age": owner_age,
    }


def _render_summary(st: Any, analytics: dict[str, Any], currency: str) -> None:
    kpis = analytics.get("kpis") if isinstance(analytics.get("kpis"), dict) else {}
    st.subheader("Financial summary")
    st.metric("Revenue", _money(kpis.get("total_income_minor"), currency))
    st.metric("Expenses", _money(kpis.get("total_expense_minor"), currency))
    st.metric("Net cash flow", _money(kpis.get("net_cash_flow_minor"), currency))
    st.metric("Transactions", str(kpis.get("transaction_count", 0)))
    if not kpis.get("transaction_count"):
        st.info("No accepted transactions exist for the selected period.")
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


def _render_schemes_and_report(
    st: Any, session_token: str, scope: dict[str, Any]
) -> None:
    analytics = scope["analytics"]
    profile = _scheme_profile(st, analytics, scope["start_date"], scope["end_date"])
    eligibility_results = check_eligibility(profile)

    st.subheader("Matched government schemes")
    eligible = [item for item in eligibility_results if item.get("eligible")]
    if not eligible:
        st.warning("No schemes matched the selected financial period and profile.")
    for item in eligible:
        with st.container(border=True):
            st.write(f"**{item['scheme_name']}**")
            st.write(item["benefit_summary"])
            st.caption(
                f"Source: {item['source_url']} | Verified: {item['last_verified_date']}"
            )

    if eligible:
        st.subheader("Ask FinSight Assistant")
        st.caption(
            "Ask about eligibility, benefits, documents, or how to apply. "
            "Answers use the selected scheme guide—not your transaction data."
        )
        scheme_names = [item["scheme_name"] for item in eligible]
        selected_scheme = st.selectbox(
            "Scheme", scheme_names, key="assistant_scheme"
        )
        question = st.text_input(
            "What would you like to know?",
            placeholder="Example: Which documents do I need and how do I apply?",
            key="assistant_question",
        )
        if st.button("Ask assistant", type="primary", disabled=not question.strip()):
            try:
                response = answer_scheme_question(selected_scheme, question)
                with st.container(border=True):
                    st.write(response.answer)
                    if response.mode == "local":
                        st.caption(
                            "Verified-guide mode · Add GROQ_API_KEY for a more conversational answer."
                        )
                    else:
                        st.caption("AI answer grounded in the verified scheme guide.")
                    with st.expander("Reference sections"):
                        st.caption("Sections used from the selected scheme guide:")
                        headings = set()
                        for passage in response.passages:
                            heading = passage.heading.strip()
                            if heading and heading not in headings:
                                st.markdown(f"- {heading}")
                                headings.add(heading)
            except SchemeAssistantError as error:
                st.warning(str(error))
            except Exception:
                st.warning(
                    "The AI service is temporarily unavailable. The scheme details above are still available."
                )

    with st.expander("Schemes not matched"):
        for item in eligibility_results:
            if not item.get("eligible"):
                st.write(f"**{item['scheme_name']}**")
                for check_name, passed in item.get("checks", []):
                    if not passed:
                        st.write(f"❌ {check_name}")

    st.subheader("Download report")
    if st.button("Generate PDF report"):
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
            pdf_buffer = generate_report(report, eligibility_results)
            st.download_button(
                "Download PDF Report",
                data=pdf_buffer.getvalue(),
                file_name="finsight_report.pdf",
                mime="application/pdf",
            )
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

    business = scope.get("business")
    account = scope.get("account")
    business_name = (
        business.get("business_name") if isinstance(business, dict) else "Selected business"
    )
    account_name = (
        account.get("account_name") if isinstance(account, dict) else "Selected account"
    )
    st.title("FinSight financial dashboard")
    st.caption(
        f"{business_name} · {account_name} · "
        f"{scope['start_date']} to {scope['end_date']}"
    )
    _render_summary(st, scope["analytics"], scope["currency"])
    with st.expander("Government scheme matching"):
        _render_schemes_and_report(st, session_token, scope)
    return True


def render_reports_page(st: Any, session_token: Any, scope: Any) -> bool:
    st.title("Reports and schemes")
    if not isinstance(scope, dict) or not isinstance(scope.get("analytics"), dict):
        st.info("Open Dashboard and choose a business, account, and date range first.")
        return False
    business = scope.get("business", {})
    account = scope.get("account", {})
    st.caption(
        f"{business.get('business_name', 'Selected business')} · "
        f"{account.get('account_name', 'Selected account')} · "
        f"{scope['start_date']} to {scope['end_date']}"
    )
    _render_schemes_and_report(st, session_token, scope)
    return True


__all__ = ["render_database_dashboard", "render_reports_page"]
