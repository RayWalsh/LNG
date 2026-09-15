"""Extract ACP auction-price summary PDFs into an idempotent history file."""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pdfplumber


CATEGORIES = {
    "Neopanamax": (130, 340),
    "Super": (430, 650),
    "Regular": (730, 960),
}


@dataclass(frozen=True)
class AuctionSummary:
    update_date: str
    window_start: str
    window_end: str
    vessel_category: str
    minimum_usd: int
    average_usd: int
    maximum_usd: int
    source_file: str
    source_url: str


def _usd_k(value: str) -> int:
    return int(value.replace(",", "").removesuffix("K")) * 1_000


def extract_summaries(pdf_path: Path, source_url: str) -> list[AuctionSummary]:
    with pdfplumber.open(pdf_path) as pdf:
        if len(pdf.pages) != 1:
            raise ValueError(f"Expected one-page auction summary, found {len(pdf.pages)} pages")
        page = pdf.pages[0]
        text = page.extract_text() or ""
        words = page.extract_words()

    date_match = re.search(r"Update Date:\s*([A-Za-z]+ \d{1,2}, \d{4})", text)
    if not date_match:
        raise ValueError("Update Date was not found in the PDF")
    update = datetime.strptime(date_match.group(1), "%B %d, %Y").date()

    blocks = {}
    for category, (x_min, x_max) in CATEGORIES.items():
        values = [
            _usd_k(w["text"])
            for w in words
            if x_min <= float(w["x0"]) <= x_max
            and re.fullmatch(r"[\d,]+K", w["text"])
        ]
        if not values:
            raise ValueError(f"No plotted values found for {category}")
        blocks[category] = values

    averages = {}
    panel_for_x = ((340, "Neopanamax"), (650, "Super"), (float("inf"), "Regular"))
    for average_word in (w for w in words if w["text"].lower() == "average"):
        category = next(name for boundary, name in panel_for_x if float(average_word["x0"]) < boundary)
        candidates = [
            w for w in words
            if float(w["x1"]) <= float(average_word["x0"]) + 2
            and abs(float(w["top"]) - float(average_word["top"])) <= 5
            and re.search(r"\d[\d,]*K", w["text"])
        ]
        if candidates:
            nearest = max(candidates, key=lambda w: float(w["x1"]))
            value = re.findall(r"(\d[\d,]*K)", nearest["text"])[-1]
            averages[category] = _usd_k(value)
    if set(averages) != set(CATEGORIES):
        raise ValueError(f"Expected averages for all categories, found {sorted(averages)}")

    output = []
    for category, values in blocks.items():
        average = averages[category]
        plotted = [v for v in values if v != average]
        output.append(
            AuctionSummary(
                update_date=update.isoformat(),
                window_start=(update - timedelta(days=6)).isoformat(),
                window_end=update.isoformat(),
                vessel_category=category,
                minimum_usd=min(plotted),
                average_usd=average,
                maximum_usd=max(plotted),
                source_file=pdf_path.name,
                source_url=source_url,
            )
        )
    return output


def upsert_csv(rows: list[AuctionSummary], history_path: Path) -> tuple[int, int]:
    fieldnames = list(asdict(rows[0])) + ["ingested_at_utc"]
    existing = []
    if history_path.exists():
        with history_path.open(newline="", encoding="utf-8") as handle:
            existing = list(csv.DictReader(handle))
    keys = {(r["update_date"], r["vessel_category"]) for r in existing}
    now = datetime.now(timezone.utc).isoformat()
    additions = []
    for row in rows:
        data = asdict(row)
        key = (data["update_date"], data["vessel_category"])
        if key not in keys:
            data["ingested_at_utc"] = now
            additions.append(data)
            keys.add(key)
    if additions:
        history_path.parent.mkdir(parents=True, exist_ok=True)
        with history_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(existing + additions)
    return len(additions), len(existing) + len(additions)


def write_json(history_path: Path, output_path: Path) -> None:
    with history_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps({"auction_prices": rows}, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--history", type=Path, default=Path("data/auction_prices.csv"))
    parser.add_argument("--json", type=Path, default=Path("site/auction_prices.json"))
    parser.add_argument("--source-url", default="https://auctioninfo.pancanal.com/en/pdfs")
    args = parser.parse_args()
    rows = extract_summaries(args.pdf, args.source_url)
    added, total = upsert_csv(rows, args.history)
    write_json(args.history, args.json)
    print(f"Auction update {rows[0].update_date}: {added} rows added; {total} rows retained")


if __name__ == "__main__":
    main()
