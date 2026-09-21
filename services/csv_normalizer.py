"""Deterministic CSV-to-canonical preprocessing for Module 4 ingestion."""

import csv
import io
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Optional

from services import ingestion_validation


class CSVNormalizationError(ValueError):
    """Safe, deterministic error raised for an unusable CSV upload."""

    _MESSAGES = {
        "INVALID_INPUT": "The uploaded CSV input is invalid.",
        "MALFORMED_CSV": "The uploaded CSV is malformed.",
        "EMPTY_CSV": "The CSV contains no records.",
        "DUPLICATE_HEADER": "The CSV contains duplicate headers.",
        "LOW_CONFIDENCE": "The CSV columns or direction could not be identified confidently.",
        "REQUIRED_COLUMN": "The CSV is missing a required column.",
        "INVALID_DATE": "A CSV transaction date is invalid.",
        "INVALID_AMOUNT": "A CSV transaction amount is invalid.",
        "INVALID_PRECISION": "A CSV amount has unsupported precision.",
        "INVALID_DIRECTION": "A CSV transaction direction is invalid.",
        "TOO_MANY_RECORDS": "The CSV contains too many records.",
        "INVALID_CANONICAL": "The normalized CSV failed canonical validation.",
    }

    def __init__(self, code: str) -> None:
        self.code = code if code in self._MESSAGES else "INVALID_INPUT"
        super().__init__(self._MESSAGES[self.code])


def _fail(code: str) -> None:
    raise CSVNormalizationError(code)


def _header_key(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value)).lstrip("\ufeff").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", str(value))
    text = re.sub(r"\s+", " ", text.strip())
    return text or None


_DATE_ALIASES = {
    "date",
    "transaction date",
    "txn date",
    "posting date",
    "value date",
    "date posted",
    "posted date",
    "invoice date",
}
_DESCRIPTION_ALIASES = {
    "description",
    "narration",
    "remarks",
    "details",
    "memo",
    "transaction details",
    "transaction description",
    "particulars",
}
_AMOUNT_ALIASES = {
    "amount",
    "transaction amount",
    "value",
    "transaction value",
    "net amount",
    "amount paid",
    "total amount",
    "balance change",
    "total",
}
_MINOR_AMOUNT_ALIASES = {
    "amount minor",
    "minor amount",
    "amount in minor units",
    "amount paise",
    "amount cents",
}
_DEBIT_ALIASES = {
    "debit",
    "debit amount",
    "withdrawal",
    "withdrawals",
    "withdraw",
    "outflow",
    "dr",
}
_CREDIT_ALIASES = {
    "credit",
    "credit amount",
    "deposit",
    "deposits",
    "inflow",
    "cr",
}
_DIRECTION_ALIASES = {
    "direction",
    "transaction direction",
    "debit credit",
    "credit debit",
    "cash flow",
    "flow",
    "income expense",
    "expense income",
    "type",
    "transaction type",
    "dr cr",
}
_BALANCE_ALIASES = {
    "balance",
    "closing balance",
    "running balance",
    "ledger balance",
    "available balance",
    "balance after",
}
_CATEGORY_ALIASES = {
    "category",
    "expense type",
    "income type",
    "transaction type",
    "expense category",
    "income category",
    "classification",
    "expense head",
}
_PAYMENT_ALIASES = {
    "payment mode",
    "payment method",
    "method",
    "mode",
    "payment type",
    "transaction mode",
    "channel",
}
_SOURCE_ID_ALIASES = {
    "source transaction id",
    "transaction id",
    "txn id",
    "reference",
    "reference id",
    "transaction reference",
    "source ref",
    "source reference",
    "utr",
    "rrn",
}
_COUNTERPARTY_ALIASES = {"counterparty", "merchant", "payee", "beneficiary"}
_SUBTYPE_ALIASES = {"subtype", "transaction subtype", "source subtype"}
_RECORD_REFERENCE_ALIASES = {
    "source record reference",
    "record reference",
    "line number",
    "row number",
}

