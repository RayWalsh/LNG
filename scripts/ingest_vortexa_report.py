"""
Ingest a Vortexa Panama Canal Report (.xlsx) into the persistent master
dataset at data/master_transits.csv.

This is the real deal — Vortexa confirmed there is no API access to
Panama Canal wait times, only this periodic email report. It contains
exactly the fields the (denied) CanalTransit API endpoint would have
given us: queue_arrival_time, canal_entry_time, canal_exit_time,
wait_time, direction, lock, vessel_deadweight — at the individual
vessel/transit level, with a stable unique `id` per transit.

Design: rather than reprocessing from scratch on every upload, this
UPSERTS into a persistent CSV keyed on `id`. Each new report re-exports
overlapping history (the 'historic' sheet alone covers ~6 years), so:
  - a transit seen before gets its row updated (e.g. a 'future' booking
    that has since happened gains a real canal_entry_time / wait_time)
  - a transit never seen before gets added
  - nothing is ever silently dropped, even if a future report's window
    is narrower than this one

Run manually or via GitHub Actions:
    python3 scripts/ingest_vortexa_report.py <path-to-xlsx>
"""

import sys
import os
from datetime import datetime, timezone

import pandas as pd

MASTER_PATH = os.environ.get("MASTER_TRANSITS_PATH", "data/master_transits.csv")

# The three sheets that carry individual transit/vessel records (the
# rest are Vortexa's own pre-built chart/dashboard sheets, which we
# don't need — we compute our own charts from these three).
SOURCE_SHEETS = ["historic", "waiting", "future"]

# Columns we keep from each sheet. All three sheets share this shape.
KEEP_COLUMNS = [
    "id", "vessel_name", "vessel_imo", "vessel_class", "vessel_family",
    "vessel_category", "vessel_deadweight",
    "queue_arrival_time", "canal_entry_time", "canal_exit_time",
    "wait_time", "booked", "booked_date", "direction", "lock",
    "voyage_status", "origin_port", "destination_port",
]


def read_sheet(xlsx_path, sheet_name):
    df = pd.read_excel(xlsx_path, sheet_name=sheet_name)
    if not len(df):
        return df

    # Not every sheet necessarily has every column (defensive — add any
    # missing ones as empty so concatenation below is always safe).
    for col in KEEP_COLUMNS:
        if col not in df.columns:
            df[col] = None
    df = df[KEEP_COLUMNS].copy()
    df["source_sheet"] = sheet_name
    return df


def load_master(path):
    if os.path.exists(path):
        df = pd.read_csv(path, parse_dates=[
            "queue_arrival_time", "canal_entry_time", "canal_exit_time", "booked_date",
        ])
        return df
    return pd.DataFrame(columns=KEEP_COLUMNS + ["source_sheet", "ingested_at"])


def upsert(master_df, new_df, ingested_at):
    new_df = new_df.copy()
    new_df["ingested_at"] = ingested_at

    if not len(master_df):
        return new_df.drop_duplicates(subset="id", keep="last")

    # Combine, then for any duplicate id keep the LAST occurrence — the
    # new_df rows are appended after master_df, so "last" means "the
    # freshest data we just ingested" wins for any id seen before.
    combined = pd.concat([master_df, new_df], ignore_index=True)
    combined = combined.drop_duplicates(subset="id", keep="last")
    return combined


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 scripts/ingest_vortexa_report.py <path-to-xlsx>")
        sys.exit(1)

    xlsx_path = sys.argv[1]
    if not os.path.exists(xlsx_path):
        print(f"File not found: {xlsx_path}")
        sys.exit(1)

    ingested_at = datetime.now(timezone.utc).isoformat()

    print(f"Reading {xlsx_path} ...")
    all_new_rows = []
    for sheet in SOURCE_SHEETS:
        df = read_sheet(xlsx_path, sheet)
        print(f"  {sheet}: {len(df)} rows")
        all_new_rows.append(df)

    new_df = pd.concat(all_new_rows, ignore_index=True)
    print(f"\nTotal new/updated rows from this report: {len(new_df)}")

    print(f"\nLoading existing master dataset from {MASTER_PATH} ...")
    master_df = load_master(MASTER_PATH)
    print(f"  {len(master_df)} rows currently in master dataset")

    merged = upsert(master_df, new_df, ingested_at)
    print(f"\nMerged master dataset: {len(merged)} rows "
          f"({len(merged) - len(master_df)} net new)")

    os.makedirs(os.path.dirname(MASTER_PATH) or ".", exist_ok=True)
    merged.to_csv(MASTER_PATH, index=False)
    print(f"\nWrote {MASTER_PATH}")


if __name__ == "__main__":
    main()