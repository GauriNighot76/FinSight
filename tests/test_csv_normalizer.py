from decimal import Decimal

import pytest


CONTRACT_VERSION = "finsight_ingestion_v1"
SOURCE_SYSTEM = "finsight_demo_bank_statement_v1"


def normalize(csv_data):
    from services.csv_normalizer import normalize_csv

    return normalize_csv(csv_data)


def test_common_bank_headers_produce_canonical_payload():
    payload = normalize(
        "Date,Description,Amount,Type,Category,Payment Mode\n"
        "01-08-2026,Daily sale,\"1,234.50\",Income,Sales,UPI\n"
    )

    assert payload == {
        "contract_version": CONTRACT_VERSION,
        "source_system": SOURCE_SYSTEM,
        "records": [
            {
                "transaction_date": "2026-08-01",
                "amount_minor": 123450,
                "direction": "income",
                "category": "Sales",
                "description": "Daily sale",
                "payment_method": "UPI",
            }
        ],
    }


def test_alias_headers_and_mixed_order_are_supported():
    payload = normalize(
        "Remarks,Txn Date,Withdrawal,Running Balance,Method\n"
        "Coffee,2026/08/02,₹80,\"9,920.00\",UPI\n"
    )

    record = payload["records"][0]
    assert record["transaction_date"] == "2026-08-02"
    assert record["amount_minor"] == 8000
    assert record["direction"] == "expense"
    assert record["description"] == "Coffee"
    assert record["balance_after_minor"] == 992000
    assert record["payment_method"] == "UPI"


def test_debit_credit_columns_map_direction_and_amount():
    payload = normalize(
        "Posting Date,Narration,Debit,Credit,Ledger Balance\n"
        "15/08/2026,Purchase,\"1,000.00\",,\"8,000.00\"\n"
        "16/08/2026,Refund,,250.50,\"8,250.50\"\n"
    )

    assert payload["records"] == [
        {
            "transaction_date": "2026-08-15",
            "amount_minor": 100000,
            "direction": "expense",
            "description": "Purchase",
            "balance_after_minor": 800000,
        },
        {
            "transaction_date": "2026-08-16",
            "amount_minor": 25050,
            "direction": "income",
            "description": "Refund",
            "balance_after_minor": 825050,
        },
    ]


def test_single_signed_amount_derives_direction():
    payload = normalize(
        "Transaction Date,Memo,Transaction Amount\n"
        "2026-08-01,Income,+500.00\n"
        "2026-08-02,Expense,-80.25\n"
    )

    assert [record["direction"] for record in payload["records"]] == [
        "income",
        "expense",
    ]
    assert [record["amount_minor"] for record in payload["records"]] == [
        50000,
        8025,
    ]


def test_direction_values_are_normalized_without_using_category_as_authority():
    payload = normalize(
        "Value Date,Details,Value,Direction,Expense Type\n"
        "2026-08-01,Sale,100,credit,Medical\n"
        "2026-08-02,Medicine,25,debit,Medical\n"
    )

    assert payload["records"][0]["direction"] == "income"
    assert payload["records"][1]["direction"] == "expense"
    assert payload["records"][0]["category"] == "Medical"
    assert payload["records"][1]["category"] == "Medical"


def test_optional_columns_can_be_missing_and_extra_columns_are_ignored():
    payload = normalize(
        "Date,Amount,Source Ref,Unused Column\n"
        "2026-08-01,-10.00,bank-1,ignored\n"
    )

    assert payload["records"] == [
        {
            "transaction_date": "2026-08-01",
            "amount_minor": 1000,
            "direction": "expense",
            "source_transaction_id": "bank-1",
        }
    ]


def test_whitespace_case_and_duplicate_spaces_are_cleaned():
    payload = normalize(
        "  DATE  ,  TRANSACTION   DETAILS ,  AMOUNT  ,  TYPE  \n"
        " 2026-08-01 ,  Rent   payment  ,  \"₹ 1,200.00\" ,  INCOME  \n"
    )

    record = payload["records"][0]
    assert record["transaction_date"] == "2026-08-01"
    assert record["description"] == "Rent payment"
    assert record["amount_minor"] == 120000


