import json

from services import ingestion_service


class UploadedJson:
    def __init__(self, value):
        self._value = value

    def getvalue(self):
        return self._value


class UploadedCsv:
    def __init__(self, value, name="statement.csv"):
        self._value = value
        self.name = name
        self.type = "text/csv"

    def getvalue(self):
        return self._value


class FakeStreamlit:
    def __init__(self, *, uploaded=None, button_values=None):
        self.uploaded = uploaded
        self.button_values = button_values or {}
        self.session_state = {}
        self.events = []

    def _event(self, name, *values):
        self.events.append((name, *values))

    def header(self, value):
        self._event("header", value)

    def subheader(self, value):
        self._event("subheader", value)

    def caption(self, value):
        self._event("caption", value)

    def info(self, value):
        self._event("info", value)

    def warning(self, value):
        self._event("warning", value)

    def error(self, value):
        self._event("error", value)

    def success(self, value):
        self._event("success", value)

    def metric(self, label, value):
        self._event("metric", label, value)

    def selectbox(self, label, options, format_func=None):
        self._event("selectbox", label, tuple(options))
        return options[0] if options else None

    def file_uploader(self, label, **kwargs):
        self._event("file_uploader", label, kwargs)
        return self.uploaded

    def button(self, label, **kwargs):
        self._event("button", label)
        return self.button_values.get(label, False)


def _authorized_context(monkeypatch, role="owner"):
    from finsight_app import ingestion_ui

    monkeypatch.setattr(
        ingestion_ui.auth_service,
        "validate_session",
        lambda token: {
            "success": True,
            "user": {"user_id": "uploader-1", "role": "standard_business"},
        },
    )
    monkeypatch.setattr(
        ingestion_ui.business_service,
        "list_user_businesses",
        lambda token: {
            "success": True,
            "businesses": [
                {
                    "business_id": "business-1",
                    "business_name": "Controlled Demo",
                    "business_status": "active",
                    "membership": {
                        "membership_role": role,
                        "membership_status": "active",
                    },
                }
            ],
        },
    )
    monkeypatch.setattr(
        ingestion_ui.account_service,
        "list_business_accounts",
        lambda token, business_id: {
            "success": True,
            "accounts": [
                {
                    "account_id": "account-1",
                    "account_name": "Demo Account",
                    "currency": "INR",
                    "account_status": "active",
                }
            ],
        },
    )
    monkeypatch.setattr(
        ingestion_ui.bridge_service,
        "bridge_status",
        lambda token, business_id: {"success": True, "status": "active"},
    )
    return ingestion_ui


def _payload():
    return {
        "contract_version": "finsight_ingestion_v1",
        "source_system": "finsight_demo_bank_statement_v1",
        "records": [
            {
                "transaction_date": "2026-08-31",
                "amount_minor": 1234,
                "direction": "income",
            }
        ],
    }


def _events_text(ui):
    return repr(ui.events)


def test_unauthenticated_user_cannot_reach_upload_controls(monkeypatch):
    from finsight_app import ingestion_ui

    monkeypatch.setattr(
        ingestion_ui.auth_service,
        "validate_session",
        lambda token: {"success": False, "error": "SESSION_INVALID"},
    )
    ui = FakeStreamlit()

    assert ingestion_ui.render_ingestion_page(ui, "invalid-session") is False
    assert not any(event[0] == "file_uploader" for event in ui.events)
    assert "invalid-session" not in _events_text(ui)


