import sys
import tempfile
import unittest
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.ingest_vortexa_report import KEEP_COLUMNS, merge, read_workbook, reject_stale_report


def row(identifier, sheet, vessel="VESSEL"):
    values = {column: pd.NA for column in KEEP_COLUMNS}
    values.update({"id": identifier, "vessel_name": vessel,
                   "queue_arrival_time": pd.Timestamp("2026-08-01"),
                   "direction": "northbound", "lock": "neo_panamax",
                   "source_sheet": sheet})
    return values


class MergeTests(unittest.TestCase):
    def test_replaces_snapshots_and_preserves_history(self):
        master = pd.DataFrame([row("h1", "historic"), row("w-old", "waiting"), row("f-old", "future")])
        incoming = pd.DataFrame([row("h2", "historic"), row("w-new", "waiting")])
        merged, stats = merge(master, incoming, "2026-09-01T00:00:00+00:00")
        self.assertEqual(set(merged.id), {"h1", "h2", "w-new"})
        self.assertEqual(stats["existing_snapshot_rows_replaced"], 2)

    def test_historic_outranks_conflicting_future(self):
        master = pd.DataFrame([row("same", "historic", "COMPLETED")])
        incoming = pd.DataFrame([row("same", "future", "PLANNED")])
        merged, _ = merge(master, incoming, "2026-09-01T00:00:00+00:00")
        self.assertEqual(merged.iloc[0].vessel_name, "COMPLETED")


class WorkbookSafetyTests(unittest.TestCase):
    def test_older_report_is_rejected(self):
        master = pd.DataFrame([row("current", "waiting")])
        master["report_timestamp"] = "2026-08-31T00:00:00+00:00"
        with self.assertRaisesRegex(ValueError, "older than the latest accepted"):
            reject_stale_report(master, pd.Timestamp("2026-08-30T00:00:00+00:00"))

    def test_same_day_correction_is_allowed(self):
        master = pd.DataFrame([row("current", "waiting")])
        master["report_timestamp"] = "2026-08-31T00:00:00+00:00"
        reject_stale_report(master, pd.Timestamp("2026-08-31T00:00:00+00:00"))

    def test_empty_historic_sheet_is_rejected(self):
        columns = [column for column in KEEP_COLUMNS if column not in {"source_sheet", "ingested_at"}]
        with tempfile.TemporaryDirectory() as directory:
            workbook = Path(directory) / "empty.xlsx"
            with pd.ExcelWriter(workbook) as writer:
                welcome = pd.DataFrame([[pd.NA] * 2 for _ in range(6)])
                welcome.iloc[5, 1] = pd.Timestamp("2026-08-31")
                welcome.to_excel(writer, sheet_name="Welcome!", index=False, header=False)
                for sheet in ("historic", "waiting", "future"):
                    pd.DataFrame(columns=columns).to_excel(writer, sheet_name=sheet, index=False)
            with self.assertRaisesRegex(ValueError, "no valid records"):
                read_workbook(workbook)


if __name__ == "__main__": unittest.main()
