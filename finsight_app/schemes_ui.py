"""Authenticated Government Scheme screening UI."""

from decimal import Decimal, InvalidOperation
from typing import Any

from finsight_app.eligibility_engine import find_relevant_schemes
from finsight_app import scheme_rag


def _optional_decimal(value: str):
    value = (value or "").strip().replace(",", "")
    if not value:
        return None
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise ValueError("Annual turnover must be a valid number.")
    if number < 0:
        raise ValueError("Annual turnover cannot be negative.")
    return float(number)


def _optional_int(value: str, label: str):
    value = (value or "").strip()
    if not value:
        return None
    try:
        number = int(value)
    except ValueError:
        raise ValueError(f"{label} must be a whole number.")
    if number < 0:
        raise ValueError(f"{label} cannot be negative.")
    return number


def _bool_choice(value: str):
    if value == "Yes":
        return True
    if value == "No":
        return False
    return None


def render_government_schemes(
    st: Any,
    token: str,
    business: dict[str, Any],
) -> bool:
    del token  # authorization has already been enforced by the workspace/router.
    business_id = business["business_id"]
    st.subheader("Government Schemes")
    st.caption(
        "FinSight screens the repository's scheme rules using information you "
        "provide. Missing information remains unknown; eligibility is never invented."
    )

    with st.container(border=True):
        st.markdown(f"**Business:** {business['business_name']}")
        st.write("Known business type:", business.get("business_type") or "Not specified")

    st.markdown("#### Business information for scheme screening")
    state = st.text_input(
        "State",
        key=f"scheme_state_{business_id}",
        placeholder="e.g. Maharashtra",
    )
    sector_options = ["Select sector", "Service", "Manufacturing", "Other"]
    exact_type = business.get("business_type")
    default_sector = "Manufacturing" if exact_type == "Manufacturing" else (
        "Service" if exact_type == "Services" else "Select sector"
    )
    sector = st.selectbox(
        "Scheme sector",
        sector_options,
        index=sector_options.index(default_sector),
        key=f"scheme_sector_{business_id}",
    )
    category = st.selectbox(
        "Business size / category",
        ["Select category", "Micro", "Small", "Startup", "Other"],
        key=f"scheme_category_{business_id}",
    )
    turnover_text = st.text_input(
        "Annual turnover (INR, if known)",
        key=f"scheme_turnover_{business_id}",
        help="Enter a business-profile figure only if you know it. FinSight will not infer it from unrelated fields.",
    )
    owner_age_text = st.text_input(
        "Owner age (if relevant and voluntarily supplied)",
        key=f"scheme_owner_age_{business_id}",
    )
    udyam = st.selectbox(
        "Udyam / MSME registered?",
        ["Unknown / not provided", "Yes", "No"],
        key=f"scheme_udyam_{business_id}",
    )
    startup = st.selectbox(
        "DPIIT startup recognised?",
        ["Unknown / not provided", "Yes", "No"],
        key=f"scheme_startup_{business_id}",
    )
    new_unit = st.selectbox(
        "New / greenfield enterprise?",
        ["Unknown / not provided", "Yes", "No"],
        key=f"scheme_new_unit_{business_id}",
    )
    tarun = st.selectbox(
        "Prior Tarun loan repaid?",
        ["Unknown / not provided", "Yes", "No"],
        key=f"scheme_tarun_{business_id}",
    )
    ownership = st.selectbox(
        "Ownership category (optional / voluntary)",
        ["Prefer not to say", "Woman-owned", "SC/ST-owned", "Other / Not applicable"],
        key=f"scheme_ownership_{business_id}",
        help="This is used only when a scheme explicitly depends on that criterion.",
    )

    if st.button("Check Relevant Schemes", type="primary"):
        try:
            profile = {
                "state": state.strip() or None,
                "sector": None if sector == "Select sector" else sector,
                "business_category": None if category == "Select category" else category,
                "annual_turnover": _optional_decimal(turnover_text),
                "owner_age": _optional_int(owner_age_text, "Owner age"),
                "udyam_registered": _bool_choice(udyam),
                "startup_recognized": _bool_choice(startup),
                "new_or_greenfield": _bool_choice(new_unit),
                "prior_tarun_repaid": _bool_choice(tarun),
                "ownership_category": ownership,
            }
        except ValueError as error:
            st.error(str(error))
            return False
        try:
            results = find_relevant_schemes(profile)
        except Exception:
            st.error("Scheme rules could not be loaded from the FinSight scheme dataset.")
            return False
        st.session_state[f"scheme_results_{business_id}"] = results
        st.session_state[f"scheme_profile_{business_id}"] = profile

    results = st.session_state.get(f"scheme_results_{business_id}")
    if not isinstance(results, list):
        st.info("Provide the available business information, then select **Check Relevant Schemes**.")
        return True

    order = {
        "Likely relevant based on supplied information": 0,
        "Potentially relevant": 1,
        "Not matched based on supplied information": 2,
    }
    results = sorted(results, key=lambda item: (order.get(item.get("relevance"), 9), item.get("scheme_name", "")))

    for item in results:
        with st.container(border=True):
            st.markdown(f"### {item.get('scheme_name', 'Scheme')}")
            st.write(item.get("benefit_summary", ""))
            st.caption(f"Status: {item.get('relevance', 'Potentially relevant')}")
            missing = item.get("missing_information") or []
            failed = item.get("failed_reasons") or []
            if missing:
                st.write("**Additional information required:**")
                for value in missing:
                    st.write(f"- {value}")
            if failed:
                st.write("**Current mismatches:**")
                for value in failed:
                    st.write(f"- {value}")
            checks = item.get("checks") or []
            if checks:
                with st.expander("Rule checks"):
                    for check in checks:
                        marker = "✓" if check.get("passed") else "Not met"
                        st.write(f"{marker} — {check.get('name')}")
            source = item.get("source_url")
            if source:
                st.link_button("Open Source", source)

            scheme_name = item.get("scheme_name", "")
            if scheme_rag.supports_scheme(scheme_name):
                with st.expander("Ask about this scheme"):
                    status = scheme_rag.rag_status()
                    if not status["dependencies_available"]:
                        st.info(
                            "Scheme document Q&A is unavailable because the optional "
                            "RAG dependencies are not installed. Deterministic scheme "
                            "screening above is still active."
                        )
                    elif not status["api_key_configured"]:
                        st.info(
                            "Scheme document Q&A requires GROQ_API_KEY. "
                            "Deterministic screening above is still active."
                        )
                    else:
                        question = st.text_input(
                            "Question",
                            key=f"scheme_question_{business_id}_{scheme_name}",
                        )
                        if st.button(
                            "Ask Scheme Documents",
                            key=f"scheme_ask_{business_id}_{scheme_name}",
                        ):
                            if not question.strip():
                                st.warning("Enter a question first.")
                            else:
                                try:
                                    answer = scheme_rag.ask_scheme_question(
                                        scheme_name, question.strip()
                                    )
                                    st.write(answer)
                                except scheme_rag.SchemeRAGUnavailable as error:
                                    st.info(str(error))
                                except Exception:
                                    st.error(
                                        "Scheme document Q&A could not be completed. "
                                        "No eligibility result was fabricated."
                                    )
    return True
