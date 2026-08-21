"""
Panama Canal LNG Transit Wait Time Puller — Vortexa API
=========================================================

Pulls raw Panama Canal transit records from Vortexa's "Canal Transit"
dataset, computes actual wait time per vessel (queue arrival -> canal
entry), and produces:
  - current average wait times for two LNG carrier DWT bands
    (default: ~88,000 DWT and ~95,000 DWT),
  - a week-by-week average wait time series for the past year,
  - a 5-year seasonal range (min / max / avg per week-of-year, built from
    the 4 years prior to the last 52 weeks) so the past year can be
    plotted against where it historically sits, and
  - a live snapshot of vessels currently sitting in the queue.

Output: panama_wait_times.json — consumed by panama_canal_dashboard.html

SETUP
-----
This script is designed to run inside GitHub Actions (see
.github/workflows/update-and-deploy.yml), not on a local machine. The
Vortexa API key lives ONLY as a GitHub Actions repository secret
(Settings -> Secrets and variables -> Actions -> New repository secret,
named VORTEXA_API_KEY) — it is never committed, never put in a local
.env file, and never typed into a Claude Code chat session (Claude
Code's cloud sessions have no secrets store).

To run it manually on your own machine for debugging instead, you'd do:
    pip install vortexasdk pandas
    export VORTEXA_API_KEY="your-key-here"
    python3 scripts/fetch_panama_wait_times.py

NOTE ON FILTERS
----------------
The Vortexa "Canal Transit" endpoint definitely exposes these fields per
record (confirmed via the SDK's entity docs):
    vessel_id, vessel_name, vessel_imo, vessel_mmsi, vessel_class,
    vessel_cubic_capacity, vessel_dead_weight, canal, direction, lock,
    queue_arrival_time, canal_entry_time, canal_exit_time, booked_time,
    voyage_status, cargoes, origin, destination, charterer,
    effective_controller

The installed vortexasdk 1.0.29 signature was verified in GitHub Actions.
This script anchors the broad lookback window on queue_arrival_time, which
includes both completed transits and vessels that are still waiting. Panama,
DWT-band, and direction filtering remains local in pandas.
"""

import os
import json
from datetime import datetime, timedelta

import pandas as pd

try:
    from vortexasdk import CanalTransit
except ImportError as e:
    raise SystemExit(
        "vortexasdk not installed. Run: pip install vortexasdk\n"
        f"Original error: {e}"
    )

# ---------------------------------------------------------------------------
# CONFIG — adjust as needed
# ---------------------------------------------------------------------------

LOOKBACK_DAYS = 1830  # ~5 years, with a little slack for week-boundary trimming

# The most recent PAST_YEAR_DAYS days are treated as "the past year" (shown
# as its own overlay line). Everything older than that, back to
# LOOKBACK_DAYS, forms the historical band used to compute the 5-year
# min/max/avg per week-of-year.
PAST_YEAR_DAYS = 364  # exactly 52 weeks

# DWT bands to report on. Bands have some width around the target DWT
# because AIS/registry DWT figures for sister ships vary slightly and a
# single exact-DWT filter would return almost nothing.
DWT_BANDS = {
    "88k DWT LNG": (86_000, 90_000),
    "95k DWT LNG": (93_000, 97_000),
}

# Which timestamp anchors a transit to a given week/year. canal_entry_time
# = the week the vessel actually got through (most common convention for
# "how bad was congestion that week"). Swap to queue_arrival_time if you'd
# rather bucket by when the wait started.
WEEKLY_ANCHOR_COLUMN = "canal_entry_time"

OUTPUT_JSON = os.environ.get("OUTPUT_JSON_PATH", "site/panama_wait_times.json")


# ---------------------------------------------------------------------------
# 1. Pull raw canal transit records from Vortexa
# ---------------------------------------------------------------------------

def fetch_canal_transits(days_back: int = LOOKBACK_DAYS) -> pd.DataFrame:
    time_max = datetime.utcnow()
    time_min = time_max - timedelta(days=days_back)

    search_result = CanalTransit().search(
        filter_queue_arrival_time_min=time_min,
        filter_queue_arrival_time_max=time_max,
    )

    df = search_result.to_df()
    return df


# ---------------------------------------------------------------------------
# 2. Filter to Panama, compute wait time per vessel transit
# ---------------------------------------------------------------------------