def test_utf8_bom_and_quoted_commas_are_supported():
    payload = normalize(
        b"\xef\xbb\xbfDate,Description,Amount,Direction\r\n"
        b"2026-08-01,\"Shop, Main Street\",\"1,250.00\",expense\r\n"
    )

    assert payload["records"][0]["description"] == "Shop, Main Street"
    assert payload["records"][0]["amount_minor"] == 125000
    assert payload["records"][0]["direction"] == "expense"


def test_semicolon_excel_export_is_supported():
    payload = normalize(
        "Date;Narration;Amount;Type\n"
        "2026-08-01;\"Sale; counter\";2.50;income\n"
    )

    assert payload["records"][0]["description"] == "Sale; counter"
    assert payload["records"][0]["amount_minor"] == 250


def test_blank_rows_and_blank_columns_are_ignored():
    payload = normalize(
        "Date,,Description,Amount,,\n"
        ",,,,,\n"
        "2026-08-01,,Sale,-10.00,,\n"
        ",,,,,\n"
    )

    assert len(payload["records"]) == 1
    assert payload["records"][0]["description"] == "Sale"


def test_negative_parenthesized_and_currency_values_are_losslessly_parsed():
    payload = normalize(
        "Date,Description,Amount\n"
        "2026-08-01,Refund,\"(₹1,250.50)\"\n"
        "2026-08-02,Sale,-$80.25\n"
    )

    assert [record["direction"] for record in payload["records"]] == [
        "expense",
        "expense",
    ]
    assert [record["amount_minor"] for record in payload["records"]] == [
        125050,
        8025,
    ]


def test_minor_unit_header_preserves_exact_integer_amount():
    payload = normalize(
        "Date,Amount Minor,Direction\n"
        "2026-08-01,12345,income\n"
    )

    assert payload["records"][0]["amount_minor"] == 12345


def test_source_transaction_id_and_balance_are_mapped():
    payload = normalize(
        "Date,Transaction_ID,Amount,Direction,Closing Balance\n"
        "2026-08-01,  txn-001  ,10.00,income,110.00\n"
    )

    assert payload["records"][0]["source_transaction_id"] == "txn-001"
    assert payload["records"][0]["balance_after_minor"] == 11000


def test_invalid_dates_are_rejected_with_safe_error():
    from services.csv_normalizer import CSVNormalizationError

    with pytest.raises(CSVNormalizationError, match="date"):
        normalize("Date,Amount,Direction\n2026-02-31,10.00,income\n")


def test_unknown_headers_are_rejected_instead_of_guessed():
    from services.csv_normalizer import CSVNormalizationError

    with pytest.raises(CSVNormalizationError, match="column"):
        normalize("When,What,How Much\n2026-08-01,Sale,10.00\n")


def test_ambiguous_positive_amount_without_direction_is_rejected():
    from services.csv_normalizer import CSVNormalizationError

    with pytest.raises(CSVNormalizationError, match="direction"):
        normalize("Date,Amount\n2026-08-01,10.00\n")


def test_duplicate_headers_are_rejected():
    from services.csv_normalizer import CSVNormalizationError

    with pytest.raises(CSVNormalizationError, match="header"):
        normalize("Date,Date,Amount\n2026-08-01,2026-08-01,10.00\n")


def test_malformed_csv_is_rejected_safely():
    from services.csv_normalizer import CSVNormalizationError

    with pytest.raises(CSVNormalizationError, match="CSV"):
        normalize('Date,Description,Amount\n2026-08-01,"unterminated,10.00\n')


def test_realistic_larger_csv_is_not_truncated():
    from services import ingestion_validation

    record_count = 1200
    rows = ["Date,Description,Amount,Direction,Category,Payment Mode"] + [
        f"2026-08-01,Sale {index},{index}.00,income,Sales,UPI"
        for index in range(1, record_count + 1)
    ]

    payload = normalize("\n".join(rows))

    assert len(payload["records"]) == record_count
    assert payload["records"][0]["description"] == "Sale 1"
    assert payload["records"][-1]["description"] == f"Sale {record_count}"
    assert record_count < ingestion_validation.MAX_RECORD_COUNT


