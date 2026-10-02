"""Ratios retain backend orientation and render through real Streamlit elements."""
from decimal import Decimal, ROUND_HALF_UP

import pytest
from streamlit.testing.v1 import AppTest

from finsight_app import workspace_ui
from finsight_app.metric_formatting import format_metric, present_report_rows
from services import business_health_service
from services.rag.dashboard_context import GUIDE
from test_module4_ingestion_service import ingestion_repository
from test_module5_analytics import ACCOUNT_ID, BUSINESS_ID, _analytics, _seed_accepted_transaction


@pytest.mark.parametrize('income,expense,ratio,burden,savings', [
    (14456450, 10000000, '1.45×', '0.69', '30.83%'),
    (14456450, 0, 'N/A', '0.00', '100.00%'),
    (0, 10000000, '0.00×', 'N/A', 'N/A'),
    (0, 0, 'N/A', 'N/A', 'N/A'),
])
def test_backend_and_streamlit_paths(ingestion_repository, monkeypatch,
                                     income, expense, ratio, burden, savings):
    with ingestion_repository() as connection:
        for direction, amount in [('income', income), ('expense', expense)]:
            if amount:
                _seed_accepted_transaction(connection, direction,
                                           amount_minor=amount, direction=direction)
    analysis = _analytics()
    health = business_health_service.get_business_health(
        session_token='token-owner_user_001',
        business_id=BUSINESS_ID,
        account_id=ACCOUNT_ID,
        start_date='2026-01-01', end_date='2026-12-31', currency='INR')
    kpis = analysis['kpis']
    assert kpis['income_expense_ratio'] == (
        Decimal(income) / Decimal(expense) if expense else None)
    assert health['metrics']['expense_to_income_ratio'] == (
        (Decimal(expense) / Decimal(income)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        if income else None)
    assert format_metric(kpis['savings_rate'], suffix='%') == savings
    if income and expense:
        assert kpis['income_expense_ratio'] == Decimal('1.445645')
        assert kpis['savings_rate'] == Decimal('30.83')

    monkeypatch.setattr(workspace_ui, 'load_business_analytics',
                        lambda *a: ({'currency': 'INR'}, analysis))
    monkeypatch.setattr(workspace_ui, '_health_context', lambda *a: ({}, health))

    def app(analysis):
        import streamlit as st
        from finsight_app.analytics_ui import _render_analytics
        from finsight_app.workspace_ui import render_overview, render_business_health
        _render_analytics(st, analysis, 'INR')
        business = {'business_id': 'test', 'business_name': 'Ratio Regression'}
        render_overview(st, 'token', business)
        render_business_health(st, 'token', business)

    rendered = AppTest.from_function(app, args=(analysis,)).run()
    assert not rendered.exception
    metrics = [(m.label, m.value) for m in rendered.metric]
    assert ('Income-to-Expense Ratio', ratio) in metrics
    assert ('Savings Rate', savings) in metrics
    assert all(value == savings for label, value in metrics if label == 'Savings Rate')
    text = '\n'.join(x.value for x in [*rendered.caption, *rendered.markdown])
    if income or expense:
        assert f'Income-to-Expense Ratio: {ratio}' in text
        assert f'**Expense-to-Income Ratio:** {burden}' in text
    assert '1.445645' not in str(metrics) + text


@pytest.mark.parametrize('value', [None, Decimal('NaN'), Decimal('Infinity'), '-Infinity'])
def test_unavailable_metric_is_safe(value):
    assert format_metric(value, suffix='×') == 'N/A'


def test_pdf_csv_and_finny_labels(monkeypatch):
    from finsight_app.pdf_generator import generate_business_report
    from services import report_service
    from test_module7_reports import _analytics_result, _health_result, _authorized_context, _build
    analysis = _analytics_result()
    analysis['kpis'].update(income_expense_ratio=Decimal('1.44564509002540042781398431'),
                            savings_rate=Decimal('30.83'))
    health = _health_result()
    health['metrics']['expense_to_income_ratio'] = Decimal('.69')
    service, _ = _authorized_context(monkeypatch, analytics=analysis, health=health)
    report = _build(service)
    raw = report_service.report_to_csv_rows(report)
    displayed = present_report_rows(raw)
    assert any(r.get('field') == 'income_expense_ratio' for r in raw)
    for label, value in [('Income-to-Expense Ratio', '1.45×'),
                         ('Expense-to-Income Ratio', '0.69×'), ('Savings Rate', '30.83%')]:
        assert any(r.get('field') == label and r.get('value') == value for r in displayed)
    pdf = generate_business_report(business={'business_name': 'Ratio Regression'},
                                    report=report, decision_support={'recommendations': []},
                                    scheme_results=[]).getvalue()
    assert b'Income-to-Expense Ratio: 1.45' in pdf
    assert b'Expense-to-Income Ratio: 0.69' in pdf
    assert b'Savings Rate: 30.83%' in pdf
    assert b'1.445645' not in pdf
    assert 'income_expense_ratio and income_ratio mean Income-to-Expense Ratio (Income / Expense)' in GUIDE
    assert 'expense_to_income_ratio means Expense-to-Income Ratio (Expense / Income)' in GUIDE
    assert 'Do not calculate KPIs yourself' in GUIDE
