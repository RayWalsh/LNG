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

import ast
import os
import json
import re
from datetime import datetime, timedelta, timezone

import pandas as pd

MASTER_PATH = os.environ.get("MASTER_TRANSITS_PATH", "data/master_transits.csv")
OUTPUT_JSON = os.environ.get("OUTPUT_JSON_PATH", "site/panama_wait_times.json")

MARKET_GROUPS = {
    "LPG": [
        {"label": "84k CBM — Panamax", "field": "estimated_capacity_cbm", "min": 82_000, "max": 86_000, "range_label": "82,000–86,000 CBM"},
        {"label": "88k CBM — Super Panamax", "field": "estimated_capacity_cbm", "min": 86_001, "max": 90_000, "range_label": "86,001–90,000 CBM"},
        {"label": "95k CBM — Neo Panamax", "field": "estimated_capacity_cbm", "min": 93_000, "max": 97_000, "range_label": "93,000–97,000 CBM"},
    ],
    "LNG": [
        {"label": "88k DWT LNG", "field": "vessel_deadweight", "min": 86_000, "max": 90_000, "range_label": "86,000–90,000 DWT"},
        {"label": "95k DWT LNG", "field": "vessel_deadweight", "min": 93_000, "max": 97_000, "range_label": "93,000–97,000 DWT"},
    ],
    "Tankers": [
        {"label": "MR1", "classes": ["MR1", "Handysize"], "range_label": "MR1 / Handysize"},
        {"label": "MR2", "classes": ["MR2", "Handymax"], "range_label": "MR2 / Handymax"},
        {"label": "LR1", "classes": ["LR1", "Panamax"], "range_label": "LR1 / Panamax"},
        {"label": "LR2 / Aframax", "classes": ["LR2", "Aframax"], "range_label": "LR2 / Aframax"},
        {"label": "Suezmax", "classes": ["Suezmax", "LR3"], "range_label": "Suezmax / LR3"},
    ],
}

PERIODS = {"3m": 90, "6m": 182, "1y": 365, "5y": 1826}
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


def filter_market(df, market):
    vessel_type = df.get("vessel_type", pd.Series("", index=df.index)).fillna("").astype(str)
    if market == "LPG":
        return add_estimated_capacity(filter_lpg(df))
    if market == "LNG":
        return df[vessel_type.str.fullmatch("LNG Carriers", case=False)].copy()
    if market == "Tankers":
        return df[vessel_type.str.fullmatch("Oil Tankers", case=False)].copy()
    return df.iloc[0:0].copy()


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


def filter_group(df, spec):
    if "classes" in spec:
        return df[df["vessel_class"].isin(spec["classes"])].copy()
    field = spec["field"]
    return df[df[field].notna() & df[field].between(spec["min"], spec["max"])].copy()


def completed_transits(df):
    """Rows with a real, completed wait — i.e. canal_entry_time is set
    (so the transit actually started, not still queuing/future)."""
    return df[df["canal_entry_time"].notna() & df["wait_time"].notna()]


def summarise_current(band, range_label, window_days):
    now = pd.Timestamp.now('UTC').tz_localize(None)
    window_start = now - timedelta(days=window_days)

    band = completed_transits(band).copy()
    band = band[band["canal_entry_time"] >= window_start]

    result = {
        "range_label": range_label,
        "window_days": window_days,
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


def summarise_weekly(band):
    now = pd.Timestamp.now('UTC').tz_localize(None)
    cutoff = now - timedelta(days=PAST_YEAR_DAYS)

    band = completed_transits(band)
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


def summarise_seasonal_range(band):
    """Current calendar year versus the previous five complete years."""
    now = pd.Timestamp.now('UTC').tz_localize(None)
    band = completed_transits(band).copy()
    iso = band["canal_entry_time"].dt.isocalendar()
    band["calendar_year"] = band["canal_entry_time"].dt.year.astype(int)
    band["week_of_year"] = iso.week.astype(int)
    current_year = now.year
    historical = band[band["calendar_year"].between(current_year - 5, current_year - 1)]
    current = band[band["calendar_year"] == current_year]

    output = {}
    subsets = {
        "Combined": (historical, current),
        "Northbound": (historical[historical["direction"].str.lower() == "northbound"], current[current["direction"].str.lower() == "northbound"]),
        "Southbound": (historical[historical["direction"].str.lower() == "southbound"], current[current["direction"].str.lower() == "southbound"]),
    }
    for direction, (subset, current_subset) in subsets.items():
        per_year_week = (
            subset.groupby(["calendar_year", "week_of_year"])["wait_time"]
            .mean()
            .reset_index()
        )
        weeks = []
        for wk, wgroup in per_year_week.groupby("week_of_year"):
            weeks.append({
                "week_of_year": int(wk),
                "n_years": int(wgroup["calendar_year"].nunique()),
                "min_days": round(float(wgroup["wait_time"].min()), 2),
                "max_days": round(float(wgroup["wait_time"].max()), 2),
                "avg_days": round(float(wgroup["wait_time"].mean()), 2),
            })
        weeks.sort(key=lambda w: w["week_of_year"])
        current_weeks = []
        for wk, wgroup in current_subset.groupby("week_of_year"):
            current_weeks.append({
                "week_of_year": int(wk),
                "n_transits": int(len(wgroup)),
                "avg_wait_days": round(float(wgroup["wait_time"].mean()), 2),
            })
        current_weeks.sort(key=lambda w: w["week_of_year"])
        output[direction] = {"historical": weeks, "current_year": current_weeks}
    return output


def product_label(value):
    if pd.isna(value) or not str(value).strip():
        return None
    try:
        parsed = ast.literal_eval(str(value))
        values = parsed if isinstance(parsed, (list, tuple)) else [parsed]
    except (ValueError, SyntaxError):
        values = [str(value)]
    clean = []
    for item in values:
        label = str(item).strip()
        if label and label not in clean:
            clean.append(label)
    return " / ".join(clean) or None


def safe_text(value):
    return None if pd.isna(value) else str(value)


def current_queue(band):
    """REAL live queue, from the 'waiting' sheet — actual named vessels
    currently waiting, not an empty placeholder."""
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
            "estimated_capacity_cbm": None if "estimated_capacity_cbm" not in row or pd.isna(row["estimated_capacity_cbm"]) else int(row["estimated_capacity_cbm"]),
            "direction": None if pd.isna(row["direction"]) else str(row["direction"]).capitalize(),
            "lock": row["lock"],
            "queue_arrival_time": str(row["queue_arrival_time"]),
            "hours_waiting_so_far": round(float(row["hours_waiting_so_far"]), 1),
            "cargo_grade": product_label(row.get("products")),
            "origin": safe_text(row.get("origin_port")),
            "destination": safe_text(row.get("destination_port")),
        })
    return records


