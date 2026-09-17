"""FinSight authenticated Streamlit application."""

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
    page_title="FinSight | MSME Financial Analytics",
    page_icon="FS",
    layout="wide",
    initial_sidebar_state="expanded",
)


def apply_styles() -> None:
    st.markdown(
        """
        <style>
        @import url("https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Playfair+Display:wght@600;700&display=swap");

        :root {
            --fs-blue: #8DB4D6;
            --fs-blue-dark: #547C9C;
            --fs-blue-soft: #D6E6F2;
            --fs-blue-pale: #F2F7FB;
            --fs-white: #FFFFFF;
            --fs-ink: #20313E;
            --fs-muted: #647482;
            --fs-border: #BCD0DF;
            --fs-border-light: #DDE9F1;
            --fs-success: #E5F1E9;
            --fs-success-ink: #2D6A4F;
        }

        html, body, [class*="css"] {
            font-family: "DM Sans", Arial, sans-serif;
        }

        .stApp {
            background: var(--fs-blue-pale);
            color: var(--fs-ink);
        }

        .block-container {
            max-width: 1240px;
            padding: 2.6rem 3.2rem 4rem;
        }

        [data-testid="stSidebar"] {
            background: var(--fs-white);
            border-right: 1px solid var(--fs-border);
        }

        [data-testid="stSidebar"] > div:first-child {
            padding: 2rem 1.2rem;
        }

        h1, h2, h3 {
            color: var(--fs-ink) !important;
            font-family: "Playfair Display", Georgia, serif !important;
            letter-spacing: 0 !important;
        }

        h1 {
            font-size: 2.75rem !important;
            line-height: 1.08 !important;
            margin-bottom: 0.45rem !important;
        }

        h2 {
            font-size: 1.85rem !important;
        }

        h3 {
            font-size: 1.35rem !important;
        }

        p, label, [data-testid="stCaptionContainer"] {
            color: var(--fs-muted) !important;
        }

        .fs-logo {
            display: flex;
            align-items: center;
            gap: 0.7rem;
            margin-bottom: 0.35rem;
        }

        .fs-logo-mark {
            width: 34px;
            height: 34px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: var(--fs-blue);
            color: var(--fs-white);
            border: 1px solid var(--fs-blue-dark);
            font-weight: 700;
            font-size: 0.78rem;
        }

        .fs-logo-name {
            color: var(--fs-ink);
            font-size: 1.4rem;
            font-weight: 700;
        }

        .fs-sidebar-user {
            color: var(--fs-muted);
            font-size: 0.84rem;
            margin: 0.7rem 0 1.8rem;
        }

        .fs-side-note {
            border-top: 1px solid var(--fs-border-light);
            margin-top: 1.5rem;
            padding-top: 1.2rem;
            color: var(--fs-muted);
            font-size: 0.83rem;
            line-height: 1.6;
        }

        [data-testid="stSidebar"] [data-testid="stRadio"] label {
            border: 1px solid transparent;
            border-radius: 4px;
            color: var(--fs-ink) !important;
            margin: 0.15rem 0;
            padding: 0.6rem 0.55rem;
        }

        [data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
            background: var(--fs-blue-pale);
            border-color: var(--fs-border-light);
        }

        [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
            background: var(--fs-blue-soft);
            border-color: var(--fs-blue);
            font-weight: 600;
        }

        .fs-eyebrow {
            color: var(--fs-blue-dark);
            font-size: 0.74rem;
            font-weight: 700;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            margin-bottom: 0.55rem;
        }

        .fs-page-intro {
            border-bottom: 1px solid var(--fs-border);
            margin-bottom: 1.8rem;
            padding-bottom: 1.35rem;
        }

        .fs-page-intro p {
            font-size: 1rem;
            margin: 0;
        }

        .fs-auth-panel {
            background: var(--fs-white);
            border: 1px solid var(--fs-border);
            padding: 2rem;
        }

        .fs-auth-copy {
            padding: 1rem 2.5rem 1rem 0;
        }

        .fs-auth-copy h1 {
            font-size: 3.15rem !important;
        }

        .fs-step {
            border-top: 1px solid var(--fs-border);
            display: grid;
            gap: 0.25rem;
            grid-template-columns: 2.7rem 1fr;
            margin-top: 1rem;
            padding-top: 0.9rem;
        }

        .fs-step-number {
            color: var(--fs-blue-dark);
            font-size: 0.76rem;
            font-weight: 700;
        }

        .fs-step-title {
            color: var(--fs-ink);
            font-weight: 700;
        }

        .fs-step-text {
            color: var(--fs-muted);
            font-size: 0.9rem;
            grid-column: 2;
        }

        .stButton > button,
        .stDownloadButton > button,
        [data-testid="stFormSubmitButton"] > button {
            border: 1px solid var(--fs-blue-dark) !important;
            border-radius: 4px !important;
            box-shadow: none !important;
            font-family: "DM Sans", Arial, sans-serif !important;
            font-weight: 700 !important;
            min-height: 2.65rem !important;
        }

        .stButton > button[kind="primary"],
        [data-testid="stFormSubmitButton"] > button[kind="primary"] {
            background: var(--fs-blue-dark) !important;
            color: var(--fs-white) !important;
        }

        .stButton > button:not([kind="primary"]),
        .stDownloadButton > button {
            background: var(--fs-white) !important;
            color: var(--fs-ink) !important;
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover {
            border-color: var(--fs-blue-dark) !important;
            background: var(--fs-blue-soft) !important;
        }

        .stTextInput input,
        .stNumberInput input,
        .stDateInput input,
        [data-baseweb="select"] > div {
            background: var(--fs-white) !important;
            border: 1px solid var(--fs-border) !important;
            border-radius: 4px !important;
            color: var(--fs-ink) !important;
        }

        [data-testid="stMetric"] {
            background: var(--fs-white);
            border: 1px solid var(--fs-border);
            border-radius: 4px;
            box-shadow: none;
            padding: 1.05rem;
        }

        [data-testid="stMetricLabel"] {
            color: var(--fs-muted) !important;
            font-size: 0.8rem !important;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }

        [data-testid="stMetricValue"] {
            color: var(--fs-ink) !important;
            font-family: "Playfair Display", Georgia, serif !important;
        }

        [data-testid="stVerticalBlockBorderWrapper"] {
            background: var(--fs-white);
            border: 1px solid var(--fs-border) !important;
            border-radius: 4px !important;
            box-shadow: none !important;
        }

        [data-testid="stDataFrame"] {
            border: 1px solid var(--fs-border);
            border-radius: 4px;
            overflow: hidden;
        }

        [data-testid="stTabs"] [data-baseweb="tab-list"] {
            border-bottom: 1px solid var(--fs-border);
            gap: 1.3rem;
        }

        [data-testid="stTabs"] button {
            color: var(--fs-muted);
            font-weight: 700;
        }

        [data-testid="stTabs"] button[aria-selected="true"] {
            color: var(--fs-blue-dark);
        }

        div[data-testid="stAlert"] {
            border-radius: 4px;
            border: 1px solid var(--fs-border);
        }

        @media (max-width: 760px) {
            .block-container {
                padding: 1.4rem 1rem 3rem;
            }

            .fs-auth-copy {
                padding-right: 0;
            }

            .fs-auth-copy h1 {
                font-size: 2.35rem !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def initialize_database() -> None:
    if not st.session_state.get("_finsight_database_initialized"):
        db.initialize_database()
        st.session_state["_finsight_database_initialized"] = True


def render_authentication() -> str | None:
    token = st.session_state.get("auth_token")
    if token:
        session = auth_service.validate_session(token)
        if session.get("success"):
            return token
        st.session_state.pop("auth_token", None)

    left, right = st.columns([1.08, 0.92], gap="large")

    with left:
        st.caption("FINSIGHT FOR MSMEs")
        st.title("Financial clarity for your business.")
        st.write(
            "Bring your transactions, business health, reports, and government "
            "scheme guidance into one focused workspace."
        )

        steps = [
            ("01", "Create your account", "Secure access to your financial workspace."),
            ("02", "Add your business", "Set up a business and financial account once."),
            ("03", "Import transactions", "Upload CSV, JSON, or XML data for analysis."),
            ("04", "Review and download reports", "Use the dashboard, scheme finder, and PDF report."),
        ]

        for number, title, description in steps:
            number_column, text_column = st.columns([1, 8])
            with number_column:
                st.markdown(f"### {number}")
            with text_column:
                st.markdown(f"**{title}**")
                st.caption(description)
            st.divider()

    with right:
        st.markdown("### Access FinSight")
        st.caption("Use your email and password to continue.")

        sign_in_tab, create_tab = st.tabs(["Sign in", "Create account"])

        with sign_in_tab:
            with st.form("sign_in_form"):
                email = st.text_input("Email address", key="login_email")
                password = st.text_input("Password", type="password", key="login_password")
                submitted = st.form_submit_button(
                    "Sign in", type="primary", width="stretch"
                )

            if submitted:
                result = auth_service.login(email, password)
                if result.get("success"):
                    st.session_state["auth_token"] = result["session"]["token"]
                    st.rerun()
                else:
                    st.error(result.get("message", "Unable to sign in."))

            st.button(
                "Continue with Google",
                disabled=True,
                width="stretch",
                help="Google sign-in needs OAuth credentials before it can be enabled.",
            )
            st.caption("Google sign-in will be enabled after OAuth is configured.")

        with create_tab:
            with st.form("create_user_form"):
                username = st.text_input("Your name", key="signup_username")
                email = st.text_input("Email address", key="signup_email")
                contact = st.text_input("Contact number", key="signup_contact")
                password = st.text_input(
                    "Password", type="password", key="signup_password"
                )
                confirm = st.text_input(
                    "Confirm password", type="password", key="signup_confirm"
                )
                submitted = st.form_submit_button(
                    "Create account", type="primary", width="stretch"
                )

            if submitted:
                if password != confirm:
                    st.error("Passwords do not match.")
                else:
                    result = auth_service.signup(username, email, contact, password)
                    if result.get("success"):
                        st.success("Account created. Please sign in to continue.")
                    else:
                        st.error(result.get("message", "Unable to create the account."))

    return None


def render_navigation(token: str) -> str:
    session = auth_service.validate_session(token)
    username = session.get("user", {}).get("username", "User")

    with st.sidebar:
        st.markdown(
            """
            <div class="fs-logo">
                <div class="fs-logo-mark">FS</div>
                <div class="fs-logo-name">FinSight</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="fs-sidebar-user">Signed in as {username}</div>',
            unsafe_allow_html=True,
        )

        page = st.radio(
            "Navigation",
            [
                "01 / Business",
                "02 / Transactions",
                "03 / Dashboard",
                "04 / Reports",
            ],
            label_visibility="collapsed",
            key="main_navigation",
        )

        st.divider()

        if st.button("Sign out", width="stretch"):
            auth_service.logout(token)
            st.session_state.clear()
            st.rerun()

        st.markdown(
            """
            <div class="fs-side-note">
                Your businesses and financial accounts remain separate. Select the correct business before uploading or reviewing reports.
            </div>
            """,
            unsafe_allow_html=True,
        )

    return page


