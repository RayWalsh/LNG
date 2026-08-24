"""
Follow-up probe: VoyagesCongestionBreakdown looks like a genuine
alternative to the denied CanalTransit endpoint — it's accessible, and
its columns (avg_waiting_time, vessel_dwt, location_details.0.label)
are exactly the shape we need. This script:

  1. Searches Geographies (confirmed accessible) for anything matching
     "panama", to find the right geography ID(s) to filter on.
  2. Pulls VoyagesCongestionBreakdown with NO location filter, over a
     wider recent window, and prints every distinct location label that
     comes back — so we can see with our own eyes whether "Panama
     Canal" (or similar) is actually one of the breakdown locations.
  3. If a Panama-like location is found, re-runs the breakdown filtered
     to just that location, once per target DWT band, to see whether
     avg_waiting_time comes back sensibly split by DWT.
"""

from datetime import datetime, timedelta

from vortexasdk import Geographies, VoyagesCongestionBreakdown

DWT_BANDS = {
    "88k DWT LNG": (86_000, 90_000),
    "95k DWT LNG": (93_000, 97_000),
}


def find_panama_geographies():
    print("--- Geographies matching 'panama' ---")
    df = Geographies().search(term="panama").to_df()
    print(f"{len(df)} matches")
    if len(df):
        cols = [c for c in ["id", "name", "layer", "label"] if c in df.columns]
        print(df[cols].to_string())
    print()
    return df


def survey_congestion_locations():
    print("--- VoyagesCongestionBreakdown: distinct locations, last 90 days, no filter ---")
    now = datetime.utcnow()
    df = VoyagesCongestionBreakdown().search(
        time_min=now - timedelta(days=90),
        time_max=now,
        breakdown_size=2000,
    ).to_df()
    print(f"{len(df)} rows total")

    if "location_details.0.label" in df.columns:
        labels = sorted(df["location_details.0.label"].dropna().unique().tolist())
        panama_like = [l for l in labels if "panama" in l.lower()]
        print(f"\n{len(labels)} distinct locations. Panama-like matches: {panama_like}")
        if not panama_like:
            print("\nFirst 30 location labels (for manual inspection):")
            for l in labels[:30]:
                print(f"  {l}")
    print()
    return df


def test_panama_by_dwt_band(location_value):
    now = datetime.utcnow()
    week_ago = now - timedelta(days=90)

    for band_label, (dwt_min, dwt_max) in DWT_BANDS.items():
        print(f"--- Panama congestion, {band_label} ({dwt_min}-{dwt_max} DWT) ---")
        try:
            df = VoyagesCongestionBreakdown().search(
                time_min=week_ago,
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
    geo_df = find_panama_geographies()
    congestion_df = survey_congestion_locations()

    # Best-effort: try congestion_target_location using whatever Panama
    # geography ID we found, if any — this part is exploratory since we
    # don't yet know exactly what congestion_target_location expects
    # (a geography ID? a label string?).
    if len(geo_df) and "id" in geo_df.columns:
        panama_id = geo_df.iloc[0]["id"]
        print(f"Trying congestion_target_location={panama_id!r} (first Geographies match for 'panama')\n")
        test_panama_by_dwt_band(panama_id)


if __name__ == "__main__":
    main()
