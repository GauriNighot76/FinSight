"""FinSight Streamlit application entry point."""

import sys
from collections import Counter
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database import db
from finsight_app.analytics_ui import render_analytics_page
from finsight_app.business_ui import render_create_business, render_manage_businesses
from finsight_app.ingestion_ui import render_ingestion_page
from finsight_app.reports_ui import render_reports
from finsight_app.schemes_ui import render_government_schemes
from finsight_app.workspace_ui import (
    render_anomalies,
    render_business_health,
    render_overview,
    render_recommendations,
    render_transactions,
)
from services import auth_service, business_service


db.initialize_database()

st.set_page_config(page_title="FinSight", page_icon="📊", layout="wide")

st.markdown(
    """
<style>
.stApp { background: #F7FBFE; color: #173B57; }
[data-testid="stSidebar"] {
    background: #DFF3FF;
    border-right: 1px solid #D7E9F4;
}
div[data-testid="stMetric"] {
    background: #FFFFFF;
    border: 1px solid #D7E9F4;
    border-radius: 12px;
    padding: 16px;
    box-shadow: 0 2px 10px rgba(23,59,87,.05);
}
div[data-testid="stForm"],
div[data-testid="stVerticalBlockBorderWrapper"] {
    border-color: #D7E9F4 !important;
}
.stButton > button {
    background: #4EA5D9;
    color: white;
    border: 0;
    border-radius: 8px;
}
.stButton > button:hover {
    background: #3D94C8;
    color: white;
}
h1, h2, h3 { color: #173B57; }
[data-testid="stDataFrame"] { border: 1px solid #D7E9F4; border-radius: 10px; }

/* Keep form controls readable even when the browser/OS is using dark mode. */
div[data-baseweb="input"] {
    background: #FFFFFF !important;
    border: 1px solid #C8DFEC !important;
}
div[data-baseweb="input"] input {
    color: #173B57 !important;
    -webkit-text-fill-color: #173B57 !important;
    caret-color: #173B57 !important;
}
div[data-baseweb="input"] input::placeholder {
    color: #7A8E9E !important;
    opacity: 1 !important;
}
div[data-baseweb="select"] > div {
    background: #FFFFFF !important;
    color: #173B57 !important;
    border-color: #C8DFEC !important;
}
div[data-baseweb="select"] span,
div[data-baseweb="select"] svg {
    color: #173B57 !important;
    fill: #173B57 !important;
}
label[data-testid="stWidgetLabel"] p,
[data-testid="stTextInput"] label p,
[data-testid="stSelectbox"] label p {
    color: #173B57 !important;
    opacity: 1 !important;
}
[data-testid="stTextInput"] button,
[data-testid="stTextInput"] svg {
    color: #526B7C !important;
}

</style>
""",
    unsafe_allow_html=True,
)

NAVIGATION = [
    "Overview",
    "Upload Transactions",
    "Transactions",
    "Financial Analytics",
    "Business Health",
    "Anomalies",
    "Recommendations",
    "Government Schemes",
    "Reports",
]


def _clear_user_state() -> None:
    for key in list(st.session_state.keys()):
        del st.session_state[key]


def _clear_business_scoped_state() -> None:
    prefixes = (
        "upload_",
        "analysis_",
        "report_",
        "scheme_",
        "transaction_",
    )
    for key in list(st.session_state.keys()):
        if key.startswith(prefixes):
            del st.session_state[key]


def _render_authentication() -> None:
    st.markdown("<h1 style='text-align:center'>FinSight</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p style='text-align:center;color:#66788A'>"
        "Financial Analytics & Transaction Intelligence for MSMEs"
        "</p>",
        unsafe_allow_html=True,
    )
    _left, center, _right = st.columns([1, 1.25, 1])
    with center:
        mode = st.radio(
            "Account",
            ["Sign In", "Register"],
            horizontal=True,
            label_visibility="collapsed",
            key="auth_mode",
        )
        with st.container(border=True):
            if mode == "Sign In":
                st.subheader("Welcome back")
                email = st.text_input("Email", key="login_email")
                password = st.text_input(
                    "Password",
                    type="password",
                    key="login_password",
                )
                if st.button("Sign In", use_container_width=True):
                    result = auth_service.login(email, password)
                    if result.get("success"):
                        token = result["session"]["token"]
                        _clear_user_state()
                        st.session_state["auth_token"] = token
                        st.session_state["app_page"] = "Overview"
                        st.session_state["nav_choice"] = "Overview"
                        st.rerun()
                    st.error("Unable to sign in. Check your credentials and try again.")
            else:
                st.subheader("Create your FinSight account")
                username = st.text_input("Name", key="register_name")
                email = st.text_input("Email", key="register_email")
                phone = st.text_input("Phone", key="register_phone")
                password = st.text_input(
                    "Password",
                    type="password",
                    key="register_password",
                )
                if st.button("Register", use_container_width=True):
                    result = auth_service.signup(username, email, phone, password)
                    if not result.get("success"):
                        st.error(result.get("message", "Registration failed."))
                        return
                    login = auth_service.login(email, password)
                    if not login.get("success"):
                        st.error("Account created, but automatic sign-in failed.")
                        return
                    token = login["session"]["token"]
                    _clear_user_state()
                    st.session_state["auth_token"] = token
                    st.session_state["app_page"] = "Create Business"
                    st.session_state["nav_choice"] = "Overview"
                    st.rerun()