def vessel_records(band, class_label):
    """Rows for the date-filterable audit table, limited to five years."""
    now = pd.Timestamp.now('UTC').tz_localize(None)
    cutoff = now - timedelta(days=PERIODS["5y"])
    rows = band[
        ((band["canal_entry_time"].notna()) & (band["canal_entry_time"] >= cutoff)) |
        (band["source_sheet"] == "waiting")
    ].copy()
    records = []
    for _, row in rows.iterrows():
        waiting = row.get("source_sheet") == "waiting"
        event = row.get("queue_arrival_time") if waiting else row.get("canal_entry_time")
        if pd.isna(event):
            continue
        wait_days = ((now - event).total_seconds() / 86400) if waiting else row.get("wait_time")
        records.append({
            "id": safe_text(row.get("id")),
            "event_date": event.date().isoformat(),
            "date_type": "Queue arrival" if waiting else "Canal entry",
            "status": "Waiting" if waiting else "Completed",
            "vessel_name": safe_text(row.get("vessel_name")),
            "vessel_imo": None if pd.isna(row.get("vessel_imo")) else int(row.get("vessel_imo")),
            "class_label": class_label,
            "direction": None if pd.isna(row.get("direction")) else str(row.get("direction")).capitalize(),
            "cargo_grade": product_label(row.get("products")),
            "origin": safe_text(row.get("origin_port")),
            "destination": safe_text(row.get("destination_port")),
            "wait_days": None if pd.isna(wait_days) else round(float(wait_days), 2),
            "booked": safe_text(row.get("booked")),
        })
    return records


def main():
    print(f"Loading {MASTER_PATH} ...")
    all_transits = load_master()
    print(f"  {len(all_transits)} total rows")
    markets_out = {}
    for market, specs in MARKET_GROUPS.items():
        market_df = filter_market(all_transits, market)
        print(f"\n{market}: {len(market_df)} rows")
        period_out = {key: {} for key in PERIODS}
        weekly_out = {}
        seasonal_out = {}
        queue_out = []
        records_out = []
        for spec in specs:
            label = spec["label"]
            group = filter_group(market_df, spec)
            for period_key, days in PERIODS.items():
                period_out[period_key][label] = summarise_current(group, spec["range_label"], days)
            weekly_out[label] = summarise_weekly(group)
            seasonal_out[label] = summarise_seasonal_range(group)
            queue_out.extend(current_queue(group))
            records_out.extend(vessel_records(group, label))
            print(f"  {label}: {len(group)} rows; {period_out['3m'][label]['n_transits']} 3-month transits")
        queue_out.sort(key=lambda v: v["hours_waiting_so_far"], reverse=True)
        markets_out[market] = {
            "classes": period_out["3m"],
            "default_period": "3m",
            "period_summaries": period_out,
            "weekly_history": weekly_out,
            "seasonal_range": seasonal_out,
            "current_queue": queue_out,
            "vessel_records": records_out,
        }

    output = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_source": "vortexa_panama_canal_report_email",
        "notes": (
            "LPG, LNG and oil tanker vessels sourced from Vortexa's periodic Panama Canal Report email. "
            "LPG capacity bands use each vessel's maximum observed cargo cubic volume as a working proxy. "
            "export (confirmed by Vortexa: no live API access to this "
            "data). Ingested and merged into a persistent master dataset "
            "on each new upload."
        ),
        "periods": PERIODS,
        "current_year": datetime.now(timezone.utc).year,
        "default_market": "LPG",
        "markets": markets_out,
    }

    os.makedirs(os.path.dirname(OUTPUT_JSON) or ".", exist_ok=True)
    with open(OUTPUT_JSON, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\nWrote {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
