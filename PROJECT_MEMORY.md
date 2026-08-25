# Panama Canal LPG Dashboard — Project Memory

## Confirmed scope

- This project tracks **LPG**, not LNG.
- The legacy repository name and Pages path may remain `LNG` temporarily so existing links continue to work, but the product must use LPG terminology.
- LPG classification must come from vessel metadata. DWT alone must never be used to infer LPG.

## Vessel groups

| Representative DWT | Working class | Initial band |
| ---: | --- | ---: |
| 84,000 | Panamax | 82,000–86,000 DWT |
| 88,000 | Super Panamax | 86,001–90,000 DWT |
| 95,000 | Neo Panamax | 93,000–97,000 DWT |

The bands are initial analytical definitions and must remain configurable.
Each group has different pricing and must remain separate throughout ingestion,
aggregation, charts, and exports.

## Primary research question

Determine whether Panama Canal waiting times for the 84k DWT Panamax LPG group
differ from the 88k DWT Super Panamax and 95k DWT Neo Panamax LPG groups.

Compare like-for-like periods and directions. Always report sample sizes and,
where possible, average, median, and the wait-time distribution. Pricing is a
separate measure and must not be presented as evidence of a waiting-time difference.

## Current data constraint

The repository's existing master dataset was built from an LNG-oriented Vortexa
report and contains LNG vessel classifications. Those rows must not feed the LPG
dashboard. A Vortexa report containing LPG vessel records is required to populate
real LPG results; until then, an empty/no-data state is preferable to mislabeled data.

## Next steps

1. Obtain and ingest a Panama Canal report containing confirmed LPG vessels.
2. Validate Vortexa's exact LPG `vessel_family` values against the pipeline filter.
3. Confirm the initial DWT band boundaries with the commercial team.
4. Add authoritative group-specific pricing sources, units, routes, and dates.
5. Build a comparison view and test whether observed wait differences are meaningful.
