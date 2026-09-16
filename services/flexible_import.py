"""Flexible, reviewable CSV/XML preprocessing for transaction ingestion."""

from __future__ import annotations

import csv
import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from typing import Any, Optional

from services import csv_normalizer
from services import ingestion_validation

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_COLUMNS = 100

FIELD_LABELS = {
    "transaction_date": "Transaction date",
    "amount": "Amount (signed or paired with direction)",
    "debit": "Debit / expense amount",
    "credit": "Credit / income amount",
    "direction": "Direction / type",
    "description": "Description / narration",
    "category": "Category",
    "payment_method": "Payment method",
    "source_transaction_id": "Transaction/reference ID",
    "counterparty": "Counterparty / merchant",
    "balance": "Balance after transaction",
}

ALIASES = {
    "transaction_date": {"date", "transaction date", "txn date", "posting date", "posted on", "value date", "created at", "timestamp", "when"},
    "amount": {"amount", "transaction amount", "txn amount", "value", "net amount", "how much", "total", "amt"},
    "debit": {"debit", "debit amount", "withdrawal", "withdrawal amount", "money out", "paid out", "dr amount", "debit amt"},
    "credit": {"credit", "credit amount", "deposit", "deposit amount", "money in", "received", "cr amount", "credit amt"},
    "direction": {"direction", "type", "transaction type", "txn type", "debit credit", "dr cr", "income expense", "flow"},
    "description": {"description", "narration", "particulars", "remarks", "details", "memo", "transaction details", "what"},
    "category": {"category", "expense category", "income category", "classification", "purpose"},
    "payment_method": {"payment mode", "payment method", "mode", "method", "channel", "transaction mode"},
    "source_transaction_id": {"transaction id", "txn id", "reference", "reference id", "ref no", "reference number", "utr", "rrn", "cheque number"},
    "counterparty": {"counterparty", "merchant", "payee", "beneficiary", "payer", "vendor", "party"},
    "balance": {"balance", "running balance", "closing balance", "available balance", "ledger balance"},
}


class FlexibleImportError(ValueError):
    """A safe error suitable for displaying to the uploader."""


@dataclass(frozen=True)
class ImportAnalysis:
    file_type: str
    headers: list[str]
    rows: list[dict[str, str]]
    mapping: dict[str, Optional[str]]
    confidence: dict[str, int]

    @property
    def needs_review(self) -> bool:
        required = self.mapping.get("transaction_date") and (
            self.mapping.get("amount") or self.mapping.get("debit") or self.mapping.get("credit")
        )
        return not required or any(
            self.mapping.get(field) and self.confidence.get(field, 0) < 70
            for field in ("transaction_date", "amount", "debit", "credit", "direction")
        )


def _key(value: Any) -> str:
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(value))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()


def _decode(data: bytes) -> str:
    if len(data) > MAX_UPLOAD_BYTES:
        raise FlexibleImportError("The uploaded file is larger than 5 MB.")
    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise FlexibleImportError("The uploaded file uses an unsupported text encoding.")


def _csv_table(text: str) -> tuple[list[str], list[dict[str, str]]]:
    try:
        rows = csv_normalizer._csv_rows(text)
    except csv_normalizer.CSVNormalizationError as error:
        raise FlexibleImportError(str(error)) from error
    headers = [str(value).strip() for value in rows[0]]
    if not headers or len(headers) > MAX_COLUMNS or any(not value for value in headers):
        raise FlexibleImportError("The file has missing or too many column names.")
    if len({_key(value) for value in headers}) != len(headers):
        raise FlexibleImportError("The file contains duplicate column names.")
    records = []
    for raw_row in rows[1:]:
        if not any(str(value).strip() for value in raw_row):
            continue
        if len(raw_row) > len(headers):
            raise FlexibleImportError("A row contains more values than the header.")
        padded = raw_row + [""] * (len(headers) - len(raw_row))
        records.append(dict(zip(headers, padded)))
    if not records:
        raise FlexibleImportError("The uploaded file contains no transaction rows.")
    return headers, records


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xml_table(text: str) -> tuple[list[str], list[dict[str, str]]]:
    if re.search(r"<!DOCTYPE|<!ENTITY", text, re.IGNORECASE):
        raise FlexibleImportError("XML document types and entities are not allowed.")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise FlexibleImportError("The uploaded XML is malformed.") from error
    candidates = []
    for element in root.iter():
        children = list(element)
        if len(children) >= 2 and all(not list(child) for child in children):
            row = {_local_name(child.tag): (child.text or "").strip() for child in children}
            if len(row) >= 2:
                candidates.append(row)
    if not candidates:
        raise FlexibleImportError("No transaction records were found in the XML.")
    counts: dict[tuple[str, ...], int] = {}
    for row in candidates:
        signature = tuple(row)
        counts[signature] = counts.get(signature, 0) + 1
    signature = max(counts, key=lambda item: (counts[item], len(item)))
    records = [row for row in candidates if tuple(row) == signature]
    if len(signature) > MAX_COLUMNS:
        raise FlexibleImportError("The XML contains too many fields per record.")
    return list(signature), records


