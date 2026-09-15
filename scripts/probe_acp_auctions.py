#!/usr/bin/env python3
"""Read-only feasibility probe for the Panama Canal auction archive.

The probe deliberately does not infer that a vessel bought a slot.  It records
only direct identifiers and generates conservative candidate matches for review.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import ssl
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.request import Request, urlopen


BASE_URL = "https://auction.pancanal.com/Auction/"
DEFAULT_LISTING = urljoin(
    BASE_URL, "APViewInCat.asp?CMD=VIEWALLCLOSED&ID=2&VIEW=NORMAL"
)
USER_AGENT = "RayWalsh-LNG-auction-feasibility/0.1 (+https://github.com/RayWalsh/LNG)"


class RegistrationRequired(RuntimeError):
    pass


class TablesAndLinksParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)
        elif tag.lower() == "tr":
            self._row = []
        elif tag.lower() in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"td", "th"} and self._cell is not None:
            value = " ".join("".join(self._cell).split())
            assert self._row is not None
            self._row.append(value)
            self._cell = None
        elif tag.lower() == "tr" and self._row is not None:
            if any(self._row):
                self.rows.append(self._row)
            self._row = None


def parse_html(html: str) -> TablesAndLinksParser:
    parser = TablesAndLinksParser()
    parser.feed(html)
    return parser


def auction_ids(html: str) -> list[int]:
    found: set[int] = set()
    for href in parse_html(html).links:
        parsed = urlparse(href)
        query = {k.lower(): v for k, v in parse_qs(parsed.query).items()}
        path = parsed.path.lower()
        values: list[str] = []
        if path.endswith("apviewitem.asp"):
            values = query.get("id", [])
        elif path.endswith("apbidhistory.asp"):
            values = query.get("aucid", [])
        for value in values:
            if value.isdigit():
                found.add(int(value))
    return sorted(found, reverse=True)


def visible_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return " ".join(text.replace("&nbsp;", " ").split())


def first_match(text: str, patterns: Iterable[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(" :-")
    return None


def money(value: str | None) -> float | None:
    if not value:
        return None
    match = re.search(r"(?:US\$|USD|\$)?\s*([\d,]+(?:\.\d{1,2})?)", value)
    return float(match.group(1).replace(",", "")) if match else None


@dataclass
class Auction:
    auction_id: int
    title: str | None
    closes_at: str | None
    transit_date: str | None
    direction: str | None
    vessel_category: str | None
    market_segment: str | None
    starting_bid_usd: float | None
    final_bid_usd: float | None
    vessel_name: str | None
    imo: str | None
    bid_rows: list[list[str]]


def parse_auction(auction_id: int, detail_html: str, bids_html: str) -> Auction:
    detail = visible_text(detail_html)
    bid_parser = parse_html(bids_html)
    bid_text = visible_text(bids_html)
    combined = f"{detail} {bid_text}"
    title = first_match(detail, [r"Auction Title\s*[:\-]\s*(.+?)(?=Auction ID|Closes|$)"])
    closes = first_match(detail, [r"(?:Auction )?Closes(?: On)?\s*[:\-]\s*(.+?)(?=Starting Bid|Current Bid|$)"])
    transit = first_match(combined, [r"Transit Date\s*[:\-]\s*([^|;]+?)(?=Direction|Vessel|Lock|$)", r"Booking Date\s*[:\-]\s*([^|;]+?)(?=Direction|Vessel|Lock|$)"])
    direction = first_match(combined, [r"Direction\s*[:\-]\s*(Northbound|Southbound|North Bound|South Bound)"])
    category = first_match(combined, [r"(?:Vessel|Lock) Category\s*[:\-]\s*(Neopanamax|Panamax Plus|Super|Regular)"])
    segment = first_match(combined, [r"Market Segment\s*[:\-]\s*([^|;]+?)(?=Direction|Vessel|Lock|$)"])
    starting = money(first_match(detail, [r"Starting Bid\s*[:\-]\s*((?:US\$|USD|\$)?\s*[\d,.]+)"]))
    final = money(first_match(combined, [r"Final Bid(?: Price)?\s*[:\-]\s*((?:US\$|USD|\$)?\s*[\d,.]+)", r"Current Bid\s*[:\-]\s*((?:US\$|USD|\$)?\s*[\d,.]+)"]))
    vessel = first_match(combined, [r"Vessel Name\s*[:\-]\s*([A-Z0-9 ._'\-]+?)(?=IMO|Direction|Transit|$)"])
    imo = first_match(combined, [r"\bIMO(?: Number)?\s*[:#\-]?\s*(\d{7})\b"])
    return Auction(auction_id, title, closes, transit, direction, category, segment,
                   starting, final, vessel, imo, bid_parser.rows)


def ssl_context() -> ssl.SSLContext:
    cafile = os.getenv("ACP_CA_BUNDLE")
    return ssl.create_default_context(cafile=cafile or None)


def fetch(url: str, timeout: int = 30) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with urlopen(request, timeout=timeout, context=ssl_context()) as response:
        charset = response.headers.get_content_charset() or "latin-1"
        return response.read().decode(charset, errors="replace")


def normalized(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def load_vessels(path: Path | None) -> list[dict[str, str]]:
    if not path or not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def candidate_matches(auction: Auction, vessels: list[dict[str, str]]) -> list[dict[str, object]]:
    """Return candidates, but confirm only exact IMO or exact vessel-name matches."""
    candidates: list[dict[str, object]] = []
    for row in vessels:
        keys = {normalized(k): v for k, v in row.items()}
        row_imo = str(keys.get("imo") or keys.get("vesselimo") or "").strip()
        row_name = str(keys.get("vesselname") or keys.get("name") or "").strip()
        confidence = None
        reason = None
        if auction.imo and row_imo == auction.imo:
            confidence, reason = "confirmed", "exact IMO"
        elif auction.vessel_name and normalized(row_name) == normalized(auction.vessel_name):
            confidence, reason = "confirmed", "exact vessel name"
        if confidence:
            candidates.append({"vessel_id": keys.get("id"), "vessel_name": row_name,
                               "imo": row_imo, "confidence": confidence, "reason": reason})
    return candidates


def main() -> int:
    argp = argparse.ArgumentParser()
    argp.add_argument("--listing-url", default=DEFAULT_LISTING)
    argp.add_argument("--limit", type=int, default=20)
    argp.add_argument("--master", type=Path)
    argp.add_argument("--output", type=Path, default=Path("reports/auction-feasibility.json"))
    argp.add_argument("--raw-dir", type=Path, default=Path("reports/auction-raw"))
    args = argp.parse_args()
    report: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": args.listing_url,
        "status": "started",
        "auctions": [],
        "errors": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        listing = fetch(args.listing_url)
        args.raw_dir.mkdir(parents=True, exist_ok=True)
        (args.raw_dir / "closed-auction-listing.html").write_text(listing, encoding="utf-8")
        listing_text = visible_text(listing).lower()
        if "registration required" in listing_text and "only registered users" in listing_text:
            raise RegistrationRequired(
                "ACP restricts auction viewing to registered Panama local steamship agents"
            )
        ids = auction_ids(listing)[: args.limit]
        if not ids:
            raise RuntimeError("No auction IDs were discovered on the closed-auction page")
        vessels = load_vessels(args.master)
        for auction_id in ids:
            try:
                detail_url = urljoin(BASE_URL, f"APViewItem.asp?ID={auction_id}")
                bids_url = urljoin(BASE_URL, f"APBidHistory.asp?AucID={auction_id}")
                detail_html, bids_html = fetch(detail_url), fetch(bids_url)
                (args.raw_dir / f"{auction_id}-detail.html").write_text(detail_html, encoding="utf-8")
                (args.raw_dir / f"{auction_id}-bids.html").write_text(bids_html, encoding="utf-8")
                auction = parse_auction(auction_id, detail_html, bids_html)
                row = asdict(auction)
                row["candidate_matches"] = candidate_matches(auction, vessels)
                row["raw_sha256"] = hashlib.sha256((detail_html + bids_html).encode()).hexdigest()
                report["auctions"].append(row)  # type: ignore[union-attr]
            except Exception as exc:
                report["errors"].append({"auction_id": auction_id, "error": str(exc)})  # type: ignore[union-attr]
        report["status"] = "complete"
        report["auction_count"] = len(report["auctions"])  # type: ignore[arg-type]
    except RegistrationRequired as exc:
        report["status"] = "registration_required"
        report["errors"].append({"stage": "listing", "error": str(exc)})  # type: ignore[union-attr]
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0
    except Exception as exc:
        report["status"] = "source_unavailable"
        report["errors"].append({"stage": "listing", "error": str(exc)})  # type: ignore[union-attr]
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 2
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
