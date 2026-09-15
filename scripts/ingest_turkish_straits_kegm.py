"""Ingest the KEGM Turkish Straits probe output into an idempotent master CSV.

Input is the diagnostic JSON produced by ``probe_turkish_straits_kegm.py``.
The PoC keeps tanker/gas records only (the probe already applies that filter),
normalises timestamps, assigns a deterministic record_id, and upserts into a
persistent-style CSV keyed on that id.

This is deliberately conservative because KEGM's public table does not expose a
stable voyage/transit ID or IMO number in the current probe. The deterministic
key therefore uses the fields that together describe one observed table row:
ship name, vessel type, SP2 timestamp and planning/status text. If the live probe
reveals a better stable identifier, replace ``make_record_id`` before production.

Usage:
    python3 scripts/ingest_turkish_straits_kegm.py \
        artifacts/turkish_straits_kegm_probe.json

Environment:
    KEGM_MASTER_PATH   output CSV path; defaults to
                       artifacts/turkish_straits_kegm_master.csv
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

MASTER_PATH = Path(os.environ.get("KEGM_MASTER_PATH", "artifacts/turkish_straits_kegm_master.csv"))

OUTPUT_COLUMNS = [
    "record_id",
    "ship_name",
    "vessel_type",
    "loa_m",
    "status",
    "planning_raw",
    "planning_time",
    "sp2_raw",
    "sp2_time",
    "sp1_raw",
    "pilot",
    "tug",
    "sp2_to_status_hours",
    "source_url",
    "source_fetched_utc",
    "ingested_at_utc",
]


def clean(value) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\xa0", " ").split())


def parse_kegm_dt(value: str) -> str:
    """Parse KEGM's DD.MM.YY HH:MM timestamp and return ISO text."""
    value = clean(value)
    if not value:
        return ""
    for token in [value[:14], value]:
        try:
            return datetime.strptime(token, "%d.%m.%y %H:%M").isoformat()
        except ValueError:
            pass
    return ""


def make_record_id(record: dict) -> str:
    material = "|".join(
        [
            clean(record.get("ship_name")).upper(),
            clean(record.get("vessel_type")).upper(),
            clean(record.get("sp2")),
            clean(record.get("planning_raw")),
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def normalise(payload: dict) -> pd.DataFrame:
    source_url = clean(payload.get("source"))
    source_fetched = clean(payload.get("fetched_utc"))
    ingested_at = datetime.now(timezone.utc).isoformat()

    rows = []
    for record in payload.get("records", []):
        rows.append(
            {
                "record_id": make_record_id(record),
                "ship_name": clean(record.get("ship_name")),
                "vessel_type": clean(record.get("vessel_type")),
                "loa_m": clean(record.get("loa_m")),
                "status": clean(record.get("status")),
                "planning_raw": clean(record.get("planning_raw")),
                "planning_time": parse_kegm_dt(record.get("planning_raw", "")),
                "sp2_raw": clean(record.get("sp2")),
                "sp2_time": parse_kegm_dt(record.get("sp2", "")),
                "sp1_raw": clean(record.get("sp1")),
                "pilot": clean(record.get("pilot")),
                "tug": clean(record.get("tug")),
                "sp2_to_status_hours": record.get("sp2_to_status_hours"),
                "source_url": source_url,
                "source_fetched_utc": source_fetched,
                "ingested_at_utc": ingested_at,
            }
        )

    if not rows:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    df = pd.DataFrame(rows)
    for col in OUTPUT_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[OUTPUT_COLUMNS]


def load_master(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    for col in OUTPUT_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[OUTPUT_COLUMNS]


def upsert(master: pd.DataFrame, fresh: pd.DataFrame) -> pd.DataFrame:
    if fresh.empty:
        return master.copy()
    combined = pd.concat([master, fresh], ignore_index=True)
    combined = combined.drop_duplicates(subset="record_id", keep="last")
    return combined.sort_values(["sp2_time", "ship_name", "record_id"], kind="stable").reset_index(drop=True)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 scripts/ingest_turkish_straits_kegm.py <probe-json>")

    input_path = Path(sys.argv[1])
    if not input_path.exists():
        raise SystemExit(f"Input not found: {input_path}")

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    fresh = normalise(payload)
    master = load_master(MASTER_PATH)
    merged = upsert(master, fresh)

    MASTER_PATH.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(MASTER_PATH, index=False)

    print(f"Probe records: {len(payload.get('records', []))}")
    print(f"Normalised rows: {len(fresh)}")
    print(f"Existing master rows: {len(master)}")
    print(f"Merged master rows: {len(merged)}")
    print(f"Net new rows: {len(merged) - len(master)}")
    if len(merged):
        print("Vessel types:")
        print(merged["vessel_type"].value_counts(dropna=False).to_string())
    print(f"Wrote {MASTER_PATH}")


if __name__ == "__main__":
    main()
