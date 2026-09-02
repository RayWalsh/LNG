"""Import Vortexa Panama Canal workbooks into a persistent master CSV.

Historic rows are upserted by Vortexa's stable ``id``. ``waiting`` and
``future`` are current-state snapshots, so each successful workbook replaces
the previous rows from those two sheets. The master is written only after all
three source sheets pass validation.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

MASTER_PATH = Path(os.environ.get("MASTER_TRANSITS_PATH", "data/master_transits.csv"))
REPORT_PATH = Path(os.environ.get("IMPORT_REPORT_PATH", "reports/latest-import.json"))
SOURCE_SHEETS = ("historic", "waiting", "future")
SNAPSHOT_SHEETS = ("waiting", "future")
DATE_COLUMNS = ("queue_arrival_time", "canal_entry_time", "canal_exit_time", "booked_date")
REQUIRED_COLUMNS = {"id", "vessel_name", "queue_arrival_time", "direction", "lock"}
KEEP_COLUMNS = [
    "id", "vessel_name", "vessel_imo", "vessel_class", "vessel_family",
    "vessel_type", "vessel_category", "vessel_deadweight", "cubic_metres",
    "queue_arrival_time", "canal_entry_time", "canal_exit_time", "wait_time",
    "booked", "booked_date", "direction", "lock", "voyage_status",
    "origin_port", "destination_port", "products", "source_sheet", "ingested_at",
]
SHEET_PRIORITY = {"future": 1, "waiting": 2, "historic": 3}


class ImportValidationError(ValueError):
    pass


@dataclass
class WorkbookRead:
    rows: pd.DataFrame
    sheet_counts: dict[str, int]
    rejected_rows: list[dict[str, object]]
    duplicates_within_upload: int


def blank_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=KEEP_COLUMNS)


def load_master(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return blank_frame()
    master = pd.read_csv(path, dtype={"id": "string"})
    for column in KEEP_COLUMNS:
        if column not in master.columns:
            master[column] = pd.NA
    for column in DATE_COLUMNS:
        master[column] = pd.to_datetime(master[column], errors="coerce")
    return master[KEEP_COLUMNS]


def read_sheet(path: Path, sheet_name: str):
    frame = pd.read_excel(path, sheet_name=sheet_name, dtype={"id": "string"})
    missing = sorted(REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        raise ImportValidationError(
            f"Sheet '{sheet_name}' is missing required columns: {', '.join(missing)}"
        )
    for column in KEEP_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame = frame[KEEP_COLUMNS].copy()
    frame["source_sheet"] = sheet_name
    ids = frame["id"].astype("string").str.strip()
    invalid_id = ids.isna() | ids.eq("")
    # A stable id is the only field required to preserve/upsert a record.
    # Some genuine historic rows have no direction or queue timestamp; retain
    # them in the source of truth and let directional/date charts exclude them.
    invalid = invalid_id
    rejected = []
    for index in frame.index[invalid]:
        reasons = []
        if invalid_id.loc[index]: reasons.append("missing id")
        rejected.append({"sheet": sheet_name, "excel_row": int(index) + 2, "reasons": reasons})
    frame = frame.loc[~invalid].copy()
    frame["id"] = frame["id"].astype("string").str.strip()
    for column in DATE_COLUMNS:
        frame[column] = pd.to_datetime(frame[column], errors="coerce")
    frame["wait_time"] = pd.to_numeric(frame["wait_time"], errors="coerce")
    return frame, rejected


def read_workbook(path: Path) -> WorkbookRead:
    if path.suffix.lower() != ".xlsx":
        raise ImportValidationError("Only .xlsx workbooks are accepted")
    try:
        available = set(pd.ExcelFile(path).sheet_names)
    except Exception as exc:
        raise ImportValidationError(f"Cannot open workbook: {exc}") from exc
    missing = sorted(set(SOURCE_SHEETS) - available)
    if missing:
        raise ImportValidationError(f"Workbook is missing required sheets: {', '.join(missing)}")
    frames, rejected, counts = [], [], {}
    for sheet in SOURCE_SHEETS:
        frame, sheet_rejected = read_sheet(path, sheet)
        counts[sheet] = len(frame) + len(sheet_rejected)
        frames.append(frame)
        rejected.extend(sheet_rejected)
    if frames[0].empty:
        raise ImportValidationError(
            "Sheet 'historic' contains no valid records; snapshots were not replaced"
        )
    combined = pd.concat(frames, ignore_index=True)
    before = len(combined)
    combined["_priority"] = combined["source_sheet"].map(SHEET_PRIORITY)
    combined = combined.sort_values("_priority").drop_duplicates("id", keep="last")
    return WorkbookRead(combined.drop(columns="_priority"), counts, rejected, before - len(combined))


def merge(master: pd.DataFrame, incoming: pd.DataFrame, ingested_at: str):
    master, incoming = master.copy(), incoming.copy()
    incoming["ingested_at"] = ingested_at
    old_snapshot_count = int(master["source_sheet"].isin(SNAPSHOT_SHEETS).sum())
    persistent = master.loc[~master["source_sheet"].isin(SNAPSHOT_SHEETS)].copy()
    persistent_ids = set(persistent["id"].dropna().astype(str))
    incoming_history = incoming.loc[~incoming["source_sheet"].isin(SNAPSHOT_SHEETS)]
    incoming_history_ids = set(incoming_history["id"].dropna().astype(str))
    updated = len(persistent_ids & incoming_history_ids)
    combined = incoming.copy() if persistent.empty else pd.concat([persistent, incoming], ignore_index=True)
    combined["_priority"] = combined["source_sheet"].map(SHEET_PRIORITY).fillna(0)
    combined["_fresh"] = combined["ingested_at"].eq(ingested_at).astype(int)
    combined = combined.sort_values(["_priority", "_fresh"]).drop_duplicates("id", keep="last")
    combined = combined.drop(columns=["_priority", "_fresh"])[KEEP_COLUMNS]
    combined = combined.sort_values(["queue_arrival_time", "id"], na_position="last").reset_index(drop=True)
    return combined, {
        "existing_snapshot_rows_replaced": old_snapshot_count,
        "historic_records_added": len(incoming_history_ids - persistent_ids),
        "historic_records_updated": updated,
        "snapshot_rows_loaded": int(incoming["source_sheet"].isin(SNAPSHOT_SHEETS).sum()),
        "final_master_rows": len(combined),
    }


def write_master_atomic(frame: pd.DataFrame, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def process_workbook(path: Path, master_path: Path, report_path: Path):
    started = datetime.now(timezone.utc)
    master = load_master(master_path)
    result = read_workbook(path)
    merged, stats = merge(master, result.rows, started.isoformat())
    write_master_atomic(merged, master_path)
    report = {
        "status": "success", "workbook": path.name,
        "imported_at_utc": started.isoformat(), "sheet_rows_received": result.sheet_counts,
        "rows_accepted": len(result.rows), "rows_rejected": len(result.rejected_rows),
        "rejected_row_details": result.rejected_rows[:50],
        "duplicates_within_upload": result.duplicates_within_upload, **stats,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbooks", nargs="+", type=Path)
    parser.add_argument("--master", type=Path, default=MASTER_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    args = parser.parse_args(argv)
    for workbook in args.workbooks:
        try:
            print(json.dumps(process_workbook(workbook, args.master, args.report), indent=2))
        except ImportValidationError as exc:
            print(f"IMPORT REJECTED: {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