_INCOME_DIRECTIONS = {
    "income",
    "credit",
    "cr",
    "deposit",
    "inflow",
    "received",
    "receipt",
    "revenue",
    "sale",
    "sales",
    "money in",
    "positive",
}
_EXPENSE_DIRECTIONS = {
    "expense",
    "debit",
    "dr",
    "withdrawal",
    "withdraw",
    "payment",
    "purchase",
    "outflow",
    "spent",
    "money out",
    "negative",
}
_PAYMENT_MODES = {
    "cash": "Cash",
    "upi": "UPI",
    "card": "Card",
    "credit card": "Card",
    "debit card": "Card",
    "bank": "Bank",
    "bank transfer": "Bank",
    "net banking": "Bank",
    "other": "Other",
}


def _read_text(source: Any) -> str:
    try:
        value = source.read() if hasattr(source, "read") else source
    except Exception as error:
        raise CSVNormalizationError("INVALID_INPUT") from error
    if isinstance(value, (bytes, bytearray, memoryview)):
        try:
            return bytes(value).decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise CSVNormalizationError("INVALID_INPUT") from error
    if type(value) is not str:
        raise CSVNormalizationError("INVALID_INPUT")
    return value.lstrip("\ufeff")


def _csv_rows(text: str) -> list[list[str]]:
    if not text.strip():
        _fail("EMPTY_CSV")
    if not _quotes_balanced(text):
        _fail("MALFORMED_CSV")
    try:
        sample = text[:8192]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.reader(
            io.StringIO(text, newline=""),
            dialect,
            strict=False,
            skipinitialspace=True,
        )
        rows = list(reader)
    except (csv.Error, TypeError, ValueError) as error:
        raise CSVNormalizationError("MALFORMED_CSV") from error
    while rows and all(not _clean_text(cell) for cell in rows[0]):
        rows.pop(0)
    if not rows:
        _fail("EMPTY_CSV")
    return rows


def _quotes_balanced(text: str) -> bool:
    """Check CSV quote balance while allowing escaped double quotes."""
    quoted = False
    index = 0
    while index < len(text):
        if text[index] != '"':
            index += 1
            continue
        if quoted and index + 1 < len(text) and text[index + 1] == '"':
            index += 2
            continue
        quoted = not quoted
        index += 1
    return not quoted


def _score_header(header: str, aliases: Iterable[str]) -> int:
    aliases = {_header_key(alias) for alias in aliases}
    if header in aliases:
        return 100
    header_tokens = set(header.split())
    scores = [
        80 + len(alias.split())
        for alias in aliases
        if set(alias.split()) <= header_tokens
    ]
    return max(scores, default=0)


def _choose_column(
    headers: dict[int, str],
    aliases: Iterable[str],
    *,
    excluded: set[int] | None = None,
) -> Optional[int]:
    excluded = excluded or set()
    scored = [
        (index, _score_header(header, aliases))
        for index, header in headers.items()
        if index not in excluded and header
    ]
    scored = [(index, score) for index, score in scored if score]
    if not scored:
        return None
    highest = max(score for _index, score in scored)
    best = [index for index, score in scored if score == highest]
    if len(best) != 1:
        _fail("LOW_CONFIDENCE")
    return best[0]


def _direction(value: Any) -> Optional[str]:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None
    key = _header_key(cleaned)
    if key in _INCOME_DIRECTIONS:
        return "income"
    if key in _EXPENSE_DIRECTIONS:
        return "expense"
    return None


def _looks_directional(rows: list[dict[int, str]], column: Optional[int]) -> bool:
    if column is None:
        return False
    values = [_clean_text(row.get(column)) for row in rows]
    values = [value for value in values if value is not None]
    return bool(values) and all(_direction(value) is not None for value in values)


def _parse_date(value: Any) -> str:
    cleaned = _clean_text(value)
    if cleaned is None:
        _fail("INVALID_DATE")
    if len(cleaned) >= 10 and cleaned[4] == "-" and cleaned[7] == "-":
        try:
            return date.fromisoformat(cleaned[:10]).isoformat()
        except ValueError:
            _fail("INVALID_DATE")
    formats = (
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%d.%m.%Y",
        "%d %b %Y",
        "%d %B %Y",
        "%m/%d/%Y",
    )
    for date_format in formats:
        try:
            return datetime.strptime(cleaned, date_format).date().isoformat()
        except ValueError:
            continue
    _fail("INVALID_DATE")