def render_page_heading(page: str) -> None:
    headings = {
        "01 / Business": (
            "01 / Business profile",
            "Enter your business details and create the account where transactions will be stored.",
        ),
        "02 / Transactions": (
            "02 / Import transactions",
            "Upload financial data, review the result, and keep your records ready for analysis.",
        ),
        "03 / Dashboard": (
            "03 / Financial dashboard",
            "Review revenue, expenses, cash flow, category patterns, and business health.",
        ),
        "04 / Reports": (
            "04 / Reports and schemes",
            "Generate a clear financial report and review relevant government scheme guidance.",
        ),
    }

    eyebrow, description = headings[page]
    st.markdown(
        f"""
        <div class="fs-page-intro">
            <div class="fs-eyebrow">{eyebrow}</div>
            <p>{description}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


initialize_database()
apply_styles()

auth_token = render_authentication()
if not auth_token:
    st.stop()

selected_page = render_navigation(auth_token)
render_page_heading(selected_page)

if selected_page == "01 / Business":
    render_workspace_setup(st, auth_token)

elif selected_page == "02 / Transactions":
    render_ingestion_page(st, auth_token)

elif selected_page == "03 / Dashboard":
    selected_scope = render_analytics_page(
        st,
        auth_token,
        return_scope=True,
    )
    if isinstance(selected_scope, dict):
        st.session_state["_finsight_analytics_scope"] = selected_scope

else:
    render_reports_page(
        st,
        auth_token,
        st.session_state.get("_finsight_analytics_scope"),
    )

