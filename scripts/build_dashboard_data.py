"""
Build site/panama_wait_times.json from data/master_transits.csv — the
persistent dataset built by ingest_vortexa_report.py from real Vortexa
Panama Canal Report exports.

Unlike everything tried earlier this session (VoyagesCongestionBreakdown,
Cristobal port-call data, etc.), this is genuine per-transit data with a
real `direction` field (not a Laden/Ballast proxy) and real
queue_arrival_time / canal_entry_time — so all of the following are now
properly computable, not approximated:

  - current average wait time by estimated cubic-capacity band and direction
  - weekly trend over the past year
  - a genuine 5-year seasonal range (the master dataset spans back to
    2020, not just the past year)
  - a REAL live queue — actual named vessels currently waiting, from
    the 'waiting' sheet, not an empty placeholder
"""

import os
import json
import re
from datetime import datetime, timedelta, timezone

import pandas as pd

MASTER_PATH = os.environ.get("MASTER_TRANSITS_PATH", "data/master_transits.csv")
OUTPUT_JSON = os.environ.get("OUTPUT_JSON_PATH", "site/panama_wait_times.json")

CAPACITY_BANDS_CBM = {
    "84k CBM LPG — Panamax": (82_000, 86_000),
    "88k CBM LPG — Super Panamax": (86_001, 90_000),
    "95k CBM LPG — Neo Panamax": (93_000, 97_000),
}

CURRENT_WINDOW_DAYS = 30
PAST_YEAR_DAYS = 364


def load_master():
    df = pd.read_csv(MASTER_PATH, parse_dates=[
        "queue_arrival_time", "canal_entry_time", "canal_exit_time", "booked_date",
    ])
    return df


def filter_lpg(df):
    """Keep confirmed LPG vessels only.

    The report explicitly labels these rows as ``LPG Carriers`` in
    ``vessel_type``. ``VLGC/VLEC`` is retained as a fallback for master files
    created before vessel_type was added to the ingestion schema.
    """
    vessel_type = df.get("vessel_type", pd.Series("", index=df.index)).fillna("").astype(str)
    family = df.get("vessel_family", pd.Series("", index=df.index)).fillna("").astype(str)
    is_lpg = vessel_type.str.fullmatch("LPG Carriers", case=False) | family.eq("VLGC/VLEC")
    return df[is_lpg].copy()


def cubic_total(value):
    """Sum parcel volumes stored in strings such as ``[39788. 41160.]``."""
    if pd.isna(value):
        return pd.NA
    numbers = re.findall(r"[-+]?\d*\.?\d+", str(value))
    return sum(float(number) for number in numbers) if numbers else pd.NA


def add_estimated_capacity(df):
    """Use each vessel's maximum observed cargo volume as a capacity proxy."""
    df = df.copy()
    cubic_values = df.get("cubic_metres", pd.Series(pd.NA, index=df.index))
    df["observed_cubic_metres"] = cubic_values.map(cubic_total)
    by_imo = df.groupby("vessel_imo", dropna=True)["observed_cubic_metres"].transform("max")
    by_name = df.groupby("vessel_name", dropna=True)["observed_cubic_metres"].transform("max")
    df["estimated_capacity_cbm"] = by_imo.fillna(by_name)
    return df


def filter_band(df, capacity_min, capacity_max):
    return df[
        df["estimated_capacity_cbm"].notna()
        & (df["estimated_capacity_cbm"] >= capacity_min)
        & (df["estimated_capacity_cbm"] <= capacity_max)
    ]


def completed_transits(df):
    """Rows with a real, completed wait — i.e. canal_entry_time is set
    (so the transit actually started, not still queuing/future)."""
    return df[df["canal_entry_time"].notna() & df["wait_time"].notna()]


def summarise_current(df, capacity_min, capacity_max):
    now = pd.Timestamp.now('UTC').tz_localize(None)
    window_start = now - timedelta(days=CURRENT_WINDOW_DAYS)

    band = filter_band(completed_transits(df), capacity_min, capacity_max)
    band = band[band["canal_entry_time"] >= window_start]

    result = {
        "capacity_range_cbm": [capacity_min, capacity_max],
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


def summarise_weekly(df, capacity_min, capacity_max):
    now = pd.Timestamp.now('UTC').tz_localize(None)
    cutoff = now - timedelta(days=PAST_YEAR_DAYS)

    band = filter_band(completed_transits(df), capacity_min, capacity_max)
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


def summarise_seasonal_range(df, capacity_min, capacity_max):
    """Real 5-year seasonal range — finally genuinely computable, since
    the master dataset's historic sheet goes back to 2020."""
    now = pd.Timestamp.now('UTC').tz_localize(None)
    cutoff = now - timedelta(days=PAST_YEAR_DAYS)

    band = filter_band(completed_transits(df), capacity_min, capacity_max)
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


def current_queue(df, capacity_min, capacity_max):
    """REAL live queue, from the 'waiting' sheet — actual named vessels
    currently waiting, not an empty placeholder."""
    band = filter_band(df, capacity_min, capacity_max)
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
            "estimated_capacity_cbm": None if pd.isna(row["estimated_capacity_cbm"]) else int(row["estimated_capacity_cbm"]),
            "direction": None if pd.isna(row["direction"]) else str(row["direction"]).capitalize(),
            "lock": row["lock"],
            "queue_arrival_time": str(row["queue_arrival_time"]),
            "hours_waiting_so_far": round(float(row["hours_waiting_so_far"]), 1),
        })
    return records


def main():
    print(f"Loading {MASTER_PATH} ...")
    all_transits = load_master()
    print(f"  {len(all_transits)} total rows")
    df = add_estimated_capacity(filter_lpg(all_transits))
    print(f"  {len(df)} confirmed LPG rows")

    capacity_bands_out = {}
    weekly_history_out = {}
    seasonal_range_out = {}
    current_queue_out = []

    for label, (capacity_min, capacity_max) in CAPACITY_BANDS_CBM.items():
        print(f"\n{label} ({capacity_min:,}-{capacity_max:,} CBM)")

        current = summarise_current(df, capacity_min, capacity_max)
        capacity_bands_out[label] = current
        print(f"  Current ({CURRENT_WINDOW_DAYS}d): {current['n_transits']} transits, "
              f"avg {current['avg_wait_days']} days")

        weekly = summarise_weekly(df, capacity_min, capacity_max)
        weekly_history_out[label] = weekly
        print(f"  Weekly history: {len(weekly)} weeks with data")

        seasonal = summarise_seasonal_range(df, capacity_min, capacity_max)
        seasonal_range_out[label] = seasonal
        print(f"  Seasonal range: {len(seasonal)} week-of-year buckets")

        queue = current_queue(df, capacity_min, capacity_max)
        current_queue_out.extend(queue)
        print(f"  Currently waiting: {len(queue)} vessels")

    current_queue_out.sort(key=lambda v: v["hours_waiting_so_far"], reverse=True)

    output = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_source": "vortexa_panama_canal_report_email",
        "notes": (
            "Confirmed LPG vessels sourced from Vortexa's periodic Panama Canal Report email. "
            "Capacity bands use each vessel's maximum observed cargo cubic volume as a working proxy. "
            "export (confirmed by Vortexa: no live API access to this "
            "data). Ingested and merged into a persistent master dataset "
            "on each new upload."
        ),
        "current_window_days": CURRENT_WINDOW_DAYS,
        "capacity_bands": capacity_bands_out,
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
