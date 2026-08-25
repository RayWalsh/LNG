"""
Cristobal (Atlantic side) and Balboa (Pacific side) are on opposite ends
of the canal. If a vessel that shows up waiting at Cristobal genuinely
transited, it should appear at/near Balboa within roughly a day or so
afterward (canal transit itself typically takes under 24h once a vessel
enters). This pulls the FULL voyage history (no location filter) for
the specific vessels we already saw at Cristobal, by IMO, and scans
every LOCATION / ARRIVAL DATES / DEPARTURE DATES value for any mention
of Balboa — real cross-referenced evidence of a completed transit,
not just an assumption from trade-pattern reasoning.
"""

from datetime import datetime, timedelta

from vortexasdk import VoyagesSearchEnriched

# IMOs of vessels seen waiting at Cristobal with real congestion/waiting
# data, from the previous probe run.
CRISTOBAL_VESSEL_IMOS = [
    "9693161",  # SK AUDACE
    "9342487",  # SEAPEAK MAGELLAN
    "9937945",  # PUTERI SAADONG
    "9636735",  # PALU LNG
    "9758064",  # BW TULIP
    "9413327",  # BW CLEAR SKY
]


def main():
    now = datetime.utcnow()
    window_start = now - timedelta(days=400)  # a little over a year, to be safe

    real_columns = [
        "vessel_name", "imo", "voyage_status",
        "start_date", "end_date", "location",
        "arrival_dates", "departure_dates",
        "congestion_port", "waiting_time",
    ]

    print(f"--- Full voyage history for {len(CRISTOBAL_VESSEL_IMOS)} Cristobal-seen vessels (no location filter) ---\n")

    try:
        df = VoyagesSearchEnriched().search(
            time_min=window_start,
            time_max=now,
            vessels=CRISTOBAL_VESSEL_IMOS,
            columns=real_columns,
        ).to_df()
        print(f"{len(df)} total voyage legs returned across all {len(CRISTOBAL_VESSEL_IMOS)} vessels\n")
        print(df.to_string())

        print("\n--- Rows mentioning 'Balboa' anywhere (LOCATION / ARRIVAL / DEPARTURE) ---")
        text_cols = [c for c in df.columns if any(
            k in c.upper() for k in ["LOCATION", "ARRIVAL", "DEPARTURE"]
        )]
        mask = df[text_cols].apply(
            lambda row: row.astype(str).str.contains("Balboa", case=False, na=False).any(),
            axis=1,
        )
        balboa_rows = df[mask]
        print(f"{len(balboa_rows)} rows mention Balboa")
        if len(balboa_rows):
            print(balboa_rows.to_string())
        else:
            print("No mentions of Balboa found in any column for these vessels in this window.")

    except Exception as e:  # noqa: BLE001
        print(f"ERROR ({type(e).__name__}) — {e}")


if __name__ == "__main__":
    main()