def test_owner_can_select_business_account_and_submit_canonical_json(monkeypatch):
    ingestion_ui = _authorized_context(monkeypatch, "owner")
    captured = {}

    def ingest(**kwargs):
        captured.update(kwargs)
        return ingestion_service.IngestionWriteResult(
            status="completed",
            attempt_id="internal-attempt-id",
            record_count=1,
            inserted_count=1,
            duplicate_count=0,
            rejected_count=0,
            retry_count=0,
        )

    monkeypatch.setattr(ingestion_ui.ingestion_service, "ingest", ingest)
    ui = FakeStreamlit(
        uploaded=UploadedJson(json.dumps(_payload()).encode("utf-8")),
        button_values={"Ingest transactions": True},
    )

    assert ingestion_ui.render_ingestion_page(ui, "session-token") is True
    assert captured["session_token"] == "session-token"
    assert captured["business_id"] == "business-1"
    assert captured["account_id"] == "account-1"
    assert captured["payload"] == _payload()
    assert captured["record_failure"] is True
    rendered = _events_text(ui)
    assert "internal-attempt-id" not in rendered
    assert "session-token" not in rendered
    assert "1234" not in rendered
    assert any(event[:2] == ("metric", "Inserted") for event in ui.events)


def test_manager_can_use_the_same_ingestion_surface(monkeypatch):
    ingestion_ui = _authorized_context(monkeypatch, "manager")
    monkeypatch.setattr(
        ingestion_ui.ingestion_service,
        "ingest",
        lambda **kwargs: ingestion_service.IngestionWriteResult(
            status="completed",
            attempt_id="manager-attempt",
            record_count=1,
            inserted_count=0,
            duplicate_count=1,
            rejected_count=0,
        ),
    )
    ui = FakeStreamlit(
        uploaded=UploadedJson(json.dumps(_payload()).encode()),
        button_values={"Ingest transactions": True},
    )

    assert ingestion_ui.render_ingestion_page(ui, "manager-session") is True
    assert any(event[:2] == ("metric", "Duplicates") for event in ui.events)


def test_member_business_is_not_presented_as_an_ingestion_target(monkeypatch):
    ingestion_ui = _authorized_context(monkeypatch, "member")
    ui = FakeStreamlit()

    assert ingestion_ui.render_ingestion_page(ui, "member-session") is False
    assert not any(event[0] == "file_uploader" for event in ui.events)
    assert not any(event[0] == "selectbox" for event in ui.events)


def test_viewer_business_is_not_presented_as_an_ingestion_target(monkeypatch):
    ingestion_ui = _authorized_context(monkeypatch, "viewer")
    ui = FakeStreamlit()

    assert ingestion_ui.render_ingestion_page(ui, "viewer-session") is False
    assert not any(event[0] == "file_uploader" for event in ui.events)


def test_inactive_business_membership_is_not_presented_as_an_ingestion_target(monkeypatch):
    ingestion_ui = _authorized_context(monkeypatch, "owner")
    original = ingestion_ui.business_service.list_user_businesses

    def disabled_membership(token):
        result = original(token)
        result["businesses"][0]["membership"]["membership_status"] = "disabled"
        return result

    monkeypatch.setattr(ingestion_ui.business_service, "list_user_businesses", disabled_membership)
    ui = FakeStreamlit()

    assert ingestion_ui.render_ingestion_page(ui, "disabled-session") is False
    assert not any(event[0] == "file_uploader" for event in ui.events)


def test_malformed_uploaded_json_has_a_safe_error(monkeypatch):
    ingestion_ui = _authorized_context(monkeypatch)
    ui = FakeStreamlit(
        uploaded=UploadedJson(b"{not-json"),
        button_values={"Ingest transactions": True},
    )

    assert ingestion_ui.render_ingestion_page(ui, "session-token") is False
    rendered = _events_text(ui)
    assert "could not be read" in rendered
    assert "Traceback" not in rendered
    assert "not-json" not in rendered


def test_rejected_and_duplicate_counts_are_displayed_without_internal_ids(monkeypatch):
    ingestion_ui = _authorized_context(monkeypatch)
    monkeypatch.setattr(
        ingestion_ui.ingestion_service,
        "ingest",
        lambda **kwargs: ingestion_service.IngestionWriteResult(
            status="completed",
            attempt_id="attempt-secret",
            record_count=3,
            inserted_count=1,
            duplicate_count=2,
            rejected_count=0,
            retry_count=1,
        ),
    )
    ui = FakeStreamlit(
        uploaded=UploadedJson(json.dumps(_payload()).encode()),
        button_values={"Ingest transactions": True},
    )

    ingestion_ui.render_ingestion_page(ui, "session-token")
    rendered = _events_text(ui)
    assert "Inserted" in rendered
    assert "Duplicates" in rendered
    assert "Rejected" in rendered
    assert "Retry count" in rendered
    assert "attempt-secret" not in rendered


