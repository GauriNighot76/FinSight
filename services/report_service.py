"""Read-only reporting and export adapters for Modules 5 and 6."""

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from services import analytics_service, business_health_service, business_service


class ReportError(ValueError):
    """Safe error raised when a report cannot be produced."""


_REPORT_TYPE_ALIASES = {
    "executive": "combined_executive_report",
    "combined_executive": "combined_executive_report",
}
_REPORT_TYPES = frozenset(
    {
        "financial_summary",
        "income_statement",
        "expense_summary",
        "cash_flow_summary",
        "category_report",
        "payment_mode_report",
        "account_summary",
        "business_health_report",
        "anomaly_report",
        "combined_executive_report",
    }
)
_SECTION_ORDER = (
    "financial_summary",
    "income_statement",
    "expense_summary",
    "cash_flow_summary",
    "category_report",
    "payment_mode_report",
    "account_summary",
    "business_health_report",
    "anomaly_report",
)
_SENSITIVE_KEYS = frozenset(
    {
        "account_id",
        "business_id",
        "canonical_identity_hash",
        "identity_id",
        "path",
        "session_id",
        "session_token",
        "source_transaction_id",
        "sql",
        "stack_trace",
        "token",
        "transaction_id",
        "transaction_reference",
    }
)


def _validate_date_range(start_date: Any, end_date: Any) -> tuple[str, str]:
    if type(start_date) is not str or type(end_date) is not str:
        raise ReportError("The report date range is invalid.")
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError as error:
        raise ReportError("The report date range is invalid.") from error
    if start > end:
        raise ReportError("The report date range is invalid.")
    return start.isoformat(), end.isoformat()


def _timestamp(value: Any) -> str:
    if value is None:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if type(value) is str and value:
        return value
    raise ReportError("The report timestamp is invalid.")


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _sanitize(item)
            for key, item in value.items()
            if key not in _SENSITIVE_KEYS
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value