def compute_wait_times(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if "canal" in df.columns:
        df = df[df["canal"].astype(str).str.contains("panama", case=False, na=False)]

    for col in ["queue_arrival_time", "canal_entry_time", "canal_exit_time", "booked_time"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)

    df["wait_time_hours"] = (
        df["canal_entry_time"] - df["queue_arrival_time"]
    ).dt.total_seconds() / 3600

    # Keep only transits where we can actually compute a completed wait
    df = df[df["wait_time_hours"].notna() & (df["wait_time_hours"] >= 0)]

    return df


# ---------------------------------------------------------------------------
# 3. Slice by DWT band and direction, aggregate
# ---------------------------------------------------------------------------

def summarise_by_band(df: pd.DataFrame) -> dict:
    results = {}

    for band_label, (dwt_min, dwt_max) in DWT_BANDS.items():
        band_df = df[
            df["vessel_dead_weight"].notna()
            & (df["vessel_dead_weight"] >= dwt_min)
            & (df["vessel_dead_weight"] <= dwt_max)
        ]

        band_summary = {
            "dwt_range": [dwt_min, dwt_max],
            "n_transits": int(len(band_df)),
            "avg_wait_hours": None,
            "avg_wait_days": None,
            "by_direction": {},
        }

        if len(band_df):
            band_summary["avg_wait_hours"] = round(float(band_df["wait_time_hours"].mean()), 1)
            band_summary["avg_wait_days"] = round(float(band_df["wait_time_hours"].mean()) / 24, 2)

            for direction, dgroup in band_df.groupby("direction"):
                band_summary["by_direction"][str(direction)] = {
                    "n_transits": int(len(dgroup)),
                    "avg_wait_hours": round(float(dgroup["wait_time_hours"].mean()), 1),
                    "avg_wait_days": round(float(dgroup["wait_time_hours"].mean()) / 24, 2),
                }

        results[band_label] = band_summary

    return results


# ---------------------------------------------------------------------------
# 4. Weekly history — average wait time per week, per band, over the window
# ---------------------------------------------------------------------------

def summarise_weekly(df: pd.DataFrame) -> dict:
    """
    Buckets the PAST YEAR of completed transits into ISO weeks (Mon-Sun,
    labelled by the Monday of that week) and computes average wait time
    per week, per DWT band, both combined and split by direction. Each
    week also carries its ISO week-of-year number so the dashboard can
    align this series against the 5-year seasonal range by week-of-year
    rather than by calendar date. Weeks with zero transits for a band are
    omitted rather than filled with nulls/zeros.
    """
    results = {}

    if WEEKLY_ANCHOR_COLUMN not in df.columns:
        return {label: [] for label in DWT_BANDS}

    df = df.copy()
    cutoff = pd.Timestamp.utcnow() - pd.Timedelta(days=PAST_YEAR_DAYS)
    df = df[df[WEEKLY_ANCHOR_COLUMN] >= cutoff]

    df["week_start"] = (
        df[WEEKLY_ANCHOR_COLUMN].dt.tz_convert("UTC").dt.to_period("W-SUN").dt.start_time
    )
    df["week_of_year"] = df[WEEKLY_ANCHOR_COLUMN].dt.isocalendar().week.astype(int)

    for band_label, (dwt_min, dwt_max) in DWT_BANDS.items():
        band_df = df[
            df["vessel_dead_weight"].notna()
            & (df["vessel_dead_weight"] >= dwt_min)
            & (df["vessel_dead_weight"] <= dwt_max)
        ]

        weeks = []
        for week_start, wgroup in band_df.groupby("week_start"):
            entry = {
                "week_start": week_start.date().isoformat(),
                "week_of_year": int(wgroup["week_of_year"].iloc[0]),
                "n_transits": int(len(wgroup)),
                "avg_wait_days": round(float(wgroup["wait_time_hours"].mean()) / 24, 2),
                "by_direction": {},
            }
            for direction, dgroup in wgroup.groupby("direction"):
                entry["by_direction"][str(direction)] = {
                    "n_transits": int(len(dgroup)),
                    "avg_wait_days": round(float(dgroup["wait_time_hours"].mean()) / 24, 2),
                }
            weeks.append(entry)

        weeks.sort(key=lambda w: w["week_start"])
        results[band_label] = weeks

    return results


# ---------------------------------------------------------------------------
# 4b. 5-year seasonal range — min/max/avg per week-of-year, prior 4 years
# ---------------------------------------------------------------------------

def summarise_seasonal_range(df: pd.DataFrame) -> dict:
    """
    Uses everything OLDER than the past year (i.e. roughly years 2-5 back)
    to build a min/max/avg band per ISO week-of-year, so the dashboard can
    shade "the historical range for this week" and plot the past year's
    actual value against it.

    Method: first compute each (year, week-of-year)'s own average wait
    time (so one outlier vessel doesn't skew a whole 5-year band), then
    take the min/max/avg of those yearly week-values across however many
    years of history are available for that week number.
    """
    results = {}

    if WEEKLY_ANCHOR_COLUMN not in df.columns:
        return {label: [] for label in DWT_BANDS}

    df = df.copy()
    cutoff = pd.Timestamp.utcnow() - pd.Timedelta(days=PAST_YEAR_DAYS)
    df = df[df[WEEKLY_ANCHOR_COLUMN] < cutoff]

    iso = df[WEEKLY_ANCHOR_COLUMN].dt.isocalendar()
    df["iso_year"] = iso.year.astype(int)
    df["week_of_year"] = iso.week.astype(int)

    for band_label, (dwt_min, dwt_max) in DWT_BANDS.items():
        band_df = df[
            df["vessel_dead_weight"].notna()
            & (df["vessel_dead_weight"] >= dwt_min)
            & (df["vessel_dead_weight"] <= dwt_max)
        ]

        # Step 1: average wait time per (iso_year, week_of_year)
        per_year_week = (
            band_df.groupby(["iso_year", "week_of_year"])["wait_time_hours"]
            .mean()
            .reset_index()
        )
        per_year_week["avg_wait_days"] = per_year_week["wait_time_hours"] / 24

        # Step 2: min/max/avg of those yearly values, per week_of_year
        weeks = []
        for wk, wgroup in per_year_week.groupby("week_of_year"):
            weeks.append({
                "week_of_year": int(wk),
                "n_years": int(wgroup["iso_year"].nunique()),
                "min_days": round(float(wgroup["avg_wait_days"].min()), 2),
                "max_days": round(float(wgroup["avg_wait_days"].max()), 2),
                "avg_days": round(float(wgroup["avg_wait_days"].mean()), 2),
            })

        weeks.sort(key=lambda w: w["week_of_year"])
        results[band_label] = weeks

    return results


# ---------------------------------------------------------------------------
# 5. Live snapshot: vessels currently sitting in the queue (any DWT)
# ---------------------------------------------------------------------------

def current_queue_snapshot(df: pd.DataFrame) -> list:
    """Vessels that have joined the queue but not yet entered the canal,
    restricted to the two DWT bands so the dashboard table stays focused."""
    if "queue_arrival_time" not in df.columns or "canal_entry_time" not in df.columns:
        return []

    waiting = df[
        df["queue_arrival_time"].notna() & df["canal_entry_time"].isna()
    ].copy()

    if "vessel_dead_weight" in waiting.columns:
        lo = min(v[0] for v in DWT_BANDS.values())
        hi = max(v[1] for v in DWT_BANDS.values())
        waiting = waiting[
            waiting["vessel_dead_weight"].notna()
            & (waiting["vessel_dead_weight"] >= lo)
            & (waiting["vessel_dead_weight"] <= hi)
        ]

    waiting["hours_waiting_so_far"] = (
        pd.Timestamp.utcnow() - waiting["queue_arrival_time"]
    ).dt.total_seconds() / 3600

    cols = [
        "vessel_name", "vessel_imo", "vessel_dead_weight",
        "direction", "lock", "queue_arrival_time", "hours_waiting_so_far",
    ]
    cols = [c for c in cols if c in waiting.columns]

    return (
        waiting[cols]
        .sort_values("hours_waiting_so_far", ascending=False)
        .to_dict("records")
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not os.environ.get("VORTEXA_API_KEY"):
        raise SystemExit(
            "Set the VORTEXA_API_KEY environment variable first.\n"
            "Find your key in your Vortexa account / API settings."
        )

    print("Pulling Panama Canal transit records from Vortexa...")
    raw = fetch_canal_transits()
    print(f"  {len(raw)} raw records pulled")

    processed = compute_wait_times(raw)
    print(f"  {len(processed)} completed transits with a computable wait time")

    band_summary = summarise_by_band(processed)
    weekly_history = summarise_weekly(processed)
    seasonal_range = summarise_seasonal_range(processed)
    queue_now = current_queue_snapshot(raw)

    output = {
        "generated_at_utc": datetime.utcnow().isoformat() + "Z",
        "lookback_days": LOOKBACK_DAYS,
        "past_year_days": PAST_YEAR_DAYS,
        "dwt_bands": band_summary,
        "weekly_history": weekly_history,
        "seasonal_range": seasonal_range,
        "current_queue": queue_now,
    }

    os.makedirs(os.path.dirname(OUTPUT_JSON) or ".", exist_ok=True)
    with open(OUTPUT_JSON, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\nWrote {OUTPUT_JSON}")
    for label, summary in band_summary.items():
        lo, hi = summary["dwt_range"]
        print(f"\n{label} ({lo:,}-{hi:,} DWT)")
        print(f"  Transits in window: {summary['n_transits']}")
        print(f"  Avg wait: {summary['avg_wait_days']} days ({summary['avg_wait_hours']} hrs)")
        for direction, d in summary["by_direction"].items():
            print(f"    {direction}: {d['avg_wait_days']} days over {d['n_transits']} transits")
        n_weeks = len(weekly_history.get(label, []))
        n_seasonal_weeks = len(seasonal_range.get(label, []))
        max_years = max((w["n_years"] for w in seasonal_range.get(label, [])), default=0)
        print(f"  Past-year weekly points: {n_weeks}")
        print(f"  Seasonal range weeks covered: {n_seasonal_weeks} (up to {max_years} years of history per week)")


if __name__ == "__main__":
    main()
