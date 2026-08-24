"""
Follow-up probe, round 3.

VesselPositions is now conclusively answered — DENIED (explicit 403
permissions_error) — so it's dropped from this round entirely.

The four Voyages* endpoints failed in round 2 not because of a
permissions issue but because of a real quirk in their signatures:
vessel_wait_time_min/_max are typed Optional[int] (a wait-time-in-hours
THRESHOLD filter) despite matching the same "contains 'time', ends in
_min/_max" naming pattern as genuine date-range parameters like
time_min/time_max. This version checks each parameter's real type
annotation (not just its name) to tell the two apart, and leaves the
int-typed threshold params untouched at their default.
"""

import inspect
from datetime import datetime, timedelta

from vortexasdk import (
    VoyagesCongestionBreakdown,
    VoyagesSearchEnriched,
    VoyagesTimeseries,
    VoyagesTopHits,
)

TARGET_CLASSES = [
    ("VoyagesCongestionBreakdown", VoyagesCongestionBreakdown),
    ("VoyagesSearchEnriched", VoyagesSearchEnriched),
    ("VoyagesTimeseries", VoyagesTimeseries),
    ("VoyagesTopHits", VoyagesTopHits),
]


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def build_kwargs_for(search_method, now, week_ago):
    """
    Inspect the REAL signature and fill in only genuine time-window
    parameters — using each parameter's REAL TYPE ANNOTATION to decide
    how to fill it in, not just its name. This matters because these
    endpoints mix two different things that both happen to match a
    naive "contains 'time', ends in _min/_max" name filter:

      - real date-range boundaries (e.g. time_min/time_max), which on
        some endpoints are typed datetime.datetime (want a real
        datetime object) and on others typed Optional[str] (want an
        ISO string) — VesselPositions vs the Voyages family disagree
        with each other here, confirmed empirically.
      - vessel_wait_time_min/_max, which are typed Optional[int] — a
        wait-time-in-hours THRESHOLD filter, not a date range at all.
        These must be left at their default (None), not filled in.

    Returns None if some other required (no-default) parameter can't be
    safely guessed.
    """
    sig = inspect.signature(search_method)
    kwargs = {}
    for pname, param in sig.parameters.items():
        if pname == "self":
            continue
        has_default = param.default is not inspect.Parameter.empty
        looks_like_time_window = "time" in pname and (
            pname.endswith("_min") or pname.endswith("_max")
        )
        ann_str = str(param.annotation)

        if looks_like_time_window:
            if "int" in ann_str:
                # e.g. vessel_wait_time_min: Optional[int] — a threshold
                # filter, not a date. Leave at default, don't touch it.
                continue
            elif "datetime" in ann_str:
                kwargs[pname] = week_ago if pname.endswith("_min") else now
            elif "str" in ann_str:
                kwargs[pname] = iso(week_ago) if pname.endswith("_min") else iso(now)
            # else: unrecognised annotation shape — leave at default
            # rather than guess wrong.
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
    except Exception as e:  # noqa: BLE001 - deliberately broad, this is a diagnostic script
        msg = str(e)
        if "403" in msg or "401" in msg or "permission" in msg.lower():
            print(f"DENIED — {msg}")
        else:
            print(f"ERROR ({type(e).__name__}) — {msg}")
    print()


def main():
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)

    for label, cls in TARGET_CLASSES:
        probe(label, cls, now, week_ago)


if __name__ == "__main__":
    main()
