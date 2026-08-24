"""
Follow-up probe, round 2: the first attempt at fixing these five
endpoints (VesselPositions, VoyagesCongestionBreakdown,
VoyagesSearchEnriched, VoyagesTimeseries, VoyagesTopHits) guessed wrong
parameter names by hand. This version inspects each endpoint's REAL
search() signature (inspect.signature) instead of guessing, which
revealed: VesselPositions explicitly types its time params as
Optional[str], and the Voyages* family — despite a datetime.datetime
type hint — throws a JSON-serialization TypeError when given a real
datetime object. So this version passes ISO-formatted strings for every
time-window parameter it finds via introspection, which matches what
these endpoints actually expect empirically.

CargoMovements is intentionally NOT re-tested here — it already
returned a clean, real answer in the previous run (30,509 rows, 9
columns, none of them canal/waypoint-related), so there's nothing left
to learn by re-running it.
"""

import inspect
from datetime import datetime, timedelta

from vortexasdk import (
    VesselPositions,
    VoyagesCongestionBreakdown,
    VoyagesSearchEnriched,
    VoyagesTimeseries,
    VoyagesTopHits,
)

TARGET_CLASSES = [
    ("VesselPositions", VesselPositions),
    ("VoyagesCongestionBreakdown", VoyagesCongestionBreakdown),
    ("VoyagesSearchEnriched", VoyagesSearchEnriched),
    ("VoyagesTimeseries", VoyagesTimeseries),
    ("VoyagesTopHits", VoyagesTopHits),
]


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def build_kwargs_for(search_method, now, week_ago):
    """Inspect the REAL signature and fill in only the obviously
    time-range-shaped parameters. These five endpoints' internal
    serialization chokes on raw datetime objects (confirmed empirically —
    even params type-hinted as datetime.datetime throw a JSON
    serialization TypeError), so we pass ISO-formatted strings instead,
    matching what VesselPositions explicitly types as Optional[str].
    Returns None if some other required parameter can't be safely
    guessed."""
    sig = inspect.signature(search_method)
    kwargs = {}
    for pname, param in sig.parameters.items():
        if pname == "self":
            continue
        has_default = param.default is not inspect.Parameter.empty
        looks_like_time_window = "time" in pname and (
            pname.endswith("_min") or pname.endswith("_max")
        )
        if looks_like_time_window:
            kwargs[pname] = iso(week_ago) if pname.endswith("_min") else iso(now)
        elif not has_default:
            return None
    return kwargs


def probe(label, cls, now, week_ago):
    print(f"--- {label} ---")
    instance = cls()

    sig = inspect.signature(instance.search)
    print(f"Real search() signature: {sig}")

    kwargs = build_kwargs_for(instance.search, now, week_ago)
    if kwargs is None:
        print("SKIPPED — requires a specific argument that can't be safely guessed")
        print()
        return

    print(f"Calling with: {kwargs}")
    try:
        df = instance.search(**kwargs).to_df()
        print(f"ACCESSIBLE — {len(df)} rows")
        if len(df):
            cols = list(df.columns)
            print(f"Columns ({len(cols)}):", cols[:20], "..." if len(cols) > 20 else "")
    except ValueError as e:
        msg = str(e)
        if "403" in msg or "401" in msg or "permission" in msg.lower():
            print(f"DENIED — {msg}")
        else:
            print(f"ERROR (ValueError) — {msg}")
    except Exception as e:  # noqa: BLE001
        print(f"ERROR ({type(e).__name__}) — {e}")
    print()


def main():
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    day_ago = now - timedelta(days=1)

    for label, cls in TARGET_CLASSES:
        window = (day_ago, now) if label == "VesselPositions" else (week_ago, now)
        probe(label, cls, window[1], window[0])


if __name__ == "__main__":
    main()