def _number(value: str) -> bool:
    cleaned = re.sub(r"(?i)(inr|rs\.?|usd|eur)", "", value)
    cleaned = re.sub(r"[₹$€£,\s()]", "", cleaned).replace("−", "-")
    try:
        return bool(cleaned) and Decimal(cleaned).is_finite()
    except InvalidOperation:
        return False


def _date(value: str) -> bool:
    value = value.strip()
    formats = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d.%m.%Y", "%m/%d/%Y", "%d %b %Y")
    for date_format in formats:
        try:
            datetime.strptime(value[:10] if date_format == "%Y-%m-%d" else value, date_format)
            return True
        except ValueError:
            pass
    return False


def _direction(value: str) -> bool:
    return _key(value) in csv_normalizer._INCOME_DIRECTIONS | csv_normalizer._EXPENSE_DIRECTIONS


def _header_score(header: str, field: str) -> int:
    key = _key(header)
    aliases = ALIASES[field]
    if key in aliases:
        return 100
    token_score = max((80 if set(alias.split()) <= set(key.split()) else 0) for alias in aliases)
    fuzzy = int(max(SequenceMatcher(None, key, alias).ratio() for alias in aliases) * 75)
    return max(token_score, fuzzy if fuzzy >= 55 else 0)


def _value_score(values: list[str], field: str) -> int:
    present = [str(value).strip() for value in values if str(value).strip()][:50]
    if not present:
        return 0
    checker = _date if field == "transaction_date" else _number if field in {"amount", "debit", "credit", "balance"} else _direction if field == "direction" else None
    if checker is None:
        return 25
    return int(sum(checker(value) for value in present) * 100 / len(present))


def analyze_upload(data: bytes, filename: str) -> ImportAnalysis:
    text = _decode(data)
    if filename.lower().endswith(".xml") or text.lstrip().startswith("<"):
        headers, rows, file_type = *_xml_table(text), "XML"
    else:
        headers, rows, file_type = *_csv_table(text), "CSV"
    mapping: dict[str, Optional[str]] = {}
    confidence: dict[str, int] = {}
    used: set[str] = set()
    for field in FIELD_LABELS:
        candidates = []
        for header in headers:
            if header not in used:
                score = int(_header_score(header, field) * 0.75 + _value_score([row.get(header, "") for row in rows], field) * 0.25)
                candidates.append((score, header))
        score, header = max(candidates, default=(0, None))
        threshold = 55 if field in {"transaction_date", "amount", "debit", "credit", "direction"} else 68
        if header is not None and score >= threshold:
            mapping[field], confidence[field] = header, score
            used.add(header)
        else:
            mapping[field], confidence[field] = None, 0
    return ImportAnalysis(file_type, headers, rows, mapping, confidence)


def normalize_analysis(analysis: ImportAnalysis, mapping: dict[str, Optional[str]]) -> dict[str, Any]:
    if not mapping.get("transaction_date"):
        raise FlexibleImportError("Select the transaction-date column.")
    has_amount = bool(mapping.get("amount"))
    has_split_amount = bool(mapping.get("debit") or mapping.get("credit"))
    if not (has_amount or has_split_amount):
        raise FlexibleImportError("Select an amount column or debit/credit columns.")
    if has_amount and has_split_amount:
        raise FlexibleImportError(
            "Use either one amount column or separate money-out and money-in columns, not both."
        )
    selected_columns = [column for column in mapping.values() if column]
    if len(selected_columns) != len(set(selected_columns)):
        raise FlexibleImportError("Each source column can be assigned only once.")
    output_names = {
        "transaction_date": "Date", "amount": "Amount", "debit": "Debit", "credit": "Credit",
        "direction": "Direction", "description": "Description", "category": "Category",
        "payment_method": "Payment Mode", "source_transaction_id": "Transaction ID",
        "counterparty": "Counterparty", "balance": "Balance",
    }
    selected = [(field, column) for field, column in mapping.items() if column]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=[output_names[field] for field, _ in selected])
    writer.writeheader()
    for row in analysis.rows:
        writer.writerow({output_names[field]: row.get(column, "") for field, column in selected})
    try:
        return csv_normalizer.normalize_csv(buffer.getvalue())
    except csv_normalizer.CSVNormalizationError as error:
        raise FlexibleImportError(str(error)) from error


def normalize_analysis_batches(
    analysis: ImportAnalysis,
    mapping: dict[str, Optional[str]],
) -> list[dict[str, Any]]:
    """Normalize a large import into backend-sized, independently valid batches."""
    size = ingestion_validation.MAX_RECORD_COUNT
    batches = []
    for start in range(0, len(analysis.rows), size):
        batch_analysis = ImportAnalysis(
            file_type=analysis.file_type,
            headers=analysis.headers,
            rows=analysis.rows[start : start + size],
            mapping=analysis.mapping,
            confidence=analysis.confidence,
        )
        batches.append(normalize_analysis(batch_analysis, mapping))
    return batches


def preview_rows(analysis: ImportAnalysis, limit: int = 5) -> list[dict[str, str]]:
    return analysis.rows[:limit]


__all__ = ["FIELD_LABELS", "FlexibleImportError", "ImportAnalysis", "analyze_upload", "normalize_analysis", "normalize_analysis_batches", "preview_rows"]
