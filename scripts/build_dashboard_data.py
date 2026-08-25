"""
Build site/panama_wait_times.json from data/master_transits.csv — the
persistent dataset built by ingest_vortexa_report.py from real Vortexa
Panama Canal Report exports.

Unlike everything tried earlier this session (VoyagesCongestionBreakdown,
Cristobal port-call data, etc.), this is genuine per-transit data with a
real `direction` field (not a Laden/Ballast proxy) and real
queue_arrival_time / canal_entry_time — so all of the following are now
properly computable, not approximated:

  - current average wait time by DWT band, by real direction
  - weekly trend over the past year
  - a genuine 5-year seasonal range (the master dataset spans back to
    2020, not just the past year)
  - a REAL live queue — actual named vessels currently waiting, from
    the 'waiting' sheet, not an empty placeholder
"""

import os
import json
from datetime import datetime, timedelta, timezone

import pandas as pd

MASTER_PATH = os.environ.get("MASTER_TRANSITS_PATH", "data/master_transits.csv")
OUTPUT_JSON = os.environ.get("OUTPUT_JSON_PATH", "site/panama_wait_times.json")

DWT_BANDS = {
    "88k DWT LNG": (86_000, 90_000),
    "95k DWT LNG": (93_000, 97_000),
}

CURRENT_WINDOW_DAYS = 30
PAST_YEAR_DAYS = 364


def load_master():
    df = pd.read_csv(MASTER_PATH, parse_dates=[
        "queue_arrival_time", "canal_entry_time", "canal_exit_time", "booked_date",
    ])
    return df


def filter_band(df, dwt_min, dwt_max):
    return df[
        df["vessel_deadweight"].notna()
        & (df["vessel_deadweight"] >= dwt_min)
        & (df["vessel_deadweight"] <= dwt_max)
    ]


def completed_transits(df):
    """Rows with a real, completed wait — i.e. canal_entry_time is set
    (so the transit actually started, not still queuing/future)."""
    return df[df["canal_entry_time"].notna() & df["wait_time"].notna()]


def summarise_current(df, dwt_min, dwt_max):
    now = pd.Timestamp.now('UTC').tz_localize(None)
    window_start = now - timedelta(days=CURRENT_WINDOW_DAYS)

    band = filter_band(completed_transits(df), dwt_min, dwt_max)
    band = band[band["canal_entry_time"] >= window_start]

    result = {
        "dwt_range": [dwt_min, dwt_max],
        "window_days": CURRENT_WINDOW_DAYS,
        "n_transits": int(len(band)),
        "avg_wait_days": None,
        "by_direction": {},
    }
    if len(band):
        result["avg_wait_days"] = round(float(band["wait_time"].mean()), 2)
        for direction, dgroup in band.groupby("direction"):
            result["by_direction"][direction.capitalize()] = {
                "n_transits": int(len(dgroup)),
                "avg_wait_days": round(float(dgroup["wait_time"].mean()), 2),
            }
    return result


def summarise_weekly(df, dwt_min, dwt_max):
    now = pd.Timestamp.now('UTC').tz_localize(None)
    cutoff = now - timedelta(days=PAST_YEAR_DAYS)

    band = filter_band(completed_transits(df), dwt_min, dwt_max)
    band = band[band["canal_entry_time"] >= cutoff].copy()

    band["week_start"] = band["canal_entry_time"].dt.to_period("W-SUN").dt.start_time
    band["week_of_year"] = band["canal_entry_time"].dt.isocalendar().week.astype(int)

    weeks = []
    for week_start, wgroup in band.groupby("week_start"):
        entry = {
            "week_start": week_start.date().isoformat(),
            "week_of_year": int(wgroup["week_of_year"].iloc[0]),
            "n_transits": int(len(wgroup)),
            "avg_wait_days": round(float(wgroup["wait_time"].mean()), 2),
            "by_direction": {},
        }
        for direction, dgroup in wgroup.groupby("direction"):
            entry["by_direction"][direction.capitalize()] = {
                "n_transits": int(len(dgroup)),
                "avg_wait_days": round(float(dgroup["wait_time"].mean()), 2),
            }
        weeks.append(entry)

    weeks.sort(key=lambda w: w["week_start"])
    return weeks