def _parse_number(value: Any) -> Decimal:
    cleaned = _clean_text(value)
    if cleaned is None:
        _fail("INVALID_AMOUNT")
    cleaned = cleaned.replace("−", "-").replace("–", "-")
    negative_parentheses = cleaned.startswith("(") and cleaned.endswith(")")
    if negative_parentheses:
        cleaned = cleaned[1:-1].strip()
    cleaned = re.sub(r"(?i)(?:inr|usd|eur|gbp|rs\.?)", "", cleaned)
    cleaned = re.sub(r"[₹$€£¥₩]", "", cleaned)
    cleaned = re.sub(r"\s+", "", cleaned)
    if re.search(r"[A-Za-z]", cleaned):
        _fail("INVALID_AMOUNT")
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind(".") and len(cleaned.rsplit(",", 1)[1]) <= 2:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        tail = cleaned.rsplit(",", 1)[1]
        if len(tail) == 2 and len(cleaned.split(",")) == 2:
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    try:
        number = Decimal(cleaned)
    except (InvalidOperation, ValueError):
        _fail("INVALID_AMOUNT")
    if not number.is_finite():
        _fail("INVALID_AMOUNT")
    return -number if negative_parentheses else number


def _to_minor(value: Decimal, *, minor_units: bool, balance: bool = False) -> int:
    magnitude = value if balance else abs(value)
    if minor_units:
        if magnitude != magnitude.to_integral_value():
            _fail("INVALID_PRECISION")
        return int(magnitude)
    scaled = magnitude * Decimal(100)
    if scaled != scaled.to_integral_value():
        _fail("INVALID_PRECISION")
    return int(scaled)


def _normalise_payment_mode(value: Any) -> Optional[str]:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None
    return _PAYMENT_MODES.get(_header_key(cleaned), cleaned)


def _header_map(rows: list[list[str]]) -> tuple[dict[int, str], list[dict[int, str]]]:
    raw_headers = rows[0]
    headers: dict[int, str] = {}
    seen: set[str] = set()
    for index, raw_header in enumerate(raw_headers):
        header = _header_key(raw_header)
        if not header:
            continue
        if header in seen:
            _fail("DUPLICATE_HEADER")
        seen.add(header)
        headers[index] = header
    if not headers:
        _fail("LOW_CONFIDENCE")
    records: list[dict[int, str]] = []
    width = len(raw_headers)
    for row in rows[1:]:
        if all(not _clean_text(cell) for cell in row):
            continue
        if len(row) > width:
            _fail("MALFORMED_CSV")
        padded = row + [""] * (width - len(row))
        records.append({index: padded[index] for index in headers})
    if not records:
        _fail("EMPTY_CSV")
    return headers, records