def _json_ready(value: Any) -> Any:
    value = _sanitize(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _safe_access(session_token: Any, business_id: Any) -> str:
    try:
        access = business_service.require_business_access(
            session_token,
            business_id,
            {"owner", "manager"},
        )
    except Exception as error:
        raise ReportError("The selected business is unavailable.") from error
    if not isinstance(access, dict) or access.get("success") is not True:
        raise ReportError("You do not have permission to view this report.")
    business = access.get("business")
    membership = access.get("membership")
    if (
        not isinstance(business, dict)
        or business.get("business_status") != "active"
        or not isinstance(membership, dict)
        or membership.get("membership_status") != "active"
        or membership.get("membership_role") not in {"owner", "manager"}
        or type(business.get("business_name")) is not str
    ):
        raise ReportError("You do not have permission to view this report.")
    return business["business_name"]


def _kpis(analytics: dict[str, Any]) -> dict[str, Any]:
    kpis = analytics.get("kpis")
    return kpis if isinstance(kpis, dict) else {}


def _financial_summary(kpis: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "total_income_minor",
        "total_expense_minor",
        "net_cash_flow_minor",
        "transaction_count",
        "average_transaction_minor",
        "largest_income_minor",
        "largest_expense_minor",
        "income_expense_ratio",
        "savings_rate",
        "opening_balance_minor",
        "closing_balance_minor",
    )
    return {field: kpis.get(field) for field in fields}


def _income_statement(kpis: dict[str, Any]) -> dict[str, Any]:
    return {
        "income_minor": kpis.get("total_income_minor", 0),
        "expense_minor": kpis.get("total_expense_minor", 0),
        "net_cash_flow_minor": kpis.get("net_cash_flow_minor", 0),
        "savings_rate": kpis.get("savings_rate"),
    }


def _expense_summary(kpis: dict[str, Any]) -> dict[str, Any]:
    return {
        "total_expense_minor": kpis.get("total_expense_minor", 0),
        "income_expense_ratio": kpis.get("income_expense_ratio"),
        "largest_expense_minor": kpis.get("largest_expense_minor"),
        "smallest_expense_minor": kpis.get("smallest_expense_minor"),
    }


def _cash_flow_summary(
    analytics: dict[str, Any], kpis: dict[str, Any]
) -> dict[str, Any]:
    trends = analytics.get("trends")
    if not isinstance(trends, dict):
        trends = {"daily": [], "weekly": [], "monthly": []}
    return {
        "opening_balance_minor": kpis.get("opening_balance_minor"),
        "closing_balance_minor": kpis.get("closing_balance_minor"),
        "net_cash_flow_minor": kpis.get("net_cash_flow_minor", 0),
        "trends": trends,
    }


def _list_section(analytics: dict[str, Any], name: str) -> list[Any]:
    value = analytics.get(name)
    return value if isinstance(value, list) else []


def _build_sections(
    analytics: dict[str, Any], health: dict[str, Any]
) -> dict[str, Any]:
    kpis = _kpis(analytics)
    health_metrics = health.get("metrics")
    anomalies = health.get("anomalies")
    sections = {
        "financial_summary": _financial_summary(kpis),
        "income_statement": _income_statement(kpis),
        "expense_summary": _expense_summary(kpis),
        "cash_flow_summary": _cash_flow_summary(analytics, kpis),
        "category_report": _list_section(analytics, "categories"),
        "payment_mode_report": _list_section(analytics, "payment_modes"),
        "account_summary": _list_section(analytics, "accounts"),
        "business_health_report": (
            health_metrics if isinstance(health_metrics, dict) else {}
        ),
        "anomaly_report": anomalies if isinstance(anomalies, list) else [],
    }
    return _sanitize(sections)


def build_report(
    *,
    session_token: str,
    business_id: str,
    account_id: str,
    start_date: str,
    end_date: str,
    currency: str,
    report_type: str = "combined_executive_report",
    generated_at: Any = None,
) -> dict[str, Any]:
    """Build a read-only report from the existing analytics and health services."""
    start_date, end_date = _validate_date_range(start_date, end_date)
    if type(currency) is not str or len(currency) != 3 or currency != currency.upper():
        raise ReportError("The report currency is invalid.")
    if type(report_type) is not str:
        raise ReportError("The requested report type is invalid.")
    report_type = _REPORT_TYPE_ALIASES.get(report_type, report_type)
    if report_type not in _REPORT_TYPES:
        raise ReportError("The requested report type is invalid.")

    business_name = _safe_access(session_token, business_id)
    service_args = {
        "session_token": session_token,
        "business_id": business_id,
        "account_id": account_id,
        "start_date": start_date,
        "end_date": end_date,
        "currency": currency,
    }
    try:
        analytics = analytics_service.get_financial_analytics(**service_args)
    except analytics_service.AnalyticsError as error:
        raise ReportError("The report data could not be loaded.") from error
    except Exception as error:
        raise ReportError("The report data could not be loaded.") from error
    try:
        health = business_health_service.get_business_health(**service_args)
    except business_health_service.BusinessHealthError as error:
        raise ReportError("The business health report could not be loaded.") from error
    except Exception as error:
        raise ReportError("The business health report could not be loaded.") from error
    if not isinstance(analytics, dict) or not isinstance(health, dict):
        raise ReportError("The report data could not be loaded.")

    sections = _build_sections(analytics, health)
    report = {
        "report_type": report_type,
        "business": {"name": business_name},
        "date_range": {"start_date": start_date, "end_date": end_date},
        "currency": currency,
        "generated_at": _timestamp(generated_at),
        "sections": sections,
    }
    report[report_type] = sections.get(report_type, sections)
    if report_type == "combined_executive_report":
        report["combined_executive_report"] = sections
    return report


def report_to_json(report: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-serializable, sanitized report dictionary."""
    if not isinstance(report, dict):
        raise ReportError("The report result is invalid.")
    return _json_ready(report)


def report_to_csv_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten report sections into deterministic CSV-ready rows."""
    safe_report = report_to_json(report)
    sections = safe_report.get("sections")
    if not isinstance(sections, dict):
        return []
    rows: list[dict[str, Any]] = []
    for section_name in _SECTION_ORDER:
        value = sections.get(section_name)
        if isinstance(value, dict):
            for field in sorted(value):
                field_value = value[field]
                if isinstance(field_value, (dict, list)):
                    field_value = json.dumps(field_value, sort_keys=True)
                rows.append(
                    {
                        "section": section_name,
                        "field": field,
                        "value": field_value,
                    }
                )
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, dict):
                    row = {"section": section_name, "row": index}
                    row.update({key: item[key] for key in sorted(item)})
                else:
                    row = {"section": section_name, "row": index, "value": item}
                rows.append(row)
    return rows


def report_to_table_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Return rows suitable for tabular presentation."""
    return report_to_csv_rows(report)


def report_to_chart_datasets(report: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Return backend trend datasets without adding presentation logic."""
    try:
        trends = report["sections"]["cash_flow_summary"]["trends"]
    except (KeyError, TypeError):
        trends = {}
    return {
        name: (
            _json_ready(trends.get(name))
            if isinstance(trends, dict) and isinstance(trends.get(name), list)
            else []
        )
        for name in ("daily", "weekly", "monthly")
    }


generate_report = build_report
create_report = build_report
to_json_ready = report_to_json


__all__ = [
    "ReportError",
    "build_report",
    "create_report",
    "generate_report",
    "report_to_chart_datasets",
    "report_to_csv_rows",
    "report_to_json",
    "report_to_table_rows",
    "to_json_ready",
]