def summarise_seasonal_range(df, dwt_min, dwt_max):
    """Real 5-year seasonal range — finally genuinely computable, since
    the master dataset's historic sheet goes back to 2020."""
    now = pd.Timestamp.now('UTC').tz_localize(None)
    cutoff = now - timedelta(days=PAST_YEAR_DAYS)

    band = filter_band(completed_transits(df), dwt_min, dwt_max)
    band = band[band["canal_entry_time"] < cutoff].copy()  # everything OLDER than the past year

    if not len(band):
        return []

    iso = band["canal_entry_time"].dt.isocalendar()
    band["iso_year"] = iso.year.astype(int)
    band["week_of_year"] = iso.week.astype(int)

    per_year_week = (
        band.groupby(["iso_year", "week_of_year"])["wait_time"]
        .mean()
        .reset_index()
    )

    weeks = []
    for wk, wgroup in per_year_week.groupby("week_of_year"):
        weeks.append({
            "week_of_year": int(wk),
            "n_years": int(wgroup["iso_year"].nunique()),
            "min_days": round(float(wgroup["wait_time"].min()), 2),
            "max_days": round(float(wgroup["wait_time"].max()), 2),
            "avg_days": round(float(wgroup["wait_time"].mean()), 2),
        })

    weeks.sort(key=lambda w: w["week_of_year"])
    return weeks


def current_queue(df, dwt_min, dwt_max):
    """REAL live queue, from the 'waiting' sheet — actual named vessels
    currently waiting, not an empty placeholder."""
    band = filter_band(df, dwt_min, dwt_max)
    waiting = band[band["source_sheet"] == "waiting"].copy()

    if not len(waiting):
        return []

    now = pd.Timestamp.now('UTC').tz_localize(None)
    waiting["hours_waiting_so_far"] = (
        now - waiting["queue_arrival_time"]
    ).dt.total_seconds() / 3600

    cols = [
        "vessel_name", "vessel_imo", "vessel_deadweight",
        "direction", "lock", "queue_arrival_time", "hours_waiting_so_far",
    ]
    waiting = waiting.sort_values("hours_waiting_so_far", ascending=False)

    records = []
    for _, row in waiting.iterrows():
        records.append({
            "vessel_name": row["vessel_name"],
            "vessel_imo": None if pd.isna(row["vessel_imo"]) else int(row["vessel_imo"]),
            "vessel_dead_weight": None if pd.isna(row["vessel_deadweight"]) else int(row["vessel_deadweight"]),
            "direction": None if pd.isna(row["direction"]) else str(row["direction"]).capitalize(),
            "lock": row["lock"],
            "queue_arrival_time": str(row["queue_arrival_time"]),
            "hours_waiting_so_far": round(float(row["hours_waiting_so_far"]), 1),
        })
    return records


def main():
    print(f"Loading {MASTER_PATH} ...")
    df = load_master()
    print(f"  {len(df)} total rows")

    dwt_bands_out = {}
    weekly_history_out = {}
    seasonal_range_out = {}
    current_queue_out = []

    for label, (dwt_min, dwt_max) in DWT_BANDS.items():
        print(f"\n{label} ({dwt_min:,}-{dwt_max:,} DWT)")

        current = summarise_current(df, dwt_min, dwt_max)
        dwt_bands_out[label] = current
        print(f"  Current ({CURRENT_WINDOW_DAYS}d): {current['n_transits']} transits, "
              f"avg {current['avg_wait_days']} days")

        weekly = summarise_weekly(df, dwt_min, dwt_max)
        weekly_history_out[label] = weekly
        print(f"  Weekly history: {len(weekly)} weeks with data")

        seasonal = summarise_seasonal_range(df, dwt_min, dwt_max)
        seasonal_range_out[label] = seasonal
        print(f"  Seasonal range: {len(seasonal)} week-of-year buckets")

        queue = current_queue(df, dwt_min, dwt_max)
        current_queue_out.extend(queue)
        print(f"  Currently waiting: {len(queue)} vessels")

    current_queue_out.sort(key=lambda v: v["hours_waiting_so_far"], reverse=True)

    output = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_source": "vortexa_panama_canal_report_email",
        "notes": (
            "Sourced from Vortexa's periodic Panama Canal Report email "
            "export (confirmed by Vortexa: no live API access to this "
            "data). Ingested and merged into a persistent master dataset "
            "on each new upload."
        ),
        "current_window_days": CURRENT_WINDOW_DAYS,
        "dwt_bands": dwt_bands_out,
        "weekly_history": weekly_history_out,
        "seasonal_range": seasonal_range_out,
        "current_queue": current_queue_out,
    }

    os.makedirs(os.path.dirname(OUTPUT_JSON) or ".", exist_ok=True)
    with open(OUTPUT_JSON, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\nWrote {OUTPUT_JSON}")


if __name__ == "__main__":
    main()