def _canonical_record(
    row: dict[int, str],
    *,
    date_column: int,
    amount_column: Optional[int],
    debit_column: Optional[int],
    credit_column: Optional[int],
    direction_column: Optional[int],
    description_column: Optional[int],
    category_column: Optional[int],
    payment_column: Optional[int],
    source_id_column: Optional[int],
    counterparty_column: Optional[int],
    subtype_column: Optional[int],
    reference_column: Optional[int],
    balance_column: Optional[int],
    amount_minor_units: bool,
    balance_minor_units: bool,
) -> dict[str, Any]:
    if debit_column is not None or credit_column is not None:
        debit = _clean_text(row.get(debit_column)) if debit_column is not None else None
        credit = _clean_text(row.get(credit_column)) if credit_column is not None else None
        if debit is not None and credit is not None:
            _fail("INVALID_DIRECTION")
        if debit is not None:
            amount_value = _parse_number(debit)
            direction = "expense"
        elif credit is not None:
            amount_value = _parse_number(credit)
            direction = "income"
        elif amount_column is not None:
            amount_value = _parse_number(row.get(amount_column))
            direction = (
                _direction(row.get(direction_column))
                if direction_column is not None
                else None
            )
        else:
            _fail("INVALID_AMOUNT")
    else:
        if amount_column is None:
            _fail("REQUIRED_COLUMN")
        amount_value = _parse_number(row.get(amount_column))
        direction = (
            _direction(row.get(direction_column))
            if direction_column is not None
            else None
        )
        if direction is None:
            if amount_value == 0:
                _fail("INVALID_AMOUNT")
            direction = "expense" if amount_value < 0 else "income"

    if direction is None:
        _fail("INVALID_DIRECTION")
    amount_minor = _to_minor(
        amount_value,
        minor_units=amount_minor_units,
    )
    if amount_minor <= 0:
        _fail("INVALID_AMOUNT")
    record: dict[str, Any] = {
        "transaction_date": _parse_date(row.get(date_column)),
        "amount_minor": amount_minor,
        "direction": direction,
    }
    optional_values = (
        (
            "source_transaction_id",
            _clean_text(row.get(source_id_column))
            if source_id_column is not None
            else None,
        ),
        (
            "category",
            _clean_text(row.get(category_column))
            if category_column is not None
            else None,
        ),
        (
            "description",
            _clean_text(row.get(description_column))
            if description_column is not None
            else None,
        ),
        (
            "counterparty",
            _clean_text(row.get(counterparty_column))
            if counterparty_column is not None
            else None,
        ),
        (
            "payment_method",
            _normalise_payment_mode(row.get(payment_column))
            if payment_column is not None
            else None,
        ),
        (
            "source_subtype",
            _clean_text(row.get(subtype_column))
            if subtype_column is not None
            else None,
        ),
        (
            "source_record_reference",
            _clean_text(row.get(reference_column))
            if reference_column is not None
            else None,
        ),
    )
    for field, value in optional_values:
        if value is not None:
            record[field] = value
    if balance_column is not None:
        balance_value = _clean_text(row.get(balance_column))
        if balance_value is not None:
            record["balance_after_minor"] = _to_minor(
                _parse_number(balance_value),
                minor_units=balance_minor_units,
                balance=True,
            )
    return record



MAPPING_IGNORE = "ignore"
MAPPING_FIELDS = (
    "transaction_date",
    "description",
    "amount",
    "direction",
    "category",
    "payment_method",
    "source_transaction_id",
    "debit",
    "credit",
)
_MAPPING_ALIASES = {
    "transaction_date": _DATE_ALIASES,
    "description": _DESCRIPTION_ALIASES,
    "amount": _MINOR_AMOUNT_ALIASES | _AMOUNT_ALIASES,
    "direction": _DIRECTION_ALIASES | {"type", "transaction type", "dr cr", "credit debit"},
    "category": _CATEGORY_ALIASES,
    "payment_method": _PAYMENT_ALIASES,
    "source_transaction_id": _SOURCE_ID_ALIASES,
    "debit": _DEBIT_ALIASES,
    "credit": _CREDIT_ALIASES,
}


def inspect_csv(source: Any) -> dict[str, Any]:
    """Return safe CSV headers and raw rows for an explicit mapping UI."""
    text = _read_text(source)
    rows = _csv_rows(text)
    headers, indexed_records = _header_map(rows)
    raw_headers = rows[0]
    visible_headers = [raw_headers[index].strip() for index in sorted(headers)]
    records = []
    for indexed in indexed_records:
        records.append({
            raw_headers[index].strip(): indexed.get(index, "")
            for index in sorted(headers)
        })
    return {
        "headers": visible_headers,
        "rows": records,
        "row_count": len(records),
    }


def _suggest_index(
    headers: dict[int, str],
    aliases: Iterable[str],
    *,
    excluded: set[int],
) -> Optional[int]:
    scored = [
        (index, _score_header(header, aliases))
        for index, header in headers.items()
        if index not in excluded and header
    ]
    scored = [(index, score) for index, score in scored if score]
    if not scored:
        return None
    highest = max(score for _index, score in scored)
    best = [index for index, score in scored if score == highest]
    return best[0] if len(best) == 1 else None


