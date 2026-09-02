import sys
import unittest
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1]))
from scripts.ingest_vortexa_report import KEEP_COLUMNS, merge


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


if __name__ == "__main__": unittest.main()