def test_conflict_is_rendered_as_a_fixed_safe_message(monkeypatch):
    ingestion_ui = _authorized_context(monkeypatch)

    def conflict(**kwargs):
        raise ingestion_service.IngestionServiceError("IDENTITY_CONFLICT")

    monkeypatch.setattr(ingestion_ui.ingestion_service, "ingest", conflict)
    ui = FakeStreamlit(
        uploaded=UploadedJson(json.dumps(_payload()).encode()),
        button_values={"Ingest transactions": True},
    )

    assert ingestion_ui.render_ingestion_page(ui, "session-token") is False
    rendered = _events_text(ui)
    assert "conflicting transaction identity" in rendered
    assert "IDENTITY_CONFLICT" not in rendered
    assert "session-token" not in rendered


def test_backend_validation_error_is_rendered_safely(monkeypatch):
    ingestion_ui = _authorized_context(monkeypatch)

    def invalid_payload(**kwargs):
        raise ingestion_service.IngestionServiceError("VALIDATION_FAILED")

    monkeypatch.setattr(ingestion_ui.ingestion_service, "ingest", invalid_payload)
    ui = FakeStreamlit(
        uploaded=UploadedJson(json.dumps(_payload()).encode()),
        button_values={"Ingest transactions": True},
    )

    assert ingestion_ui.render_ingestion_page(ui, "session-token") is False
    rendered = _events_text(ui)
    assert "ingestion payload is invalid" in rendered
    assert "VALIDATION_FAILED" not in rendered
    assert "session-token" not in rendered


def test_unexpected_service_error_never_leaks_raw_details(monkeypatch):
    ingestion_ui = _authorized_context(monkeypatch)
    monkeypatch.setattr(
        ingestion_ui.ingestion_service,
        "ingest",
        lambda **kwargs: (_ for _ in ()).throw(
            RuntimeError("SQL / secret path / raw payload")
        ),
    )
    ui = FakeStreamlit(
        uploaded=UploadedJson(json.dumps(_payload()).encode()),
        button_values={"Ingest transactions": True},
    )

    assert ingestion_ui.render_ingestion_page(ui, "session-token") is False
    rendered = _events_text(ui)
    assert "could not be completed" in rendered
    assert "SQL" not in rendered
    assert "secret path" not in rendered
    assert "raw payload" not in rendered


def test_upload_widget_accepts_canonical_json_and_csv(monkeypatch):
    ingestion_ui = _authorized_context(monkeypatch)
    ui = FakeStreamlit()

    ingestion_ui.render_ingestion_page(ui, "session-token")
    uploader = next(event for event in ui.events if event[0] == "file_uploader")
    assert uploader[2]["type"] == ["json", "csv", "xml"]


def test_no_database_or_service_call_occurs_before_submit(monkeypatch):
    ingestion_ui = _authorized_context(monkeypatch)
    calls = []
    monkeypatch.setattr(
        ingestion_ui.ingestion_service,
        "ingest",
        lambda **kwargs: calls.append(kwargs),
    )
    ui = FakeStreamlit(uploaded=UploadedJson(json.dumps(_payload()).encode()))

    ingestion_ui.render_ingestion_page(ui, "session-token")
    assert calls == []


