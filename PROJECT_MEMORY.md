# Panama Canal LPG Dashboard — Project Memory

## Delivery phases

### Phase 1 — complete

Phase 1 is accepted as complete. It covers the branded Panama Canal Intelligence dashboard, LPG/LNG/Tanker segment selection, vessel-class and direction analysis, selectable wait periods, current-year seasonality, live queue, vessel detail, CSV/PDF/PPTX exports, chart copying, and the agreed navigation and presentation system.

### Phase 2 — Canal conditions and pressure index

Phase 2 will add three operational drivers of waiting time:

1. Maximum authorised draft, stored as effective-dated changes by lock/category.
2. Transit capacity and actual transits per day, distinguishing published slot availability from realised traffic.
3. Auction price/premium and auction utilisation, separated by the applicable ACP vessel group and lock.

The proposed **Panama Canal Pressure Index** is a transparent 0–100 composite in which a higher number means tighter Canal conditions. Each input must first be transformed so its direction is consistent (lower draft = more pressure; fewer slots/transits = more pressure; higher auction premium = more pressure), then normalised before aggregation. The initial version should use explicit equal or commercially agreed weights; later weights may be calibrated against out-of-sample waiting times. Auction prices should use a log transform or robust percentile because bids are highly skewed.

Do not describe the index as causal. Auction prices, transit capacity, and waits can respond to the same demand or hydrological shock, and auction prices may be endogenous. Show the three components beside the composite so users can see what moved it.

The index should be calculated by relevant segment/lock where data permits, rather than imposing one universal score. The Phase 2 UI should add a **Canal Conditions** tab with component histories, index methodology, data freshness, and event annotations. Wait-time charts should offer an optional index overlay on a secondary axis, off by default.

Preferred sources are official ACP Advisories/Notices for effective-dated draft and slot changes, ACP operations statistics for realised transits and auction utilisation, and ACP public auction history for awarded premiums. Every observation needs source URL, publication date, effective date, category/lock applicability, value, unit, and revision status.

## Presentation and navigation

- The product name is **Panama Canal Intelligence**.
- The Braemar white Bravo mark appears at the top left of the dark header.
- Overview charts and the period-filterable vessel table live on separate tabs to keep the dashboard compact.
- Summary cards use squared corners and a full green outline; chart panels use a subtle shadow.
- Every chart provides a copy-to-clipboard control for pasting as a PNG.
- The Overview/Vessel detail tabs, segment selector, and icon-only PDF/PPTX exports share one toolbar row. Icon actions provide hover tooltips.
- The selected segment (LPG, LNG, or Tankers) controls both overview and vessel-detail data and is stated in the vessel-detail view.
- Summary cards are equal square tiles and remain on one desktop row, including the five tanker classes.
- PDF export uses landscape pages and captures each visible view block at the full printable width, paginating long tables rather than shrinking the whole dashboard.
- Avoid a generic SaaS/AI-dashboard appearance: retain Braemar colours but use sharper panel geometry, restrained shadows, fewer pill controls, editorial section rules, and intentionally asymmetric alignment.
- Summary cards align to the right. The active averaging period is shown immediately above them and repeated inside each card, updating with the shared period switch.
- Seasonal background bands must use category values rather than auto-skipped tick indexes. Winter is weeks 1–9 and 49–53; summer is weeks 23–35, using only a very light tint so data remains legible.

## Dashboard period and vessel-detail definitions

- Headline averages offer trailing 3-month (90-day), 6-month (182-day), 1-year (365-day), and 5-year (1,826-day) windows; 3 months is the default.
- Seasonal charts show the current calendar year-to-date against the previous five complete calendar years, with Combined/Northbound/Southbound switches.
- Northern Hemisphere winter is marked at weeks 1–9 and 49–53; summer at weeks 23–35.
- Cargo grade comes from Vortexa's `products` field.
- The workbook has no dedicated loading date. Waiting vessels use `queue_arrival_time`; completed transits use `canal_entry_time`, and the UI must label this distinction.
- Vessel detail supports date and class filters plus full-result CSV download, including waiting records, cargo grade, origin, destination, wait, booking status, and direction.

## Confirmed scope

- This project tracks **LPG**, not LNG.
- The legacy repository name and Pages path may remain `LNG` temporarily so existing links continue to work, but the product must use LPG terminology.
- LPG classification comes from Vortexa's `vessel_type = LPG Carriers` metadata.
- The 84k, 88k, and 95k figures are treated as cubic metres (CBM), not DWT.

## Vessel groups

The dashboard has a market selector with **LPG as the default**, plus LNG and
Tankers. Changing market refreshes cards, current comparison, weekly history,
seasonal history, queue and exports.

| Representative capacity | Working class | Initial band |
| ---: | --- | ---: |
| 84,000 CBM | Panamax | 82,000–86,000 CBM |
| 88,000 CBM | Super Panamax | 86,001–90,000 CBM |
| 95,000 CBM | Neo Panamax | 93,000–97,000 CBM |

The bands are initial analytical definitions and must remain configurable.
Each group has different pricing and must remain separate throughout ingestion,
aggregation, charts, and exports.

## Primary research question

Determine whether Panama Canal waiting times for the 84k CBM Panamax LPG group
differ from the 88k CBM Super Panamax and 95k CBM Neo Panamax LPG groups.

Compare like-for-like periods and directions. Always report sample sizes and,
where possible, average, median, and the wait-time distribution. Pricing is a
separate measure and must not be presented as evidence of a waiting-time difference.

LNG initially uses the original 88k and 95k DWT groups. Tankers use Vortexa's
commercial classes: MR1, MR2, LR1, LR2/Aframax and Suezmax. Do not apply LPG
CBM bands to LNG or tanker vessels.

Weekly and seasonal sections show one chart per capacity group. Each chart defaults
to the combined result and provides a compact switch for Combined, Northbound, or
Southbound, avoiding duplicate panels while retaining directional analysis.

## Current data constraint

The Vortexa report contains historic LPG vessels under `vessel_type = LPG Carriers`
and `vessel_family = VLGC/VLEC`. It supplies cargo cubic metres rather than a
separate nameplate-capacity field, so the maximum observed cubic cargo volume for
each vessel is used as a working capacity proxy and inherited by its ballast and
waiting records. This inference must remain clearly documented.

## Next steps

1. Reingest the current report with `vessel_type` and `cubic_metres` retained.
2. Validate the capacity proxy against an authoritative vessel-capacity registry.
3. Confirm the initial CBM band boundaries with the commercial team.
4. Add authoritative group-specific pricing sources, units, routes, and dates.
5. Build a comparison view and test whether observed wait differences are meaningful.