def test_more_than_canonical_batch_limit_is_rejected_without_truncation():
    from services import ingestion_validation
    from services.csv_normalizer import CSVNormalizationError

    record_count = ingestion_validation.MAX_RECORD_COUNT + 1
    rows = ["Date,Amount,Direction"] + [
        f"2026-08-01,{index}.00,income" for index in range(1, record_count + 1)
    ]

    assert len(rows) - 1 == record_count
    with pytest.raises(CSVNormalizationError, match="too many records"):
        normalize("\n".join(rows))


def test_preview_validation_returns_controlled_over_limit_error():
    from services import csv_normalizer, ingestion_validation

    rows = [
        {
            "Date": "2026-08-01",
            "Description": f"Sale {index}",
            "Amount": f"{index + 1}.00",
            "Direction": "income",
            "Category": "Sales",
            "Payment Mode": "UPI",
            "Reference": "",
        }
        for index in range(ingestion_validation.MAX_RECORD_COUNT + 1)
    ]

    result = csv_normalizer.validate_preview_rows(rows)

    assert result["valid"] is False
    assert result["payload"] is None
    assert result["error_code"] == "RECORD_COUNT_OUT_OF_RANGE"
    assert str(ingestion_validation.MAX_RECORD_COUNT + 1) in result["error_message"]
    assert str(ingestion_validation.MAX_RECORD_COUNT) in result["error_message"]


def test_output_is_deterministic_and_json_serializable():
    import json

    csv_data = (
        "Date,Description,Amount,Direction\n"
        "2026-08-02,Second,2.00,income\n"
        "2026-08-01,First,1.00,income\n"
    )

    first = normalize(csv_data)
    second = normalize(csv_data)

    assert first == second
    assert json.loads(json.dumps(first)) == first


def test_validation_rejects_zero_amount_and_empty_data():
    from services.csv_normalizer import CSVNormalizationError

    with pytest.raises(CSVNormalizationError, match="amount"):
        normalize("Date,Amount,Direction\n2026-08-01,0,income\n")

    with pytest.raises(CSVNormalizationError, match="record"):
        normalize("Date,Amount,Direction\n")


def test_file_like_input_is_supported_without_accepting_paths():
    from io import BytesIO

    payload = normalize(
        BytesIO(b"Date,Amount,Direction\n2026-08-01,1.00,income\n")
    )

    assert payload["records"][0]["amount_minor"] == 100


GENERIC_MAPPING_CSV = (
    'When,Item,Money,Flow,Group,PayVia,RefNo,Unused\n'
    '2026-01-01,Notebook,250.00,RECEIVED,Stationery,UPI,T001,x\n'
    '2026-01-02,Wholesale stock,100.00,PAID,Purchases,Bank,T002,y\n'
)
GENERIC_MAPPING = {'date': 'When', 'description': 'Item', 'amount': 'Money',
                   'direction': 'Flow', 'category': 'Group', 'payment_method': 'PayVia',
                   'source_transaction_id': 'RefNo'}
GENERIC_DIRECTIONS = {'RECEIVED': 'income', 'PAID': 'expense'}


def test_arbitrary_headers_direction_values_and_canonical_preview():
    from services import csv_normalizer as n
    payload = n.normalize_csv(GENERIC_MAPPING_CSV, GENERIC_MAPPING, GENERIC_DIRECTIONS)
    assert payload['records'][0] == {
        'transaction_date': '2026-01-01', 'description': 'Notebook', 'amount_minor': 25000,
        'direction': 'income', 'category': 'Stationery', 'payment_method': 'UPI',
        'source_transaction_id': 'T001',
    }
    assert payload['records'][1]['direction'] == 'expense'
    preview = n.preview_csv_with_mapping(GENERIC_MAPPING_CSV,
                n.source_column_mapping(GENERIC_MAPPING), GENERIC_DIRECTIONS)
    assert preview[0]['Description'] == 'Notebook'
    assert n.validate_preview_rows(preview)['payload'] == payload


@pytest.mark.parametrize('description_header', ['Item', 'Medicine/Product Name'])
def test_manual_description_overrides_alias_without_new_alias(description_header):
    from services import csv_normalizer as n
    raw = f'Date,Remarks,{description_header},Amount,Direction\n2026-01-01,Wrong,Chosen,10,income\n'
    assert n.normalize_csv(raw)['records'][0]['description'] == 'Wrong'
    mapping = {'date': 'Date', 'description': description_header, 'amount': 'Amount', 'direction': 'Direction'}
    assert n.normalize_csv(raw, mapping)['records'][0]['description'] == 'Chosen'
    assert n._header_key(description_header) not in n._DESCRIPTION_ALIASES


