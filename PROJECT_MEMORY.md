# Panama Canal LPG Dashboard — Project Memory

## Confirmed scope

- This project tracks **LPG**, not LNG.
- The legacy repository name and Pages path may remain `LNG` temporarily so existing links continue to work, but the product must use LPG terminology.
- LPG classification comes from Vortexa's `vessel_type = LPG Carriers` metadata.
- The 84k, 88k, and 95k figures are treated as cubic metres (CBM), not DWT.

## Vessel groups

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
