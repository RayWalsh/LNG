"""
Follow-up probe: the endpoints that came back ERROR (not ACCESSIBLE or
DENIED) in the first audit run failed because of a bug in the ORIGINAL
audit script's datetime handling. This version fixes that properly by
inspecting each endpoint's REAL search() signature (inspect.signature —
same approach that correctly identified CanalTransit's real params
earlier) instead of guessing parameter names, and uses real Python
datetime objects throughout (confirmed working for CargoMovements in
the original full audit — 14,271 rows returned that way).

Also prints the full column list of a couple of real CargoMovements
rows, so we can visually check whether any column hints at canal/transit
waypoint data riding along on the cargo movement record itself.
"""

import inspect
from datetime import datetime, timedelta

from vortexasdk import (
    CargoMovements,
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


def build_kwargs_for(search_method, now, week_ago):
    """Inspect the REAL signature and fill in only the obviously
    time-range-shaped parameters, using real datetime objects. Returns
    None if some other required parameter can't be safely guessed."""
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
            kwargs[pname] = week_ago if pname.endswith("_min") else now
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

    for label, cls in TARGET_CLASSES:
        probe(label, cls, now, week_ago)

    # --- Inspect real CargoMovements columns for anything canal-related ---
    # Uses real datetime objects, matching what already worked in the
    # original full audit (14,271 rows returned there).

    print("--- CargoMovements: full column list (last 30 days) ---")
    try:
        df = CargoMovements().search(
            filter_time_min=now - timedelta(days=30),
            filter_time_max=now,
        ).to_df()
        print(f"{len(df)} rows returned. All columns:")
        for col in df.columns:
            flag = "  <-- possible canal/waypoint field" if any(
                kw in col.lower() for kw in ["canal", "waypoint", "queue", "transit", "panama"]
            ) else ""
            print(f"  {col}{flag}")
    except Exception as e:  # noqa: BLE001
        print(f"ERROR — {e}")


if __name__ == "__main__":
    main()
