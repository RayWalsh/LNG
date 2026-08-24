"""
Panama Canal LNG Wait Time Puller — Vortexa API (VoyagesCongestionBreakdown)
=============================================================================

IMPORTANT HISTORY — read this before touching the endpoint choice below.

This script originally used Vortexa's "Canal Transit" dataset
(CanalTransit), which has exactly the fields you'd want (queue arrival
time, canal entry time, direction, DWT). Empirically confirmed, TWICE,
against a real account: CanalTransit returns a 401/403 permissions_error
— it is not included in this Vortexa plan. A full account-wide audit
(see scripts/audit_vortexa_access.py) confirmed this isn't isolated:
CanalTransit is denied alongside the entire Fixtures / Freight Pricing /
Vessel Availability / EIA Forecasts / VesselPositions group, suggesting
a separate "Freight" tier this account doesn't have. An email is out to
the Vortexa account team asking whether that tier can be added — if it
ever is, CanalTransit is the cleaner, more precise data source and this
script should be switched back (see git history for the old version).

Until/unless that happens, this script uses VoyagesCongestionBreakdown
instead — confirmed ACCESSIBLE and empirically tested to return
sensible, real numbers. Key things learned about how it actually works
(none of this is guessable from public docs, only from real testing):

  - `locations` filters to voyages congested AT a given place (we pass
    the "Panama Canal" waypoint's Geographies ID). It does NOT mean
    "group results by this place."
  - `breakdown_property` controls how the (already Panama-filtered)
    results get grouped for display. The API only accepts EXACTLY
    "port", "terminal", or "shipping_region" — confirmed via a 400
    validation error listing the valid options. There is no "canal" or
    "waypoint" option, so results always come back grouped by port
    (e.g. "Sabine Pass, TX [US]"), never labelled "Panama Canal"
    itself. This is expected, not a bug.
  - `avg_waiting_time` (and the `_laden`/`_ballast` variants) are in
    SECONDS.
  - There is no separate northbound/southbound field in the response.
    laden vs ballast is the closest available proxy (a laden LNG
    carrier is normally the leg that matters commercially) and is
    reported AS laden/ballast, not mislabelled as a direction.
  - `vessel_dwt_min` / `vessel_dwt_max` ARE real, working server-side
    filters — confirmed via real filtered pulls.
  - This endpoint returns numbers PRE-AGGREGATED over whatever
    time_min/time_max window you give it — there is no server-side
    "group by week" option. Getting a weekly series means one API call
    per week (see fetch_period() / build_weekly_history() below). This
    is why the 5-year seasonal range from the old CanalTransit-based
    version isn't implemented here yet — at ~250 calls per band it's
    expensive, and this endpoint's own multi-year reliability hasn't
    been tested yet. Revisit once weekly-over-a-year is proven stable.
  - There is no live "who's in the queue right now" list from this
    endpoint (that was a CanalTransit-only feature) — current_queue is
    always empty here, honestly, rather than faked.

SETUP
-----
Runs inside GitHub Actions (see .github/workflows/update-and-deploy.yml).
VORTEXA_API_KEY lives ONLY as a GitHub Actions repository secret.

To run manually for debugging:
    pip install vortexasdk packaging pandas
    export VORTEXA_API_KEY="your-key-here"
    python3 scripts/fetch_panama_wait_times.py
"""

import os
import json
import time
from datetime import datetime, timedelta

import pandas as pd

try:
    from vortexasdk import Geographies, VoyagesCongestionBreakdown
except ImportError as e:
    raise SystemExit(
        "vortexasdk not installed. Run: pip install vortexasdk\n"
        f"Original error: {e}"
    )

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

DWT_BANDS = {
    "88k DWT LNG": (86_000, 90_000),
    "95k DWT LNG": (93_000, 97_000),
}

CURRENT_WINDOW_DAYS = 30   # window used for the "current average wait" cards
WEEKLY_HISTORY_WEEKS = 52  # how many past weeks to build a trend line for