def suggest_column_mapping(source: Any) -> dict[str, str]:
    """Return a conservative source-header -> canonical-field suggestion."""
    text = _read_text(source)
    rows = _csv_rows(text)
    headers, records = _header_map(rows)
    raw_headers = rows[0]
    mapping = {raw_headers[index].strip(): MAPPING_IGNORE for index in sorted(headers)}
    excluded: set[int] = set()

    # Required and structurally strong fields first.
    for field in ("transaction_date", "debit", "credit", "amount"):
        index = _suggest_index(headers, _MAPPING_ALIASES[field], excluded=excluded)
        if index is not None:
            mapping[raw_headers[index].strip()] = field
            excluded.add(index)

    # Direction aliases such as "type" are accepted only when actual values
    # are directional, preventing a category/type column from being guessed.
    direction_index = _suggest_index(
        headers, _MAPPING_ALIASES["direction"], excluded=excluded
    )
    if direction_index is not None and _looks_directional(records, direction_index):
        mapping[raw_headers[direction_index].strip()] = "direction"
        excluded.add(direction_index)

    for field in (
        "description",
        "category",
        "payment_method",
        "source_transaction_id",
    ):
        index = _suggest_index(headers, _MAPPING_ALIASES[field], excluded=excluded)
        if index is not None:
            mapping[raw_headers[index].strip()] = field
            excluded.add(index)
    return mapping


def normalize_csv_with_mapping(
    source: Any,
    mapping: dict[str, str],
) -> dict[str, Any]:
    """Normalize CSV using a user-confirmed source-header mapping."""
    if not isinstance(mapping, dict):
        _fail("INVALID_INPUT")
    text = _read_text(source)
    rows = _csv_rows(text)
    headers, records = _header_map(rows)
    raw_headers = rows[0]
    index_by_raw = {raw_headers[index].strip(): index for index in headers}

    selected: dict[str, int] = {}
    for raw_header, target in mapping.items():
        if raw_header not in index_by_raw:
            _fail("INVALID_INPUT")
        if target == MAPPING_IGNORE:
            continue
        if target not in MAPPING_FIELDS:
            _fail("INVALID_INPUT")
        if target in selected:
            _fail("LOW_CONFIDENCE")
        selected[target] = index_by_raw[raw_header]

    date_column = selected.get("transaction_date")
    amount_column = selected.get("amount")
    debit_column = selected.get("debit")
    credit_column = selected.get("credit")
    direction_column = selected.get("direction")
    if date_column is None:
        _fail("REQUIRED_COLUMN")
    if amount_column is None and debit_column is None and credit_column is None:
        _fail("REQUIRED_COLUMN")
    if direction_column is None and debit_column is None and credit_column is None:
        signed_values = [_parse_number(row.get(amount_column)) for row in records]
        if not signed_values or all(value >= 0 for value in signed_values):
            _fail("LOW_CONFIDENCE")

    amount_header = headers.get(amount_column, "") if amount_column is not None else ""
    amount_minor_units = any(
        unit in amount_header for unit in ("minor", "paise", "cents")
    )

    canonical_records = [
        _canonical_record(
            row,
            date_column=date_column,
            amount_column=amount_column,
            debit_column=debit_column,
            credit_column=credit_column,
            direction_column=direction_column,
            description_column=selected.get("description"),
            category_column=selected.get("category"),
            payment_column=selected.get("payment_method"),
            source_id_column=selected.get("source_transaction_id"),
            counterparty_column=None,
            subtype_column=None,
            reference_column=None,
            balance_column=None,
            amount_minor_units=amount_minor_units,
            balance_minor_units=False,
        )
        for row in records
    ]
    payload = {
        "contract_version": ingestion_validation.CONTRACT_VERSION,
        "source_system": ingestion_validation.SOURCE_SYSTEM,
        "records": canonical_records,
    }
    try:
        return ingestion_validation.validate_ingestion_payload(payload)
    except ingestion_validation.ValidationError as error:
        if error.field == "transaction_date":
            raise CSVNormalizationError("INVALID_DATE") from error
        if error.field == "amount_minor":
            raise CSVNormalizationError("INVALID_AMOUNT") from error
        if error.field == "direction":
            raise CSVNormalizationError("INVALID_DIRECTION") from error
        if error.code == "RECORD_COUNT_OUT_OF_RANGE":
            raise CSVNormalizationError("TOO_MANY_RECORDS") from error
        raise CSVNormalizationError("INVALID_CANONICAL") from error



