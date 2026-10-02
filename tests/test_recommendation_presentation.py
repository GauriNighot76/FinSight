"""Recommendation units, detector semantics and live Streamlit presentation."""
from copy import deepcopy
from decimal import Decimal

import pytest
from streamlit.testing.v1 import AppTest

from finsight_app import workspace_ui
from finsight_app.recommendation_presentation import format_minor, present_recommendation
from services import business_health_service as health_service
from test_module7_decision_support import _analytics, _health, _context, _support, _report


@pytest.mark.parametrize('value,expected', [
    (179980, '₹1,799.80'), (120024, '₹1,200.24'), (-42256, '−₹422.56'),
    (0, '₹0.00'), (None, 'N/A'), (Decimal('NaN'), 'N/A'),
])
def test_minor_unit_display(value, expected):
    assert format_minor(value) == expected


def anomaly(kind, value, threshold, **extra):
    return {'type': kind, 'metric_value': Decimal(str(value)),
            'threshold': Decimal(str(threshold)), 'severity': 'HIGH', **extra}


def test_currency_percentage_and_ratio_evidence_are_not_confused(monkeypatch):
    findings = [anomaly('unusually_large_income', 179980, 120024),
                anomaly('negative_cash_flow_period', -42256, 0),
                anomaly('recurring_expense_growth', 60, 50),
                anomaly('high_expense_ratio', '.16', '.75')]
    service, _ = _context(monkeypatch, health=_health(anomalies=findings))
    support = _support(service)
    before = deepcopy(support)
    cards = [present_recommendation(r) for r in support['recommendations']]
    texts = {c['supporting_metrics'].get('anomaly_type'): c['explanation'] for c in cards}
    assert '₹1,799.80' in texts['unusually_large_income']
    assert '₹1,200.24' in texts['unusually_large_income']
    assert '−₹422.56' in texts['negative_cash_flow_period']
    assert '50.00%' in texts['recurring_expense_growth']
    assert '₹' not in texts['recurring_expense_growth']
    assert '0.16' in texts['high_expense_ratio']
    assert '₹' not in texts['high_expense_ratio']
    assert support == before


@pytest.mark.parametrize('burden,triggered', [('49.99', False), ('50.00', False), ('50.01', True)])
def test_strict_burden_boundary_and_measured_anomaly(monkeypatch, burden, triggered):
    metrics = _health(metrics={'recurring_expense_burden': Decimal(burden)})['metrics']
    findings = health_service._detect_period_anomalies(_analytics(), metrics)
    burden_findings = [a for a in findings if a['type'] == 'very_high_recurring_expenses']
    assert bool(burden_findings) is triggered
    if triggered:
        assert burden_findings[0]['metric_value'] == Decimal(burden)
        assert burden_findings[0]['threshold'] == Decimal('50.00')
    service, _ = _context(monkeypatch, health=_health(metrics=metrics, anomalies=findings))
    cards = _support(service)['recommendations']
    burden_cards = [c for c in cards if c['title'] == 'High recurring-category burden']
    assert len(burden_cards) == int(triggered)
    if triggered:
        assert f'{burden}% of recorded expenses' in burden_cards[0]['explanation']
        assert len(burden_cards[0]['supporting_metrics']['related_anomalies']) == 1


def test_monthly_categories_not_subscriptions_and_growth_is_retained(monkeypatch):
    transactions = [
        {'direction': 'expense', 'category': 'Stock', 'transaction_date': '2026-01-01', 'amount_minor': 10000},
        {'direction': 'expense', 'category': 'Stock', 'transaction_date': '2026-02-01', 'amount_minor': 20000},
    ]
    burden = health_service._recurring_expense_burden(transactions, 30000)
    assert burden == Decimal('100.00')
    same_month = deepcopy(transactions)
    same_month[1]['transaction_date'] = '2026-01-02'
    assert health_service._recurring_expense_burden(same_month, 30000) == 0
    analysis = _analytics()
    analysis['transactions'] = transactions
    metrics = _health(metrics={'recurring_expense_burden': burden})['metrics']
    findings = health_service._detect_period_anomalies(analysis, metrics)
    findings = health_service._finalize_anomalies(findings, business_id='b', account_id='a')
    before = deepcopy(findings)
    service, _ = _context(monkeypatch, analytics=analysis, health=_health(metrics=metrics, anomalies=findings))
    cards = _support(service)['recommendations']
    assert findings == before
    burden_cards = [c for c in cards if c['title'] == 'High recurring-category burden']
    assert len(burden_cards) == 1
    assert any('Recurring-category spending increased sharply' in c['title'] for c in cards)
    evidence = burden_cards[0]['supporting_metrics']['related_anomalies'][0]
    assert evidence['metric_value'] == '100.00'
    assert evidence['threshold'] == '50.00'
    assert evidence['anomaly_id']
    for c in cards:
        if 'recurring' in c['title'].lower():
            text = str(present_recommendation(c)).lower()
            assert 'subscription' not in text
            assert 'fixed costs' not in text
    assert _support(service)['recommendations'] == cards


