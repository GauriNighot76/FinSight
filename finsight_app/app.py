import streamlit as st
from kpi_engine import compute_kpis
from eligibility_engine import check_eligibility
from pdf_generator import generate_report

st.set_page_config(page_title="FinSight - Scheme Suggestions", layout="centered")
st.title("FinSight: Financial Report & Government Scheme Matcher")
st.caption("Demo Coffee Shop | Synthetic dataset")

with st.expander("Business profile used for this demo (some fields are assumed)"):
    st.write("Sector: Service | State: Maharashtra (assumed) | Category: Micro (assumed) | Owner age: 30 (assumed)")
    st.write("Revenue and expenses below are REAL, computed from actual transaction data.")

kpis = compute_kpis()
business = {
    "turnover": kpis["annual_turnover"],
    "sector": "Service",
    "state": "Maharashtra",
    "business_category": "Micro",
    "owner_age": 30,
}
eligibility_results = check_eligibility(business)

st.header("Financial Summary")
col1, col2, col3 = st.columns(3)
col1.metric("Revenue", f"Rs {kpis['revenue_total']:,.0f}")
col2.metric("Net Profit", f"Rs {kpis['net_profit']:,.0f}")
col3.metric("Margin", f"{kpis['net_profit_margin']:.1f}%")
st.caption(f"Estimated annual turnover (used for scheme matching): Rs {kpis['annual_turnover']:,.0f}")

st.header("Matched Government Schemes")

eligible = [r for r in eligibility_results if r["eligible"]]
not_eligible = [r for r in eligibility_results if not r["eligible"]]

if not eligible:
    st.warning("No schemes matched.")
else:
    for r in eligible:
        with st.container(border=True):
            st.subheader(r["scheme_name"])
            st.write(r["benefit_summary"])
            st.caption(f"Source: {r['source_url']} | Verified: {r['last_verified_date']}")

            with st.expander("Why this business qualifies"):
                for check_name, passed in r["checks"]:
                    icon = "\u2705" if passed else "\u274c"
                    st.write(f"{icon} {check_name}")

            # RAG chat -- only imported here so the app can still run and demo
            # KPIs + eligibility even if the RAG/API piece has an issue
            with st.expander(f"Ask a question about {r['scheme_name']}"):
                question = st.text_input("Your question", key=f"q_{r['scheme_name']}")
                if question:
                    try:
                        from scheme_rag import load_index, ask_scheme_question
                        vectorstore = load_index()
                        answer = ask_scheme_question(r["scheme_name"], question, vectorstore)
                        st.write(answer)
                    except Exception as e:
                        st.error(f"Chat unavailable right now: {e}")

with st.expander("Schemes not matched"):
    for r in not_eligible:
        st.write(f"**{r['scheme_name']}**")
        for check_name, passed in r["checks"]:
            if not passed:
                st.write(f"  \u274c {check_name}")

st.header("Download Report")
pdf_buffer = generate_report("Demo Coffee Shop", kpis, eligibility_results)
st.download_button(
    "Download PDF Report",
    data=pdf_buffer,
    file_name="finsight_report.pdf",
    mime="application/pdf",
)
