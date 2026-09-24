"""Reviewed source records. No crawling or unsafe serialized vector indexes."""
import hashlib
import json
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

CATALOG = Path(__file__).resolve().parents[2] / "data/schemes/verified.json"


def allowed_source(url):
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        return (parsed.scheme == "https" and not parsed.username and not parsed.password
                and parsed.port in (None, 443) and not parsed.fragment
                and any(host.endswith("." + suffix) for suffix in ("gov.in", "nic.in")))
    except (ValueError, TypeError):
        return False


def content_hash(record):
    content = {k: record[k] for k in ("scheme_id", "scheme_name", "facts", "rules", "official_url", "aliases", "tags")}
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def valid_record(record, today=None, max_age=90):
    try:
        age = ((today or date.today()) - date.fromisoformat(record["last_checked_at"])).days
        return (0 <= age <= max_age and record["verification_status"] == "verified_official"
                and allowed_source(record["official_url"])
                and urlsplit(record["official_url"]).hostname == record["source_domain"]
                and bool(record["scheme_name"]) and bool(record["facts"]["eligibility"]["en"])
                and record["content_hash"] == content_hash(record))
    except (KeyError, TypeError, ValueError):
        return False


def load_records(path=CATALOG, today=None):
    records = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("Invalid scheme catalog")
    return [r for r in records if valid_record(r, today)]


def eligibility(record, profile):
    missing, failed = [], []
    for field, expected in record.get("rules", {}).items():
        value = profile.get(field)
        if value is None or value == "":
            missing.append(field)
        elif field == "owner_age":
            if float(value) < expected:
                failed.append(field)
        elif isinstance(expected, list):
            if str(value).casefold() not in [str(v).casefold() for v in expected]:
                failed.append(field)
        elif value != expected:
            failed.append(field)
    return missing, failed
