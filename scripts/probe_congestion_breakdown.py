"""
Follow-up probe, round 2: Geographies search already confirmed a real
"Panama Canal" waypoint geography exists with a specific ID. This
version skips the broad unfiltered congestion survey entirely (it hit a
500 Internal Server Error last time, most likely from an unfiltered,
oversized global query — heavy and unnecessary now that we have the
exact ID we need) and goes straight to testing
VoyagesCongestionBreakdown filtered specifically to the Panama Canal
waypoint, once per target DWT band.
"""

from datetime import datetime, timedelta

from vortexasdk import Geographies, VoyagesCongestionBreakdown

DWT_BANDS = {
    "88k DWT LNG": (86_000, 90_000),
    "95k DWT LNG": (93_000, 97_000),
}


def find_panama_canal_waypoint():
    print("--- Geographies matching 'panama' ---")
    df = Geographies().search(term="panama").to_df()
    print(f"{len(df)} matches")
    if len(df):
        cols = [c for c in ["id", "name", "layer"] if c in df.columns]
        print(df[cols].to_string())
    print()

    if not len(df):
        return None

    # Specifically the "Panama Canal" waypoint, not just any Panama match
    # (the country "Panama" is also in this list and is NOT what we want).
    exact = df[df["name"] == "Panama Canal"]
    if len(exact):
        return exact.iloc[0]["id"]

    # Fallback: anything with "canal" in the name and layer == waypoint
    canal_like = df[df["name"].str.lower().str.contains("canal", na=False)]
    if len(canal_like):
        return canal_like.iloc[0]["id"]

    return None


def test_panama_by_dwt_band(location_value):
    now = datetime.utcnow()
    ninety_days_ago = now - timedelta(days=90)

    for band_label, (dwt_min, dwt_max) in DWT_BANDS.items():
        print(f"--- Panama Canal congestion, {band_label} ({dwt_min}-{dwt_max} DWT) ---")
        try:
            df = VoyagesCongestionBreakdown().search(
                time_min=ninety_days_ago,
                time_max=now,
                congestion_target_location=location_value,
                vessel_dwt_min=dwt_min,
                vessel_dwt_max=dwt_max,
            ).to_df()
            print(f"{len(df)} rows")
            if len(df):
                print(df.to_string())
        except Exception as e:  # noqa: BLE001
            print(f"ERROR ({type(e).__name__}) — {e}")
        print()


def main():
    panama_canal_id = find_panama_canal_waypoint()

    if panama_canal_id is None:
        print("Could not find a 'Panama Canal' waypoint in Geographies — stopping here.")
        return

    print(f"Using congestion_target_location={panama_canal_id!r} (Panama Canal waypoint)\n")
    test_panama_by_dwt_band(panama_canal_id)


if __name__ == "__main__":
    main()
