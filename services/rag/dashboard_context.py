"""Small, read-only dashboard summaries; never transaction rows or credentials."""
from collections import Counter
from decimal import Decimal

GUIDE = """FinSight is a financial analytics workspace for MSMEs.
Overview: total income and expenses are accepted transaction totals; net cash flow
is income minus expense. Savings rate is net cash flow as a percentage of income.
Average transaction describes the mean transaction amount, not average profit.
Charts show monthly income/expense/net cash flow and expense categories.
Transactions: accepted uploaded records; ingestion checks and rejected rows appear
under Upload Transactions. Reports export the application's calculated results.
Business Health: a deterministic score and metrics, not an audited financial opinion.
Anomalies are review signals, not proof of fraud or duplicate records. Large amounts
use the Tukey outer fence (Q3 + 3*IQR) separately for income/expense, requiring at
least eight observations and positive IQR. Repeated patterns require at least four
occurrences across three dates; they are not necessarily duplicate uploads.
Other signals include unusual monthly expenses, income drops, negative daily cash
flow, inactive periods, category movements, and recurring expense burden.
Recommendations suggest reviewing the triggering metric or anomaly. Recurring
expenses refer to categories appearing across multiple months; they are not proof
that every transaction is a subscription. Review subscriptions and fixed costs
before taking action. Multiple recommendations may refer to related signals.
Government Schemes is advisory screening, not guaranteed loan approval.
Only supplied dashboard summaries describe this user's actual figures. Missing
summaries mean unavailable information, not zero or no anomalies. Monetary keys
ending in _minor are paise/minor units; divide by 100 for display. Other metrics
must retain their supplied units. Never invent account balances or transactions.
"""


def metrics(values):
    return {k: str(v) if isinstance(v, Decimal) else v for k, v in values.items()
            if isinstance(v, (int, float, Decimal)) or v is None
            or k in {"health_level", "health_rating"}}


def remember(st, business_id, *, analysis=None, health=None, support=None,
             scope="All uploaded dates (2000-01-01 to 2099-12-31)", currency=None):
    if not hasattr(st, "session_state"):
        return
    key = f"scheme_dashboard_context_{business_id}"
    summary = dict(st.session_state.get(key, {}))
    if currency:
        summary["currency"] = currency
    if analysis is not None:
        summary["analytics_scope"] = scope
        summary["kpis"] = metrics(analysis.get("kpis", {}))
        summary["monthly_trends"] = [{"period": row.get("period"), **metrics(row)}
                                     for row in analysis.get("trends", {}).get("monthly", [])[-12:]]
    if health is not None:
        summary["health_scope"] = scope
        summary["health_metrics"] = metrics(health.get("metrics", {}))
        anomalies = health.get("anomalies", [])
        summary["anomaly_count"] = len(anomalies)
        summary["anomalies_by_type"] = dict(Counter(str(a.get("type", "Unknown")) for a in anomalies))
        summary["anomalies_by_severity"] = dict(Counter(str(a.get("severity", "Unknown")) for a in anomalies))
    if support is not None:
        summary["recommendations_scope"] = scope
        summary["recommendations"] = [{k: str(r.get(k, ""))[:500] for k in
            ("title", "priority", "explanation", "recommended_action")}
            for r in support.get("recommendations", [])[:15]]
    st.session_state[key] = summary
