"""Proof-of-concept scraper for KEGM Turkish Straits vessel traffic.

Reads the public Vessel Traffic Information Systems HTML table, normalises the
useful columns, keeps tanker/gas traffic only, and derives an SP2-to-planning
(or SP2-to-current-status) delay in hours when both timestamps are available.

This is intentionally a diagnostic. It prints enough schema/value information
to refine the production collector after the first GitHub Actions run.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

URL = "https://www.kiyiemniyeti.gov.tr/vessel_traffic_information_systems"
OUTPUT = Path("artifacts/turkish_straits_kegm_probe.json")
DATE_RE = re.compile(r"(\d{2}\.\d{2}\.\d{2}\s+\d{2}:\d{2})")


def clean(value) -> str:
    if pd.isna(value):
        return ""
    return " ".join(str(value).replace("\xa0", " ").split())


def ascii_fold(value: str) -> str:
    # Turkish dotted/dotless i need a little help before NFKD folding.
    value = value.replace("ı", "i").replace("İ", "I")
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().upper()


def is_tanker_or_gas(vessel_type: str) -> bool:
    folded = ascii_fold(vessel_type)
    return any(token in folded for token in ("TANKER", "LPG", "LNG", "GAS CARRIER", "GAS TANKER"))


def parse_dt(value: str):
    match = DATE_RE.search(clean(value))
    if not match:
        return None
    return datetime.strptime(match.group(1), "%d.%m.%y %H:%M")


def identify_columns(df: pd.DataFrame):
    cols = {ascii_fold(clean(c)): c for c in df.columns}

    def find(*needles):
        for folded, original in cols.items():
            if any(n in folded for n in needles):
                return original
        return None

    return {
        "planning": find("PLANLAMA"),
        "ship_name": find("SHIP_NAME", "SHIP NAME"),
        "loa": find("LENGTH_OVERALL", "LENGTH OVERALL"),
        "vessel_type": find("GEMI TIPI", "VESSEL TYPE", "SHIP TYPE"),
        "pilot": find("KILAVUZ KAPTAN", "PILOT"),
        "tug": find("ROMORKOR", "TUG"),
        "sp2": find("SP2"),
        "sp1": find("SP1"),
    }


def main():
    headers = {"User-Agent": "Mozilla/5.0 Turkish-Straits-research/1.0"}
    response = requests.get(URL, headers=headers, timeout=30)
    response.raise_for_status()
    print("HTTP", response.status_code, "bytes", len(response.content))

    soup = BeautifulSoup(response.text, "html.parser")
    print("forms:", len(soup.find_all("form")), "tables:", len(soup.find_all("table")))
    for select in soup.find_all("select"):
        options = [clean(o.get_text(" ", strip=True)) for o in select.find_all("option")]
        print("SELECT", select.get("name"), select.get("id"), "=>", options[:30])

    tables = pd.read_html(response.text)
    print("pandas tables found:", len(tables))

    chosen = None
    mapping = None
    for i, df in enumerate(tables):
        m = identify_columns(df)
        print(f"table {i}: shape={df.shape} columns={list(df.columns)} mapping={m}")
        if m["ship_name"] is not None and m["vessel_type"] is not None and m["sp2"] is not None:
            chosen, mapping = df, m
            break

    if chosen is None:
        raise RuntimeError("Could not identify the KEGM vessel traffic table")

    records = []
    for _, row in chosen.iterrows():
        vessel_type = clean(row[mapping["vessel_type"]])
        if not is_tanker_or_gas(vessel_type):
            continue

        planning = clean(row[mapping["planning"]]) if mapping["planning"] else ""
        sp2_raw = clean(row[mapping["sp2"]]) if mapping["sp2"] else ""
        planning_dt = parse_dt(planning)
        sp2_dt = parse_dt(sp2_raw)
        delay_hours = None
        if planning_dt and sp2_dt:
            delay_hours = round((planning_dt - sp2_dt).total_seconds() / 3600, 2)

        status = DATE_RE.sub("", planning).strip(" -")
        record = {
            "status": status,
            "planning_raw": planning,
            "ship_name": clean(row[mapping["ship_name"]]),
            "loa_m": clean(row[mapping["loa"]]) if mapping["loa"] else "",
            "vessel_type": vessel_type,
            "pilot": clean(row[mapping["pilot"]]) if mapping["pilot"] else "",
            "tug": clean(row[mapping["tug"]]) if mapping["tug"] else "",
            "sp2": sp2_raw,
            "sp1": clean(row[mapping["sp1"]]) if mapping["sp1"] else "",
            "sp2_to_status_hours": delay_hours,
        }
        records.append(record)

    print(f"\nTanker/gas records: {len(records)}")
    for r in records[:50]:
        print(json.dumps(r, ensure_ascii=False))

    type_counts = {}
    for r in records:
        type_counts[r["vessel_type"]] = type_counts.get(r["vessel_type"], 0) + 1

    payload = {
        "source": URL,
        "fetched_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "record_count": len(records),
        "vessel_type_counts": type_counts,
        "records": records,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nWrote", OUTPUT)


if __name__ == "__main__":
    main()