def preview_csv_with_mapping(
    source: Any,
    mapping: dict[str, str],
) -> list[dict[str, Any]]:
    """Map raw CSV values into an editable preview before row validation.

    This intentionally does not parse dates or amounts.  Users can therefore
    correct malformed row values in the preview instead of being blocked
    before the editor appears.
    """
    if not isinstance(mapping, dict):
        _fail("INVALID_INPUT")
    text = _read_text(source)
    rows = _csv_rows(text)
    headers, records = _header_map(rows)
    raw_headers = rows[0]
    index_by_raw = {raw_headers[index].strip(): index for index in headers}

    selected: dict[str, int] = {}
    for raw_header, target in mapping.items():
        if raw_header not in index_by_raw:
            _fail("INVALID_INPUT")
        if target == MAPPING_IGNORE:
            continue
        if target not in MAPPING_FIELDS:
            _fail("INVALID_INPUT")
        if target in selected:
            _fail("LOW_CONFIDENCE")
        selected[target] = index_by_raw[raw_header]

    if "transaction_date" not in selected:
        _fail("REQUIRED_COLUMN")
    if not {"amount", "debit", "credit"}.intersection(selected):
        _fail("REQUIRED_COLUMN")

    # Signed amount files can safely infer direction only when the file
    # actually contains both positive and negative numeric values.
    infer_signed_direction = False
    if (
        "amount" in selected
        and "direction" not in selected
        and "debit" not in selected
        and "credit" not in selected
    ):
        parsed = []
        try:
            parsed = [_parse_number(row.get(selected["amount"])) for row in records]
        except CSVNormalizationError:
            parsed = []
        infer_signed_direction = (
            bool(parsed)
            and any(value < 0 for value in parsed)
            and any(value > 0 for value in parsed)
        )

    preview: list[dict[str, Any]] = []
    for row in records:
        amount_value: Any = ""
        direction_value: Any = ""

        debit = (
            _clean_text(row.get(selected["debit"]))
            if "debit" in selected
            else None
        )
        credit = (
            _clean_text(row.get(selected["credit"]))
            if "credit" in selected
            else None
        )
        if debit is not None or credit is not None:
            if debit is not None and credit is None:
                amount_value = debit
                direction_value = "expense"
            elif credit is not None and debit is None:
                amount_value = credit
                direction_value = "income"
            else:
                # Both populated is ambiguous.  Preserve a visible amount but
                # leave direction blank so row validation forces a correction.
                amount_value = debit or credit or ""
                direction_value = ""
        elif "amount" in selected:
            amount_value = row.get(selected["amount"], "")
            if "direction" in selected:
                direction_value = row.get(selected["direction"], "")
            elif infer_signed_direction:
                try:
                    parsed_amount = _parse_number(amount_value)
                    direction_value = "expense" if parsed_amount < 0 else "income"
                except CSVNormalizationError:
                    direction_value = ""

        preview.append(
            {
                "Date": row.get(selected["transaction_date"], ""),
                "Description": (
                    row.get(selected["description"], "")
                    if "description" in selected
                    else ""
                ),
                "Amount": amount_value,
                "Direction": direction_value,
                "Category": (
                    row.get(selected["category"], "")
                    if "category" in selected
                    else ""
                ),
                "Payment Mode": (
                    row.get(selected["payment_method"], "")
                    if "payment_method" in selected
                    else ""
                ),
                "Reference": (
                    row.get(selected["source_transaction_id"], "")
                    if "source_transaction_id" in selected
                    else ""
                ),
            }
        )
    return preview

