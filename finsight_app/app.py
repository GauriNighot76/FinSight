import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database import db
from finsight_app.analytics_ui import render_analytics_page
from finsight_app.ingestion_ui import render_ingestion_page
from services import (
    account_service, auth_service, business_health_service, business_service,
    decision_support_service, report_service,
)

db.initialize_database()

st.set_page_config(page_title="FinSight", page_icon="📊", layout="wide")

st.markdown("""
<style>
.stApp { background: #F7FBFE; color: #173B57; }
[data-testid="stSidebar"] { background: #DFF3FF; border-right: 1px solid #D7E9F4; }
div[data-testid="stMetric"] { background: #FFFFFF; border: 1px solid #D7E9F4;
  border-radius: 12px; padding: 16px; box-shadow: 0 2px 10px rgba(23,59,87,.05); }
.stButton > button { background: #4EA5D9; color: white; border: 0; border-radius: 8px; }
.stButton > button:hover { background: #3D94C8; color: white; }
h1,h2,h3 { color: #173B57; }
</style>
""", unsafe_allow_html=True)


def _clear_user_state():
    for key in list(st.session_state.keys()):
        if key not in {"auth_mode"}:
            del st.session_state[key]


def _auth_screen():
    st.markdown("<h1 style='text-align:center'>FinSight</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center;color:#66788A'>Financial Analytics & Transaction Intelligence for MSMEs</p>", unsafe_allow_html=True)
    left, center, right = st.columns([1, 1.25, 1])
    with center:
        mode = st.radio("Account", ["Sign In", "Register"], horizontal=True, label_visibility="collapsed")
        with st.container(border=True):
            if mode == "Sign In":
                st.subheader("Welcome back")
                email = st.text_input("Email", key="login_email")
                password = st.text_input("Password", type="password", key="login_password")
                if st.button("Sign In", use_container_width=True):
                    result = auth_service.login(email, password)
                    if result.get("success"):
                        st.session_state["auth_token"] = result["session"]["token"]
                        st.rerun()
                    st.error("Unable to sign in. Check your credentials and try again.")
            else:
                st.subheader("Create your FinSight account")
                username = st.text_input("Name", key="register_name")
                email = st.text_input("Email", key="register_email")
                phone = st.text_input("Phone", key="register_phone")
                password = st.text_input("Password", type="password", key="register_password")
                if st.button("Register", use_container_width=True):
                    result = auth_service.signup(username, email, phone, password)
                    if result.get("success"):
                        login = auth_service.login(email, password)
                        if login.get("success"):
                            st.session_state["auth_token"] = login["session"]["token"]
                            st.rerun()
                    st.error(result.get("message", "Registration failed."))
    return None


def _business_setup(token):
    st.title("Set up your business")
    st.caption("Create a business to start uploading and analyzing transactions.")
    with st.form("create_business"):
        name = st.text_input("Business Name *")
        business_type = st.selectbox(
            "Business Type",
            ["Select business type", "Retail", "Medical / Pharmacy", "Hotel / Hospitality",
             "Clinic / Healthcare", "Services", "Manufacturing", "Trading", "Other"],
            index=0,
        )
        custom_type = st.text_input("Other business type") if business_type == "Other" else ""
        email = st.text_input("Business Email")
        phone = st.text_input("Business Phone")
        submitted = st.form_submit_button("Create Business")
    if submitted:
        result = business_service.create_business(token, {
            "business_name": name,
            "business_type": custom_type or (None if business_type == "Select business type" else business_type),
            "contact_email": email,
            "contact_phone": phone,
        })
        if result.get("success"):
            st.session_state["selected_business_id"] = result["business"]["business_id"]
            st.success("Business created successfully. You can upload transactions immediately.")
            st.rerun()
        else:
            st.error(result.get("message", "Business creation failed."))


token = st.session_state.get("auth_token")
session = auth_service.validate_session(token) if token else {"success": False}
if not session.get("success"):
    if token:
        _clear_user_state()
    _auth_screen()
    st.stop()

businesses_result = business_service.list_user_businesses(token)
businesses = businesses_result.get("businesses", []) if businesses_result.get("success") else []
if not businesses:
    _business_setup(token)
    st.stop()

with st.sidebar:
    st.title("FinSight")
    st.caption("Financial Analytics for MSMEs")
    labels = [b["business_name"] for b in businesses]
    ids = [b["business_id"] for b in businesses]
    current = st.session_state.get("selected_business_id")
    index = ids.index(current) if current in ids else 0
    selected_name = st.selectbox("Business", labels, index=index)
    selected_id = ids[labels.index(selected_name)]
    if selected_id != st.session_state.get("selected_business_id"):
        st.session_state["selected_business_id"] = selected_id
        for key in list(st.session_state.keys()):
            if key.startswith(("analysis_", "upload_", "report_")):
                del st.session_state[key]
    page = st.radio("Navigation", ["Overview", "Upload Transactions", "Financial Analytics", "Business Health", "Anomalies", "Recommendations", "Reports", "Government Schemes"])
    st.divider()
    st.caption(f"Signed in as {session['user']['username']}")
    if st.button("Logout", use_container_width=True):
        auth_service.logout(token)
        _clear_user_state()
        st.rerun()

