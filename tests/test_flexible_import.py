import pytest

from services.flexible_import import (
    FlexibleImportError,
    analyze_upload,
    normalize_analysis,
    normalize_analysis_batches,
)


def test_unfamiliar_csv_headers_are_detected_from_names_and_values():
    analysis = analyze_upload(
        b"When,What,How Much,Flow\n05/09/2026,Medicine,125.50,debit\n06/09/2026,Sale,500,income\n",
        "custom-export.csv",
    )
    assert analysis.mapping["transaction_date"] == "When"
    assert analysis.mapping["amount"] == "How Much"
    assert analysis.mapping["direction"] == "Flow"
    payload = normalize_analysis(analysis, analysis.mapping)
    assert payload["records"][0]["amount_minor"] == 12550
    assert payload["records"][0]["direction"] == "expense"


def test_xml_records_and_camel_case_fields_are_supported():
    analysis = analyze_upload(
        b"<transactions><transaction><postedOn>2026-09-05</postedOn><narration>Rent</narration><moneyOut>1000.00</moneyOut><referenceNumber>R1</referenceNumber></transaction></transactions>",
        "statement.xml",
    )
    payload = normalize_analysis(analysis, analysis.mapping)
    assert analysis.file_type == "XML"
    assert payload["records"][0]["transaction_date"] == "2026-09-05"
    assert payload["records"][0]["direction"] == "expense"
    assert payload["records"][0]["source_transaction_id"] == "R1"


def test_manual_mapping_can_resolve_unknown_headers():
    analysis = analyze_upload(
        b"Col A,Col B,Col C\n2026-09-05,-10.25,unused\n",
        "unknown.csv",
    )
    mapping = {field: None for field in analysis.mapping}
    mapping.update(transaction_date="Col A", amount="Col B")
    payload = normalize_analysis(analysis, mapping)
    assert payload["records"][0]["amount_minor"] == 1025


def test_xml_entities_are_rejected():
    with pytest.raises(FlexibleImportError, match="entities"):
        analyze_upload(
            b'<!DOCTYPE x [<!ENTITY secret "value">]><rows><row><Date>2026-09-05</Date><Amount>&secret;</Amount></row></rows>',
            "unsafe.xml",
        )


def test_large_file_is_split_into_backend_sized_batches():
    rows = "".join(f"2026-09-05,Sale {index},1.00,income\n" for index in range(2000))
    analysis = analyze_upload(
        ("Date,Description,Amount,Direction\n" + rows).encode(),
        "large.csv",
    )
    batches = normalize_analysis_batches(analysis, analysis.mapping)
    assert [len(batch["records"]) for batch in batches] == [1000, 1000]