def preview_rows_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert canonical records to user-editable major-unit preview rows."""
    records = payload.get("records", []) if isinstance(payload, dict) else []
    preview = []
    for record in records:
        preview.append({
            "Date": record.get("transaction_date"),
            "Description": record.get("description", ""),
            "Amount": str(Decimal(record.get("amount_minor", 0)) / Decimal(100)),
            "Direction": record.get("direction", ""),
            "Category": record.get("category", ""),
            "Payment Mode": record.get("payment_method", ""),
            "Reference": record.get("source_transaction_id", ""),
        })
    return preview


def validate_preview_rows(rows: Any) -> dict[str, Any]:
    """Validate user-edited preview rows without persisting any transaction."""
    if not isinstance(rows, list):
        return {"valid": False, "errors": [{"row": None, "message": "Preview data is invalid."}]}

    canonical_records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        try:
            if not isinstance(row, dict):
                _fail("INVALID_INPUT")
            transaction_date = _parse_date(row.get("Date"))
            amount = _parse_number(row.get("Amount"))
            amount_minor = _to_minor(amount, minor_units=False)
            if amount_minor <= 0:
                _fail("INVALID_AMOUNT")
            direction = _direction(row.get("Direction"))
            if direction is None:
                _fail("INVALID_DIRECTION")
            record: dict[str, Any] = {
                "transaction_date": transaction_date,
                "amount_minor": amount_minor,
                "direction": direction,
            }
            optional = {
                "description": _clean_text(row.get("Description")),
                "category": _clean_text(row.get("Category")),
                "payment_method": _normalise_payment_mode(row.get("Payment Mode")),
                "source_transaction_id": _clean_text(row.get("Reference")),
            }
            for key, value in optional.items():
                if value is not None:
                    record[key] = value
            ingestion_validation.validate_ingestion_payload({
                "contract_version": ingestion_validation.CONTRACT_VERSION,
                "source_system": ingestion_validation.SOURCE_SYSTEM,
                "records": [record],
            })
            canonical_records.append(record)
        except (CSVNormalizationError, ingestion_validation.ValidationError) as error:
            errors.append({"row": index, "message": str(error)})

    payload = None
    error_code = None
    error_message = None
    if not errors and canonical_records:
        try:
            payload = ingestion_validation.validate_ingestion_payload({
                "contract_version": ingestion_validation.CONTRACT_VERSION,
                "source_system": ingestion_validation.SOURCE_SYSTEM,
                "records": canonical_records,
            })
        except ingestion_validation.ValidationError as error:
            error_code = error.code
            if error.code == "RECORD_COUNT_OUT_OF_RANGE":
                error_message = (
                    f"This file contains {len(canonical_records)} transactions. "
                    f"FinSight currently supports up to "
                    f"{ingestion_validation.MAX_RECORD_COUNT} transactions per import. "
                    "Split the file into smaller batches and try again."
                )
            else:
                error_message = "The transaction data could not be validated."
            errors.append({"row": None, "message": error_message})

    return {
        "valid": not errors and bool(canonical_records),
        "valid_count": len(canonical_records),
        "invalid_count": len(errors),
        "errors": errors,
        "payload": payload,
        "error_code": error_code,
        "error_message": error_message,
    }

def normalize_csv(source: Any) -> dict[str, Any]:
    """Convert CSV text/bytes/file-like input into validated canonical JSON."""
    text = _read_text(source)
    rows = _csv_rows(text)
    headers, records = _header_map(rows)
    date_column = _choose_column(headers, _DATE_ALIASES)
    if date_column is None:
        _fail("REQUIRED_COLUMN")

    excluded: set[int] = {date_column}
    direction_column = _choose_column(headers, _DIRECTION_ALIASES, excluded=excluded)
    if direction_column is not None:
        excluded.add(direction_column)
    type_column = _choose_column(headers, {"type", "transaction type"}, excluded=excluded)
    if direction_column is None and _looks_directional(records, type_column):
        direction_column = type_column
        excluded.add(type_column)

    debit_column = _choose_column(headers, _DEBIT_ALIASES, excluded=excluded)
    if debit_column is not None:
        excluded.add(debit_column)
    credit_column = _choose_column(headers, _CREDIT_ALIASES, excluded=excluded)
    if credit_column is not None:
        excluded.add(credit_column)
    amount_column = _choose_column(
        headers,
        _MINOR_AMOUNT_ALIASES | _AMOUNT_ALIASES,
        excluded=excluded,
    )
    if amount_column is not None:
        excluded.add(amount_column)
    if amount_column is None and debit_column is None and credit_column is None:
        _fail("REQUIRED_COLUMN")

    if direction_column is None and debit_column is None and credit_column is None:
        if amount_column is None:
            _fail("INVALID_DIRECTION")
        signed_values = [_parse_number(row.get(amount_column)) for row in records]
        if signed_values and all(value >= 0 for value in signed_values):
            _fail("LOW_CONFIDENCE")

    description_column = _choose_column(headers, _DESCRIPTION_ALIASES, excluded=excluded)
    category_column = _choose_column(
        headers,
        _CATEGORY_ALIASES,
        excluded=excluded | ({type_column} if type_column == direction_column else set()),
    )
    payment_column = _choose_column(headers, _PAYMENT_ALIASES, excluded=excluded)
    source_id_column = _choose_column(headers, _SOURCE_ID_ALIASES, excluded=excluded)
    counterparty_column = _choose_column(headers, _COUNTERPARTY_ALIASES, excluded=excluded)
    subtype_column = _choose_column(headers, _SUBTYPE_ALIASES, excluded=excluded)
    reference_column = _choose_column(headers, _RECORD_REFERENCE_ALIASES, excluded=excluded)
    balance_column = _choose_column(headers, _BALANCE_ALIASES, excluded=excluded)

    amount_header = headers.get(amount_column, "") if amount_column is not None else ""
    balance_header = headers.get(balance_column, "") if balance_column is not None else ""
    amount_minor_units = any(
        unit in amount_header for unit in ("minor", "paise", "cents")
    )
    balance_minor_units = any(
        unit in balance_header for unit in ("minor", "paise", "cents")
    )

    canonical_records = [
        _canonical_record(
            row,
            date_column=date_column,
            amount_column=amount_column,
            debit_column=debit_column,
            credit_column=credit_column,
            direction_column=direction_column,
            description_column=description_column,
            category_column=category_column,
            payment_column=payment_column,
            source_id_column=source_id_column,
            counterparty_column=counterparty_column,
            subtype_column=subtype_column,
            reference_column=reference_column,
            balance_column=balance_column,
            amount_minor_units=amount_minor_units,
            balance_minor_units=balance_minor_units,
        )
        for row in records
    ]
    payload = {
        "contract_version": ingestion_validation.CONTRACT_VERSION,
        "source_system": ingestion_validation.SOURCE_SYSTEM,
        "records": canonical_records,
    }
    try:
        return ingestion_validation.validate_ingestion_payload(payload)
    except ingestion_validation.ValidationError as error:
        if error.field == "transaction_date":
            raise CSVNormalizationError("INVALID_DATE") from error
        if error.field == "amount_minor":
            raise CSVNormalizationError("INVALID_AMOUNT") from error
        if error.field == "direction":
            raise CSVNormalizationError("INVALID_DIRECTION") from error
        if error.code == "RECORD_COUNT_OUT_OF_RANGE":
            raise CSVNormalizationError("TOO_MANY_RECORDS") from error
        raise CSVNormalizationError("INVALID_CANONICAL") from error


def normalize_csv_text(text: str) -> dict[str, Any]:
    """Normalize a CSV Unicode string."""
    return normalize_csv(text)


def normalize_csv_bytes(data: bytes) -> dict[str, Any]:
    """Normalize UTF-8 CSV bytes, including a UTF-8 BOM."""
    return normalize_csv(data)


def normalize_uploaded_csv(uploaded_file: Any) -> dict[str, Any]:
    """Normalize a file-like upload without accepting filesystem paths."""
    return normalize_csv(uploaded_file)


__all__ = [
    "CSVNormalizationError",
    "MAPPING_FIELDS",
    "MAPPING_IGNORE",
    "inspect_csv",
    "suggest_column_mapping",
    "normalize_csv_with_mapping",
    "preview_csv_with_mapping",
    "preview_rows_from_payload",
    "validate_preview_rows",
    "normalize_csv",
    "normalize_csv_bytes",
    "normalize_csv_text",
    "normalize_uploaded_csv",
]
