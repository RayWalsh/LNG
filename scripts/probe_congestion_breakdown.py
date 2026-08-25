"""
Follow-up probe, round 3: fixed a parameter-name mix-up. The previous
attempt used `congestion_target_location`, which belongs to
VoyagesSearchEnriched/VoyagesTimeseries — NOT VoyagesCongestionBreakdown.
Checking VoyagesCongestionBreakdown's actual captured signature, the
real parameter for filtering to a specific place is plain `locations`.
This version uses that instead.
"""

from datetime import datetime, timedelta

from vortexasdk import Geographies, VoyagesCongestionBreakdown

CAPACITY_BANDS_CBM = {
    "84k CBM LPG — Panamax": (82_000, 86_000),
    "88k CBM LPG — Super Panamax": (86_001, 90_000),
    "95k CBM LPG — Neo Panamax": (93_000, 97_000),
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


def test_panama_by_capacity_band(location_value):
    now = datetime.utcnow()
    ninety_days_ago = now - timedelta(days=90)

    # IMPORTANT AMBIGUITY TO RESOLVE: with breakdown_property left at its
    # default ('port'), results came back grouped by LOADING port
    # (Sabine Pass, Cameron, etc.), not by "Panama Canal" itself. That
    # leaves it genuinely unclear whether avg_waiting_time measures wait
    # AT THE CANAL specifically, or general port/loading queue time for
    # voyages that happen to route through Panama. Try a few plausible
    # breakdown_property values to see if any produces "Panama Canal"
    # itself as the location label — that would confirm we're measuring
    # the right thing.
    breakdown_property_candidates = ["port", "waypoint", "location", "canal", "chokepoint"]

    for band_label, (capacity_min, capacity_max) in CAPACITY_BANDS_CBM.items():
        for bp in breakdown_property_candidates:
            print(f"--- Panama Canal congestion, {band_label} ({capacity_min}-{capacity_max} CBM), breakdown_property={bp!r} ---")
            try:
                df = VoyagesCongestionBreakdown().search(
                    time_min=ninety_days_ago,
                    time_max=now,
                    locations=location_value,
                    vessel_cubic_capacity_min=capacity_min,
                    vessel_cubic_capacity_max=capacity_max,
                    breakdown_property=bp,
                ).to_df()
                print(f"{len(df)} rows")
                if len(df) and "location_details.0.label" in df.columns:
                    print("Location labels:", df["location_details.0.label"].tolist())
                elif len(df):
                    print(df.to_string())
            except Exception as e:  # noqa: BLE001
                print(f"ERROR ({type(e).__name__}) — {e}")
            print()


def main():
    panama_canal_id = find_panama_canal_waypoint()

    if panama_canal_id is None:
        print("Could not find a 'Panama Canal' waypoint in Geographies — stopping here.")
        return

    print(f"Using locations={panama_canal_id!r} (Panama Canal waypoint)\n")
    test_panama_by_capacity_band(panama_canal_id)


if __name__ == "__main__":
    main()
