"""
Two checks:

1. Does Vortexa's own vessel_class taxonomy include size-based classes
   like "Panamax" / "Neopanamax" that we could filter on directly,
   rather than approximating PCA's beam/draft-based categories via DWT?
   Attributes (confirmed accessible, 94 rows) is the most likely place
   to find this.

2. Can VoyagesSearchEnriched (confirmed accessible, just needs `columns`
   + to_list() instead of to_df()) give us a real historical per-voyage
   list — vessel names, dates, wait time — to replace the permanently-
   empty "Live vessel queue" section with real historical voyages?
"""

from datetime import datetime, timedelta

from vortexasdk import Attributes, Geographies, VoyagesSearchEnriched


def check_vessel_class_taxonomy():
    print("--- Attributes: looking for vessel-class / size-related entries ---")
    df = Attributes().search().to_df()
    print(f"{len(df)} total attributes")
    cols = [c for c in ["id", "name", "category"] if c in df.columns]
    print("Columns available:", list(df.columns))
    print()

    if "name" in df.columns:
        size_like = df[df["name"].str.lower().str.contains(
            "panamax|neopanamax|regular|super", na=False, regex=True
        )]
        print(f"{len(size_like)} entries matching panamax/neopanamax/regular/super:")
        if len(size_like):
            print(size_like[cols].to_string())
    print()


def find_panama_canal_id():
    df = Geographies().search(term="panama").to_df()
    exact = df[df["name"] == "Panama Canal"]
    return exact.iloc[0]["id"] if len(exact) else None


def check_voyages_search_enriched(panama_id):
    print("--- VoyagesSearchEnriched: historical voyage list test ---")
    now = datetime.utcnow()
    ninety_days_ago = now - timedelta(days=90)

    # Request explicit columns so to_list() gives us clean records rather
    # than a raw nested structure. Guessing at likely useful column names
    # based on confirmed field names from elsewhere in the SDK — if any
    # are wrong the API should just ignore or error on them, which will
    # tell us the real names.
    candidate_columns = [
        "vessel.name", "vessel.imo", "vessel.dwt",
        "voyage_status", "start_timestamp", "end_timestamp",
        "vessel_wait_time",
    ]

    try:
        result = VoyagesSearchEnriched().search(
            time_min=ninety_days_ago,
            time_max=now,
            locations=panama_id,
            vessel_dwt_min=86_000,
            vessel_dwt_max=97_000,  # wide enough to cover both target bands at once
            columns=candidate_columns,
        )
        records = result.to_list()
        print(f"{len(records)} voyage records returned")
        for r in records[:5]:
            print(" ", r)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR ({type(e).__name__}) — {e}")
    print()


def main():
    check_vessel_class_taxonomy()
    panama_id = find_panama_canal_id()
    if panama_id:
        check_voyages_search_enriched(panama_id)
    else:
        print("Could not find Panama Canal geography ID — skipping voyage list test.")


if __name__ == "__main__":
    main()
