"""
Follow-up probe: the endpoints that came back ERROR (not ACCESSIBLE or
DENIED) in the first audit run failed because of a bug in this script,
not a real API response — it was passing raw Python datetime objects
where the SDK/API expected ISO-formatted strings, causing a local
JSON-serialization crash before the request even reached Vortexa.

This script fixes that (converts datetimes to ISO strings explicitly)
and retests just those endpoints, so we get a real ACCESSIBLE/DENIED
answer instead of an inconclusive one.

Also prints the full column list of a couple of real CargoMovements
rows, so we can visually check whether any column hints at canal/transit
waypoint data riding along on the cargo movement record itself.
"""

from datetime import datetime, timedelta

from vortexasdk import CargoMovements, VesselPositions, VoyagesCongestionBreakdown, VoyagesSearchEnriched, VoyagesTimeseries, VoyagesTopHits


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def try_endpoint(label, fn):
    print(f"--- {label} ---")
    try:
        result = fn()
        df = result.to_df()
        print(f"ACCESSIBLE — {len(df)} rows")
        if len(df):
            print("Columns:", list(df.columns)[:20], "..." if len(df.columns) > 20 else "")
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

    # --- Retest the previously-erroring endpoints with proper ISO strings ---

    try_endpoint(
        "VesselPositions (last 1 day, tiny window since position data is huge)",
        lambda: VesselPositions().search(
            filter_time_min=iso(day_ago),
            filter_time_max=iso(now),
        ),
    )

    try_endpoint(
        "VoyagesCongestionBreakdown (last 7 days)",
        lambda: VoyagesCongestionBreakdown().search(
            filter_time_min=iso(week_ago),
            filter_time_max=iso(now),
        ),
    )

    try_endpoint(
        "VoyagesSearchEnriched (last 7 days)",
        lambda: VoyagesSearchEnriched().search(
            filter_time_min=iso(week_ago),
            filter_time_max=iso(now),
        ),
    )

    try_endpoint(
        "VoyagesTimeseries (last 7 days)",
        lambda: VoyagesTimeseries().search(
            filter_time_min=iso(week_ago),
            filter_time_max=iso(now),
        ),
    )

    try_endpoint(
        "VoyagesTopHits (last 7 days)",
        lambda: VoyagesTopHits().search(
            filter_time_min=iso(week_ago),
            filter_time_max=iso(now),
        ),
    )

    # --- Inspect real CargoMovements columns for anything canal-related ---

    print("--- CargoMovements: full column list (last 30 days, size=5) ---")
    try:
        df = CargoMovements().search(
            filter_time_min=iso(now - timedelta(days=30)),
            filter_time_max=iso(now),
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