@pytest.mark.parametrize('raw,mapping,directions,expected', [
    ('When,Out,In\n2026-01-01,25,\n2026-01-02,,30\n',
     {'date': 'When', 'debit': 'Out', 'credit': 'In'}, None, ['expense', 'income']),
    ('When,Money\n2026-01-01,-25\n2026-01-02,30\n',
     {'date': 'When', 'amount': 'Money'}, None, ['expense', 'income']),
    ('When,Money\n2026-01-01,-25\n',
     {'date': 'When', 'amount': 'Money'}, None, ['expense']),
])
def test_manual_amount_models(raw, mapping, directions, expected):
    from services import csv_normalizer as n
    payload = n.normalize_csv(raw, mapping, directions)
    assert [r['direction'] for r in payload['records']] == expected
    preview = n.preview_csv_with_mapping(raw, n.source_column_mapping(mapping), directions)
    assert n.validate_preview_rows(preview)['payload'] == payload


@pytest.mark.parametrize('mapping,message', [
    ({'amount': 'Money', 'direction': 'Flow'}, 'Date column'),
    ({'date': 'When'}, 'Amount column'),
    ({'date': 'When', 'amount': 'Money'}, 'Direction column'),
    ({'date': 'When', 'amount': 'When', 'direction': 'Flow'}, 'only once'),
])
def test_manual_mapping_errors_are_safe(mapping, message):
    from services import csv_normalizer as n
    with pytest.raises(n.CSVNormalizationError, match=message):
        n.normalize_csv(GENERIC_MAPPING_CSV, mapping)


@pytest.mark.parametrize('directions', [None, {'RECEIVED': 'other'}, {'RECEIVED': []},
                                       {'RECEIVED': 'income'}, {'RECEIVED': 'ignore', 'PAID': 'ignore'}])
def test_unknown_or_invalid_direction_mapping_fails_safely(directions):
    from services import csv_normalizer as n
    with pytest.raises(n.CSVNormalizationError):
        n.normalize_csv(GENERIC_MAPPING_CSV, GENERIC_MAPPING, directions)


def test_explicit_ignore_direction_and_override_known_value():
    from services import csv_normalizer as n
    result = n.normalize_csv(GENERIC_MAPPING_CSV, GENERIC_MAPPING,
                            {'RECEIVED': 'ignore', 'PAID': 'expense'})
    assert len(result['records']) == 1
    assert result['records'][0]['source_transaction_id'] == 'T002'
    raw = 'Date,Amount,Direction\n2026-01-01,10,credit\n'
    mapping = {'date': 'Date', 'amount': 'Amount', 'direction': 'Direction'}
    assert n.normalize_csv(raw, mapping, {'credit': 'expense'})['records'][0]['direction'] == 'expense'


def test_optional_fields_minor_units_and_edit_round_trip():
    from services import csv_normalizer as n
    raw = 'When,amount_minor,Flow,Who,balance_minor,Kind,OtherRef\n2026-01-01,125050,income,A,-250,POS,R1\n'
    mapping = {'date': 'When', 'amount': 'amount_minor', 'direction': 'Flow',
               'counterparty': 'Who', 'balance': 'balance_minor', 'source_subtype': 'Kind',
               'source_record_reference': 'OtherRef'}
    payload = n.normalize_csv(raw, mapping)
    row = payload['records'][0]
    assert row['amount_minor'] == 125050 and row['balance_after_minor'] == -250
    assert row['counterparty'] == 'A' and row['source_record_reference'] == 'R1'
    assert 'description' not in row
    preview = n.preview_csv_with_mapping(raw, n.source_column_mapping(mapping))
    assert preview[0]['Amount'] == '1250.5'
    assert n.validate_preview_rows(preview)['payload'] == payload


def test_mapped_currency_amount_uses_existing_parser():
    from services import csv_normalizer as n
    raw = 'When,Money,Flow\n2026-01-01,"₹1,250.50",credit\n'
    payload = n.normalize_csv(raw, {'date': 'When', 'amount': 'Money', 'direction': 'Flow'})
    assert payload['records'][0]['amount_minor'] == 125050
