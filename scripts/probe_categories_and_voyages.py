"""
Round 2: the Attributes check (round 1) confirmed Vortexa has no native
Panamax/Neopanamax vessel-class taxonomy — "SUPER" entries found there
were ice-class notations (BV/LR "1A Super"), unrelated to Panama Canal
categories. So PCA's Regular/Super/Panamax Plus/Neopanamax categories
(defined by beam/draft) can't be replicated via Vortexa's DWT-only
filters — that path is closed.

This script re-tests VoyagesSearchEnriched with the REAL valid column
names — taken verbatim from the 400 validation error the API returned
in round 1, not guessed — to see real per-voyage records including
`waiting_time`, `waiting_commence`, `waiting_finished`, which could
replace VoyagesCongestionBreakdown's port-level aggregation entirely
with genuine per-vessel data.
"""

from datetime import datetime, timedelta

from vortexasdk import Geographies, VoyagesSearchEnriched


def find_panama_canal_id():
    df = Geographies().search(term="panama").to_df()
    exact = df[df["name"] == "Panama Canal"]
    return exact.iloc[0]["id"] if len(exact) else None


def check_voyages_search_enriched(panama_id):
    print("--- VoyagesSearchEnriched: historical voyage list test (round 2) ---")
    print("Using CONFIRMED valid column names from the API's own 400 error response.\n")
    now = datetime.utcnow()
    one_eighty_days_ago = now - timedelta(days=180)

    # These are the REAL valid columns, taken verbatim from the API's own
    # validation error in round 1 — not guessed.
    real_columns = [
        "vessel_name", "imo", "dwt", "vessel_class", "voyage_status",
        "start_date", "end_date", "location", "congestion_port",
        "waiting_time", "waiting_commence", "waiting_finished", "duration",
    ]

    try:
        result = VoyagesSearchEnriched().search(
            time_min=one_eighty_days_ago,
            time_max=now,
            locations=panama_id,
            vessel_dwt_min=86_000,
            vessel_dwt_max=97_000,  # wide enough to cover both target bands at once
            columns=real_columns,
        )
        df = result.to_df()
        print(f"{len(df)} voyage records returned")
        print("Columns:", list(df.columns))
        if len(df):
            print(df.to_string())
    except Exception as e:  # noqa: BLE001
        print(f"ERROR ({type(e).__name__}) — {e}")
    print()


def main():
    panama_id = find_panama_canal_id()
    if panama_id:
        check_voyages_search_enriched(panama_id)
    else:
        print("Could not find Panama Canal geography ID — skipping voyage list test.")


if __name__ == "__main__":
    main()