st.markdown("## FinSight")
st.caption(f"Financial Analytics for MSMEs · Business: {selected_name}")

if page == "Overview":
    st.subheader("Welcome to FinSight")
    st.write("Your business is ready. Upload transaction data to start analyzing your finances.")
    st.info("Financial values are shown only from accepted transactions uploaded for the selected business.")
    if st.button("Upload Transactions"):
        st.session_state["nav_hint"] = "Upload Transactions"
        st.info("Choose **Upload Transactions** from the sidebar.")
elif page == "Upload Transactions":
    render_ingestion_page(st, token, preferred_business_id=selected_id)
elif page == "Financial Analytics":
    render_analytics_page(st, token, preferred_business_id=selected_id)
elif page in {"Business Health", "Anomalies", "Recommendations", "Reports"}:
    accounts_result = account_service.list_business_accounts(token, selected_id)
    accounts = accounts_result.get("accounts", []) if accounts_result.get("success") else []
    if not accounts:
        st.info("Upload transaction data to begin analysis.")
    else:
        account = accounts[0]
        service_args = {
            "session_token": token, "business_id": selected_id,
            "account_id": account["account_id"], "start_date": "2000-01-01",
            "end_date": "2099-12-31", "currency": account["currency"],
        }
        try:
            health = business_health_service.get_business_health(**service_args)
            count = int(health.get("metrics", {}).get("transaction_count", 0))
            if count == 0:
                st.info("This analysis will become available after transaction data is uploaded.")
            elif page == "Business Health":
                metrics = health["metrics"]
                st.subheader("Business Health")
                a, b, c1 = st.columns(3)
                a.metric("Health Score", metrics.get("health_score", "N/A"))
                b.metric("Health Level", metrics.get("health_level", "N/A"))
                c1.metric("Savings Rate", f"{metrics.get('savings_rate', 0)}%")
                st.write("Expense-to-Income Ratio:", metrics.get("expense_to_income_ratio", "N/A"))
                st.write("Cash Flow Stability:", metrics.get("cash_flow_stability", "N/A"))
                st.write("Category Concentration:", metrics.get("category_concentration", "N/A"))
                st.write("Recurring Expense Burden:", metrics.get("recurring_expense_burden", "N/A"))
            elif page == "Anomalies":
                st.subheader("Anomalies")
                anomalies = health.get("anomalies", [])
                if not anomalies:
                    st.success("No deterministic anomalies were detected for the available transactions.")
                for item in anomalies:
                    with st.container(border=True):
                        st.markdown(f"**{str(item.get('type', 'Anomaly')).replace('_', ' ').title()}**")
                        st.write(item.get("explanation") or item.get("reason") or "Review this transaction pattern.")
                        st.caption(f"Severity: {item.get('severity', 'N/A')}")
            elif page == "Recommendations":
                st.subheader("Recommendations")
                support = decision_support_service.get_decision_support(**service_args)
                recommendations = support.get("recommendations", [])
                if not recommendations:
                    st.info("No recommendations are available for the current transaction data.")
                for item in recommendations:
                    with st.container(border=True):
                        st.markdown(f"**{item.get('title', 'Recommendation')}**")
                        st.write(item.get("explanation") or item.get("reason", ""))
                        st.caption(f"Priority: {item.get('priority', 'N/A')}")
                        if item.get("recommended_action"):
                            st.write("Suggested action:", item["recommended_action"])
            else:
                st.subheader("Reports")
                report = report_service.build_report(**service_args)
                rows = report_service.report_to_csv_rows(report)
                import csv
                import io
                output = io.StringIO()
                if rows:
                    writer = csv.DictWriter(output, fieldnames=sorted({k for row in rows for k in row}))
                    writer.writeheader()
                    writer.writerows(rows)
                st.download_button("Download Executive Report (CSV)", output.getvalue(), "finsight_report.csv", "text/csv")
        except Exception:
            st.error("This section could not be loaded. Please verify your transaction data and try again.")
else:
    st.subheader("Government Schemes")
    st.info("Scheme matching is kept separate from financial analytics. Additional business information may be required to determine eligibility.")
    st.write("FinSight will not invent missing eligibility information or treat synthetic demo data as your business data.")