# Small pause between API calls in the weekly-history loop (it makes
# ~1 call per week per band — be a little gentle rather than hammering
# the API in a tight loop).
CALL_DELAY_SECONDS = 0.2

OUTPUT_JSON = os.environ.get("OUTPUT_JSON_PATH", "site/panama_wait_times.json")


# ---------------------------------------------------------------------------
# 1. Find the "Panama Canal" waypoint's Geographies ID
# ---------------------------------------------------------------------------

def find_panama_canal_id() -> str:
    df = Geographies().search(term="panama").to_df()
    exact = df[df["name"] == "Panama Canal"]
    if len(exact):
        return exact.iloc[0]["id"]

    canal_like = df[df["name"].str.lower().str.contains("canal", na=False)]
    if len(canal_like):
        return canal_like.iloc[0]["id"]

    raise RuntimeError(
        "Could not find a 'Panama Canal' waypoint via Geographies search — "
        "Vortexa may have renamed it. Run scripts/probe_congestion_breakdown.py "
        "to re-check what Panama-related geographies currently exist."
    )


# ---------------------------------------------------------------------------
# 2. Fetch + aggregate one time window, for one DWT band
# ---------------------------------------------------------------------------

def fetch_period(panama_id: str, dwt_min: int, dwt_max: int,
                  time_min: datetime, time_max: datetime) -> pd.DataFrame:
    """One call to VoyagesCongestionBreakdown for a given window/band.
    Returns the raw (port-level) rows — may be empty if nothing matched."""
    try:
        return VoyagesCongestionBreakdown().search(
            time_min=time_min,
            time_max=time_max,
            locations=panama_id,
            vessel_dwt_min=dwt_min,
            vessel_dwt_max=dwt_max,
        ).to_df()
    except Exception as e:  # noqa: BLE001 - log and treat as "no data" rather than crash
        print(f"    (call failed for {time_min.date()}–{time_max.date()}: {e})")
        return pd.DataFrame()


def aggregate_wait(df: pd.DataFrame) -> dict:
    """
    VoyagesCongestionBreakdown returns one row PER PORT (grouped by
    origin/discharge port, not by canal — see module docstring). This
    collapses those port-level rows into a single vessel-count-weighted
    average, both overall and split laden/ballast.
    """
    empty = {
        "n_voyages": 0,
        "avg_wait_days": None,
        "by_status": {},  # "Laden" / "Ballast" — see module docstring
    }
    if df is None or not len(df) or "avg_waiting_time" not in df.columns:
        return empty

    total_vessels = int(df["vessel_count"].sum())
    if total_vessels == 0:
        return empty

    weighted_seconds = (df["avg_waiting_time"] * df["vessel_count"]).sum() / total_vessels
    result = {
        "n_voyages": total_vessels,
        "avg_wait_days": round(float(weighted_seconds) / 86400, 2),
        "by_status": {},
    }

    for status in ["laden", "ballast"]:
        n_col, w_col = f"vessel_count_{status}", f"avg_waiting_time_{status}"
        if n_col not in df.columns or w_col not in df.columns:
            continue
        n = int(df[n_col].sum())
        if n == 0:
            continue
        weighted = (df[w_col] * df[n_col]).sum() / n
        result["by_status"][status.capitalize()] = {
            "n_voyages": n,
            "avg_wait_days": round(float(weighted) / 86400, 2),
        }

    return result


# ---------------------------------------------------------------------------
# 3. Current summary — one recent window, per band
# ---------------------------------------------------------------------------

def build_current_summary(panama_id: str) -> dict:
    now = datetime.utcnow()
    window_start = now - timedelta(days=CURRENT_WINDOW_DAYS)

    results = {}
    for band_label, (dwt_min, dwt_max) in DWT_BANDS.items():
        df = fetch_period(panama_id, dwt_min, dwt_max, window_start, now)
        agg = aggregate_wait(df)
        results[band_label] = {
            "dwt_range": [dwt_min, dwt_max],
            "window_days": CURRENT_WINDOW_DAYS,
            **agg,
        }
        time.sleep(CALL_DELAY_SECONDS)

    return results


