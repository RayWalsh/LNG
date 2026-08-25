"""
New angle: instead of the generic "Panama Canal" waypoint (which we've
confirmed doesn't isolate canal-specific wait time from other port
congestion), try Balboa (Pacific-side anchorage) and Cristobal
(Atlantic-side anchorage) directly — the actual entry/exit points ships
wait at before transiting. If Vortexa tracks port-call arrival/departure
at these two specific locations, the gap between them could reconstruct
genuine transit wait time.
"""

from datetime import datetime, timedelta

from vortexasdk import Geographies, VoyagesSearchEnriched


def find_geography(term, exact_names):
    df = Geographies().search(term=term).to_df()
    print(f"--- Geographies matching '{term}' ---")
    print(f"{len(df)} matches")
    if len(df):
        cols = [c for c in ["id", "name", "layer"] if c in df.columns]
        print(df[cols].to_string())
    print()

    for name in exact_names:
        exact = df[df["name"] == name]
        if len(exact):
            return exact.iloc[0]["id"], exact.iloc[0]["name"]
    return None, None


def test_location(location_id, location_name):
    print(f"--- VoyagesSearchEnriched: voyages at {location_name!r} (last 180 days, wide DWT) ---")
    now = datetime.utcnow()
    window_start = now - timedelta(days=180)

    real_columns = [
        "vessel_name", "imo", "dwt", "vessel_class", "voyage_status",
        "start_date", "end_date", "location", "congestion_port",
        "waiting_time", "waiting_commence", "waiting_finished", "duration",
        "arrival_dates", "departure_dates",
    ]

    try:
        df = VoyagesSearchEnriched().search(
            time_min=window_start,
            time_max=now,
            locations=location_id,
            vessel_dwt_min=80_000,   # widened on purpose to see ANY traffic here first
            vessel_dwt_max=100_000,
            columns=real_columns,
        ).to_df()
        print(f"{len(df)} voyage records")
        print("Columns:", list(df.columns))
        if len(df):
            print(df.to_string())
    except Exception as e:  # noqa: BLE001
        print(f"ERROR ({type(e).__name__}) — {e}")
    print()


def main():
    balboa_id, balboa_name = find_geography("balboa", ["Balboa"])
    cristobal_id, cristobal_name = find_geography("cristobal", ["Cristobal"])

    if balboa_id:
        test_location(balboa_id, balboa_name)
    else:
        print("Could not find an exact 'Balboa' geography match.\n")

    if cristobal_id:
        test_location(cristobal_id, cristobal_name)
    else:
        print("Could not find an exact 'Cristobal' geography match.\n")


if __name__ == "__main__":
    main()
