"""FinSight's authenticated, database-backed Streamlit application."""

import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from database import db
from finsight_app.analytics_ui import render_analytics_page
from finsight_app.dashboard_ui import render_reports_page
from finsight_app.ingestion_ui import render_ingestion_page
from finsight_app.workspace_ui import render_workspace_setup
from services import auth_service

st.set_page_config(
    page_title="FinSight — MSME Financial Analytics",
    page_icon="💠",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _styles() -> None:
    st.markdown(
        """<style>
        :root {--fs-blue:#58a6ff;--fs-violet:#8b7cff;--fs-mint:#3dd9b3;--fs-line:rgba(148,163,184,.18);}
        .stApp {
          background:
            radial-gradient(circle at 75% -10%, rgba(88,166,255,.13), transparent 33rem),
            radial-gradient(circle at 20% 105%, rgba(61,217,179,.08), transparent 28rem),
            #0b0f17;
        }
        .block-container {max-width: 1220px; padding-top: 2.2rem; padding-bottom: 4rem;}
        [data-testid="stSidebar"] {
          background:linear-gradient(180deg,#111827 0%,#161b2b 100%);
          border-right:1px solid var(--fs-line);
        }
        [data-testid="stSidebar"] [data-testid="stRadio"] label {
          padding:.42rem .65rem;border-radius:10px;transition:background .15s ease;
        }
        [data-testid="stSidebar"] [data-testid="stRadio"] label:hover {background:rgba(88,166,255,.08);}
        h1 {font-size:clamp(2.2rem,4vw,3.35rem)!important;letter-spacing:-.045em!important;line-height:1.05!important;}
        h2,h3 {letter-spacing:-.025em!important;}
        [data-testid="stMetric"] {
          background:linear-gradient(145deg,rgba(30,41,59,.82),rgba(15,23,42,.72));
          border:1px solid var(--fs-line);border-radius:18px;padding:1.2rem 1.25rem;
          box-shadow:0 18px 45px rgba(0,0,0,.16);min-height:128px;
        }
        [data-testid="stMetricValue"] {font-weight:720;letter-spacing:-.035em;}
        div[data-testid="stAlert"] {border-radius:14px;border:1px solid var(--fs-line);}
        [data-testid="stVerticalBlockBorderWrapper"] {
          border-color:var(--fs-line)!important;border-radius:18px!important;
          background:rgba(15,23,42,.38);box-shadow:0 16px 44px rgba(0,0,0,.12);
        }
        .stButton>button,.stDownloadButton>button {border-radius:11px;min-height:2.8rem;font-weight:650;}
        .stButton>button[kind="primary"] {
          background:linear-gradient(100deg,var(--fs-blue),var(--fs-violet));border:0;
          box-shadow:0 10px 28px rgba(88,166,255,.22);
        }
        [data-baseweb="select"]>div,.stTextInput input,.stNumberInput input {border-radius:11px!important;}
        [data-testid="stDataFrame"] {border:1px solid var(--fs-line);border-radius:14px;overflow:hidden;}
        .fs-brand {font-size:1.55rem;font-weight:800;letter-spacing:-.04em;margin-bottom:.25rem;}
        .fs-muted {opacity:.7;font-size:.88rem;line-height:1.6;}
        @media (max-width: 768px) {.block-container {padding:1.25rem 1rem 3rem;} [data-testid="stMetric"] {min-height:auto;}}
        </style>""",
        unsafe_allow_html=True,
    )


def _initialize() -> None:
    if not st.session_state.get("_finsight_database_initialized"):
        db.initialize_database()
        st.session_state["_finsight_database_initialized"] = True


def _authentication() -> str | None:
    token = st.session_state.get("auth_token")
    if token:
        session = auth_service.validate_session(token)
        if session.get("success"):
            with st.sidebar:
                st.markdown('<div class="fs-brand">💠 FinSight</div>', unsafe_allow_html=True)
                st.caption(f"Signed in as {session['user']['username']}")
            return token
        st.session_state.pop("auth_token", None)

    st.title("Welcome to FinSight")
    st.caption("Financial clarity and scheme discovery for Indian MSMEs.")
    sign_in, create = st.tabs(["Sign in", "Create account"])
    with sign_in:
        with st.form("sign_in_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)
        if submitted:
            result = auth_service.login(email, password)
            if result.get("success"):
                st.session_state["auth_token"] = result["session"]["token"]
                st.rerun()
            if result.get("error") == "LOGIN_THROTTLED":
                st.warning(result["message"])
            else:
                st.error("Check your email and password and try again.")
    with create:
        with st.form("create_user_form"):
            username = st.text_input("Name")
            email = st.text_input("Email", key="signup_email")
            contact = st.text_input("Contact number")
            password = st.text_input("Password", type="password", key="signup_password")
            confirm = st.text_input("Confirm password", type="password")
            submitted = st.form_submit_button("Create account", type="primary", use_container_width=True)
        if submitted:
            if password != confirm:
                st.error("Passwords do not match.")
            else:
                result = auth_service.signup(username, email, contact, password)
                if result.get("success"):
                    st.success("Account created. You can now sign in.")
                else:
                    st.error(result.get("message", "The account could not be created."))
    return None


def _navigation(token: str) -> str:
    with st.sidebar:
        page = st.radio(
            "Navigation",
            ["Setup", "Import", "Dashboard", "Reports"],
            label_visibility="collapsed",
        )
        st.divider()
        if st.button("Sign out", use_container_width=True):
            auth_service.logout(token)
            st.session_state.clear()
            st.rerun()
        st.markdown('<div class="fs-muted">Your financial data stays separated by business and account.</div>', unsafe_allow_html=True)
    return page


_initialize()
_styles()
auth_token = _authentication()
if not auth_token:
    st.stop()

page = _navigation(auth_token)
if page == "Setup":
    render_workspace_setup(st, auth_token)
elif page == "Import":
    render_ingestion_page(st, auth_token)
elif page == "Dashboard":
    scope = render_analytics_page(st, auth_token, return_scope=True)
    if isinstance(scope, dict):
        st.session_state["_finsight_analytics_scope"] = scope
else:
    render_reports_page(st, auth_token, st.session_state.get("_finsight_analytics_scope"))