def _display_names(businesses):
    counts = Counter(item["business_name"] for item in businesses)
    seen = Counter()
    labels = {}
    for business in businesses:
        name = business["business_name"]
        seen[name] += 1
        if counts[name] == 1:
            labels[business["business_id"]] = name
        else:
            business_type = business.get("business_type") or "Business"
            labels[business["business_id"]] = (
                f"{name} — {business_type} ({seen[name]})"
            )
    return labels


def _nav_changed():
    st.session_state["app_page"] = st.session_state["nav_choice"]


token = st.session_state.get("auth_token")
session = auth_service.validate_session(token) if token else {"success": False}
if not session.get("success"):
    if token:
        _clear_user_state()
    _render_authentication()
    st.stop()

businesses_result = business_service.list_user_businesses(token)
businesses = (
    businesses_result.get("businesses", [])
    if isinstance(businesses_result, dict) and businesses_result.get("success")
    else []
)

if not businesses:
    st.markdown("## FinSight")
    st.caption(f"Signed in as {session['user']['username']}")
    render_create_business(st, token, first_business=True)
    if st.button("Logout"):
        auth_service.logout(token)
        _clear_user_state()
        st.rerun()
    st.stop()

business_ids = [item["business_id"] for item in businesses]
selected_id = st.session_state.get("selected_business_id")
if selected_id not in business_ids:
    selected_id = business_ids[0]
    st.session_state["selected_business_id"] = selected_id

display_names = _display_names(businesses)
selected_business = next(
    item for item in businesses if item["business_id"] == selected_id
)

pending_page = st.session_state.pop("pending_page", None)
if pending_page is not None:
    st.session_state["app_page"] = pending_page
    if pending_page in NAVIGATION:
        st.session_state["nav_choice"] = pending_page

if "app_page" not in st.session_state:
    st.session_state["app_page"] = "Overview"

# Keep the navigation widget aligned with the actual navigable page.  This
# runs before the widget is instantiated, which is the only safe time to
# programmatically change a widget-backed session key.
if st.session_state["app_page"] in NAVIGATION:
    st.session_state["nav_choice"] = st.session_state["app_page"]
else:
    # Create/Manage are workspace actions rather than sidebar destinations.
    # Use Overview as the neutral navigation selection so a previous page
    # such as Reports is never shown as active while a transient view is open.
    st.session_state["nav_choice"] = "Overview"

with st.sidebar:
    st.title("FinSight")
    st.caption("Financial Intelligence for MSMEs")
    st.markdown("#### Current Business")
    selector_index = business_ids.index(selected_id)
    new_selected_id = st.selectbox(
        "Business",
        options=business_ids,
        index=selector_index,
        format_func=lambda value: display_names[value],
        label_visibility="collapsed",
        key="business_selector",
    )
    if new_selected_id != selected_id:
        st.session_state["selected_business_id"] = new_selected_id
        _clear_business_scoped_state()
        selected_id = new_selected_id
        selected_business = next(
            item for item in businesses if item["business_id"] == selected_id
        )
        st.rerun()

    c1, c2 = st.columns(2)
    if c1.button("+ Create", use_container_width=True):
        st.session_state["pending_page"] = "Create Business"
        st.rerun()
    if c2.button("Manage", use_container_width=True):
        st.session_state["pending_page"] = "Manage Businesses"
        st.rerun()

    st.divider()
    st.markdown("#### Navigation")
    st.radio(
        "Navigation",
        NAVIGATION,
        key="nav_choice",
        label_visibility="collapsed",
        on_change=_nav_changed,
    )

    st.divider()
    st.markdown("#### Account")
    st.caption(f"Signed in as {session['user']['username']}")
    if st.button("Logout", use_container_width=True):
        auth_service.logout(token)
        _clear_user_state()
        st.rerun()

page = st.session_state.get("app_page", "Overview")

st.markdown("## FinSight")
st.caption(
    f"Financial Analytics for MSMEs · Business: {selected_business['business_name']}"
)

if page == "Create Business":
    render_create_business(st, token, first_business=False)
elif page == "Manage Businesses":
    render_manage_businesses(st, token, businesses, selected_id)
elif page == "Overview":
    render_overview(st, token, selected_business)
elif page == "Upload Transactions":
    render_ingestion_page(st, token, preferred_business_id=selected_id)
elif page == "Transactions":
    render_transactions(st, token, selected_business)
elif page == "Financial Analytics":
    render_analytics_page(st, token, preferred_business_id=selected_id)
elif page == "Business Health":
    render_business_health(st, token, selected_business)
elif page == "Anomalies":
    render_anomalies(st, token, selected_business)
elif page == "Recommendations":
    render_recommendations(st, token, selected_business)
elif page == "Government Schemes":
    render_government_schemes(st, token, selected_business)
elif page == "Reports":
    render_reports(st, token, selected_business)
else:
    st.session_state["pending_page"] = "Overview"
    st.rerun()