def test_owner_can_submit_csv_through_the_existing_ingestion_service(monkeypatch):
    ingestion_ui = _authorized_context(monkeypatch)
    captured = []

    def ingest(**kwargs):
        captured.append(kwargs)
        return ingestion_service.IngestionWriteResult(
            status="completed",
            attempt_id="csv-attempt",
            record_count=1,
            inserted_count=1,
            duplicate_count=0,
            rejected_count=0,
        )

    monkeypatch.setattr(ingestion_ui.ingestion_service, "ingest", ingest)
    ui = FakeStreamlit(
        uploaded=UploadedCsv(
            b"Date,Description,Amount,Direction\n"
            b"2026-08-01,Sale,10.00,income\n"
        ),
        button_values={"Ingest transactions": True},
    )

    assert ingestion_ui.render_ingestion_page(ui, "session-token") is True
    assert len(captured) == 1
    assert captured[0]["payload"]["records"][0] == {
        "transaction_date": "2026-08-01",
        "amount_minor": 1000,
        "direction": "income",
        "description": "Sale",
    }


def test_csv_normalization_and_ingestion_are_each_called_once(monkeypatch):
    from services import csv_normalizer

    ingestion_ui = _authorized_context(monkeypatch)
    normalization_calls = []
    ingestion_calls = []
    original_normalize = csv_normalizer.normalize_csv

    def normalize_once(uploaded_file):
        normalization_calls.append(uploaded_file)
        return original_normalize(uploaded_file)

    monkeypatch.setattr(ingestion_ui, "csv_normalizer", csv_normalizer, raising=False)
    monkeypatch.setattr(csv_normalizer, "normalize_csv", normalize_once)
    monkeypatch.setattr(
        ingestion_ui.ingestion_service,
        "ingest",
        lambda **kwargs: ingestion_calls.append(kwargs)
        or ingestion_service.IngestionWriteResult(
            status="completed",
            attempt_id="csv-attempt",
            record_count=1,
            inserted_count=1,
            duplicate_count=0,
            rejected_count=0,
        ),
    )
    ui = FakeStreamlit(
        uploaded=UploadedCsv(
            b"Date;Narration;Amount;Type\n"
            b"2026-08-01;Sale;10.00;income\n"
        ),
        button_values={"Ingest transactions": True},
    )

    assert ingestion_ui.render_ingestion_page(ui, "session-token") is True
    assert len(normalization_calls) == 1
    assert len(ingestion_calls) == 1


def test_malformed_csv_has_a_sanitized_error_and_no_ingestion(monkeypatch):
    ingestion_ui = _authorized_context(monkeypatch)
    ingestion_calls = []
    monkeypatch.setattr(
        ingestion_ui.ingestion_service,
        "ingest",
        lambda **kwargs: ingestion_calls.append(kwargs),
    )
    ui = FakeStreamlit(
        uploaded=UploadedCsv(
            b"Date,Amount,Direction\n2026-08-01,\"unterminated,income\n"
        ),
        button_values={"Ingest transactions": True},
    )

    assert ingestion_ui.render_ingestion_page(ui, "session-token") is False
    rendered = _events_text(ui)
    assert "CSV" in rendered
    assert "malformed" in rendered
    assert "unterminated" not in rendered
    assert ingestion_calls == []


def test_csv_counts_and_warnings_are_displayed_without_internal_values(monkeypatch):
    ingestion_ui = _authorized_context(monkeypatch)
    monkeypatch.setattr(
        ingestion_ui.ingestion_service,
        "ingest",
        lambda **kwargs: ingestion_service.IngestionWriteResult(
            status="completed",
            attempt_id="internal-csv-attempt",
            record_count=4,
            inserted_count=2,
            duplicate_count=1,
            rejected_count=1,
        ),
    )
    ui = FakeStreamlit(
        uploaded=UploadedCsv(
            b"Date,Amount,Direction\n2026-08-01,10.00,income\n"
        ),
        button_values={"Ingest transactions": True},
    )

    ingestion_ui.render_ingestion_page(ui, "session-token")
    rendered = _events_text(ui)
    assert "Rows detected" in rendered
    assert "Rows accepted" in rendered
    assert "Duplicates" in rendered
    assert "Rows rejected" in rendered
    assert "internal-csv-attempt" not in rendered