def test_distinct_category_growth_cards_survive(monkeypatch):
    findings = [anomaly('recurring_expense_growth', 80, 50,
                        affected_period='2026-02', detection_context={'category': category})
                for category in ['Stock', 'Rent']]
    service, _ = _context(monkeypatch, health=_health(anomalies=findings))
    cards = [c for c in _support(service)['recommendations']
             if c['supporting_metrics'].get('anomaly_type') == 'recurring_expense_growth']
    assert len(cards) == 2
    assert len({c['title'] for c in cards}) == 2


def test_visible_health_score_stays_85():
    metrics = _health(metrics={
        'expense_to_income_ratio': Decimal('.16'), 'savings_rate': Decimal('84'),
        'cash_flow_stability': Decimal('93.09'), 'category_concentration': Decimal('19.24'),
        'recurring_expense_burden': Decimal('100'), 'monthly_decline': Decimal('0'),
    })['metrics']
    assert health_service._health_score(metrics) == (85, 'Excellent')


def test_real_recommendation_rendering_and_finny_context(monkeypatch):
    findings = [anomaly('unusually_large_income', 179980, 120024),
                anomaly('negative_cash_flow_period', -42256, 0)]
    health = _health(metrics={'cash_reserve_estimate_minor': 179980}, anomalies=findings)
    service, _ = _context(monkeypatch, analytics=_analytics(income=1000000, expense=200000), health=health)
    support = _support(service)
    monkeypatch.setattr(workspace_ui, '_health_context', lambda *a: ({'currency': 'INR'}, health))
    monkeypatch.setattr(service, 'get_decision_support', lambda **k: support)

    def app():
        import streamlit as st
        from finsight_app.workspace_ui import render_recommendations
        render_recommendations(st, 'token', {'business_id': 'b'})

    rendered = AppTest.from_function(app).run()
    assert not rendered.exception
    text = '\n'.join(e.value for e in rendered.markdown)
    assert '₹1,799.80' in text and '₹1,200.24' in text and '−₹422.56' in text
    assert 'Cash reserve: ₹1,799.80' in text
    assert 'Expense threshold: ₹2,000.00' in text
    assert 'minor units' not in text
    assert '179980' not in text and '-42256' not in text
    context = rendered.session_state['scheme_dashboard_context_b']
    assert '₹1,799.80' in str(context['recommendations'])
    assert 'minor units' not in str(context['recommendations'])


def test_pdf_consumes_presented_recommendations(monkeypatch):
    from finsight_app import pdf_generator
    service, _ = _context(monkeypatch, health=_health(anomalies=[
        anomaly('unusually_large_income', 179980, 120024)]))
    support = _support(service)
    original = pdf_generator.report_service.build_advisory_model
    seen = []
    def capture(report, recommendations):
        seen.extend(recommendations)
        return original(report, recommendations)
    monkeypatch.setattr(pdf_generator.report_service, 'build_advisory_model', capture)
    pdf = pdf_generator.generate_business_report(business={'business_name': 'Test'},
                                                 report=_report(), decision_support=support)
    assert pdf.getvalue().startswith(b'%PDF')
    assert any('₹1,799.80' in c['explanation'] for c in seen)
    assert all('179980' not in c['explanation'] for c in seen)


def test_anomaly_only_burden_is_not_hidden_and_merge_preserves_priority(monkeypatch):
    finding = anomaly('very_high_recurring_expenses', 100, 50, severity='CRITICAL')
    service, _ = _context(monkeypatch, health=_health(anomalies=[finding]))
    cards = _support(service)['recommendations']
    assert sum(c['title'] == 'High recurring-category burden' for c in cards) == 1
    service, _ = _context(monkeypatch, health=_health(
        metrics={'recurring_expense_burden': Decimal('100')}, anomalies=[finding]))
    cards = _support(service)['recommendations']
    merged = [c for c in cards if c['title'] == 'High recurring-category burden']
    assert len(merged) == 1
    assert merged[0]['priority'] == 'CRITICAL'
    assert merged[0]['supporting_metrics']['related_anomalies'][0]['metric_value'] == '100'