# ---------------------------------------------------------------------------
# 4. Weekly history — one call per week, per band (see module docstring
#    for why this can't be done in a single server-side call)
# ---------------------------------------------------------------------------

def build_weekly_history(panama_id: str) -> dict:
    now = datetime.utcnow()
    results = {label: [] for label in DWT_BANDS}

    for week_index in range(WEEKLY_HISTORY_WEEKS):
        week_end = now - timedelta(weeks=week_index)
        week_start = week_end - timedelta(days=7)

        for band_label, (dwt_min, dwt_max) in DWT_BANDS.items():
            df = fetch_period(panama_id, dwt_min, dwt_max, week_start, week_end)
            agg = aggregate_wait(df)
            if agg["avg_wait_days"] is not None:
                results[band_label].append({
                    "week_start": week_start.date().isoformat(),
                    "week_of_year": week_start.isocalendar()[1],
                    "n_voyages": agg["n_voyages"],
                    "avg_wait_days": agg["avg_wait_days"],
                    "by_status": agg["by_status"],
                })
            time.sleep(CALL_DELAY_SECONDS)

    for label in results:
        results[label].sort(key=lambda w: w["week_start"])

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not os.environ.get("VORTEXA_API_KEY"):
        raise SystemExit(
            "Set the VORTEXA_API_KEY environment variable first.\n"
            "Find your key in your Vortexa account / API settings."
        )

    print("Finding Panama Canal waypoint ID via Geographies...")
    panama_id = find_panama_canal_id()
    print(f"  Using location ID: {panama_id}")

    print(f"\nBuilding current summary (trailing {CURRENT_WINDOW_DAYS} days)...")
    current_summary = build_current_summary(panama_id)

    print(f"\nBuilding weekly history ({WEEKLY_HISTORY_WEEKS} weeks — "
          f"this makes ~{WEEKLY_HISTORY_WEEKS * len(DWT_BANDS)} API calls, may take a few minutes)...")
    weekly_history = build_weekly_history(panama_id)

    output = {
        "generated_at_utc": datetime.utcnow().isoformat() + "Z",
        "data_source": "vortexa_voyages_congestion_breakdown",
        "notes": (
            "CanalTransit (the ideal dataset) is not accessible on this "
            "Vortexa account (confirmed 401/403). This data instead comes "
            "from VoyagesCongestionBreakdown filtered to the Panama Canal "
            "waypoint. 'Laden'/'Ballast' is used instead of a true "
            "northbound/southbound direction, since this endpoint doesn't "
            "expose one. There is no live vessel-queue list from this "
            "endpoint (current_queue is intentionally always empty). "
            "5-year seasonal range is not yet implemented for this data "
            "source — see script docstring for why."
        ),
        "current_window_days": CURRENT_WINDOW_DAYS,
        "dwt_bands": current_summary,
        "weekly_history": weekly_history,
        "seasonal_range": {label: [] for label in DWT_BANDS},  # not yet implemented, see docstring
        "current_queue": [],  # not available from this data source, see docstring
    }

    os.makedirs(os.path.dirname(OUTPUT_JSON) or ".", exist_ok=True)
    with open(OUTPUT_JSON, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\nWrote {OUTPUT_JSON}")
    for label, summary in current_summary.items():
        lo, hi = summary["dwt_range"]
        print(f"\n{label} ({lo:,}-{hi:,} DWT)")
        print(f"  Voyages in trailing {CURRENT_WINDOW_DAYS}d: {summary['n_voyages']}")
        print(f"  Avg wait: {summary['avg_wait_days']} days")
        for status, d in summary["by_status"].items():
            print(f"    {status}: {d['avg_wait_days']} days over {d['n_voyages']} voyages")
        n_weeks = len(weekly_history.get(label, []))
        print(f"  Weekly history points with data: {n_weeks} / {WEEKLY_HISTORY_WEEKS}")


if __name__ == "__main__":
    main()
