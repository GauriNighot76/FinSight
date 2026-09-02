import pytest


@pytest.mark.parametrize("membership_role", ["member", "viewer"])
def test_analytics_rejects_non_management_membership_before_reads(
    monkeypatch, membership_role
):
    from services import analytics_service

    monkeypatch.setattr(
        analytics_service.auth_service,
        "validate_session",
        lambda token: {"success": True, "user": {"user_id": "user-1"}},
    )
    monkeypatch.setattr(
        analytics_service.queries,
        "get_business_membership",
        lambda business_id, user_id: {
            "business_status": "active",
            "membership_status": "active",
            "membership_role": membership_role,
        },
    )
    monkeypatch.setattr(
        analytics_service,
        "_load_account",
        lambda *args, **kwargs: pytest.fail("analytics read occurred before authorization"),
    )

    with pytest.raises(analytics_service.AnalyticsError, match="business"):
        analytics_service.get_financial_analytics(
            session_token="session-token",
            business_id="business-1",
            account_id="account-1",
            start_date="2026-01-01",
            end_date="2026-01-31",
            currency="INR",
        )


def test_analytics_rejects_malformed_successful_session_without_raw_exception(
    monkeypatch,
):
    from services import analytics_service

    monkeypatch.setattr(
        analytics_service.auth_service,
        "validate_session",
        lambda token: {"success": True},
    )

    with pytest.raises(
        analytics_service.AnalyticsError, match="(?i)authentication"
    ):
        analytics_service.get_financial_analytics(
            session_token="session-token",
            business_id="business-1",
            account_id="account-1",
            start_date="2026-01-01",
            end_date="2026-01-31",
            currency="INR",
        )


def test_analytics_rejects_malformed_membership_without_raw_exception(monkeypatch):
    from services import analytics_service

    monkeypatch.setattr(
        analytics_service.auth_service,
        "validate_session",
        lambda token: {"success": True, "user": {"user_id": "user-1"}},
    )
    monkeypatch.setattr(
        analytics_service.queries,
        "get_business_membership",
        lambda business_id, user_id: {
            "business_status": "active",
            "membership_status": "active",
        },
    )

    with pytest.raises(analytics_service.AnalyticsError, match="(?i)business"):
        analytics_service.get_financial_analytics(
            session_token="session-token",
            business_id="business-1",
            account_id="account-1",
            start_date="2026-01-01",
            end_date="2026-01-31",
            currency="INR",
        )
