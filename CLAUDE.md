# Project context for Claude Code

## What this repo does

Pulls Panama Canal LNG transit wait-time data from the Vortexa API,
aggregates it (current averages, weekly trend, 5-year seasonal range),
and publishes a static dashboard via GitHub Pages. Everything runs on a
schedule inside GitHub Actions — there is no local/manual run in normal
operation.

Read `README.md` first for the full picture and the one-time manual
setup steps (repo secret, Pages source) that only the human can do via
the GitHub web UI.

## Critical: secrets

- The real `VORTEXA_API_KEY` lives ONLY as a GitHub Actions repository
  secret (Settings → Secrets and variables → Actions).
- Never write it into any file in this repo, never ask the user to paste
  it into chat, and never put it in a Claude Code cloud environment's
  "Environment variables" field — that field is plaintext and has no
  secrets store; Anthropic's own docs warn against putting credentials
  there.
- You cannot execute the fetch script against real data from within a
  Claude Code session. Validation happens by editing the code, pushing,
  and reading the GitHub Actions run logs (which have access to the real
  secret) — or by asking the user to paste back the log output / error
  text (never the key itself).

## Current data source (as of this pivot)

**CanalTransit is NOT used.** It was the original, ideal choice but is
confirmed denied (401/403) on this Vortexa account — verified twice
independently, and confirmed as part of a broader denied group
(Fixtures, Freight Pricing, Vessel Availability, EIA Forecasts,
VesselPositions) via `scripts/audit_vortexa_access.py`. An email is
pending with the Vortexa account team asking about that tier.

The pipeline now uses **`VoyagesCongestionBreakdown`**, confirmed
accessible and tested with real filtered pulls. Full detail — including
several non-obvious things learned only through live testing, not from
any documentation — is in the docstring at the top of
`scripts/fetch_panama_wait_times.py`. Read that before changing the
data-fetching logic. Highlights:

- `locations` = the Panama Canal waypoint's Geographies ID filters TO
  voyages congested there; `breakdown_property` only accepts
  `"port"`/`"terminal"`/`"shipping_region"` — there's no way to get
  "Panama Canal" itself as a result label, so results always come back
  grouped by port and get aggregated in this script.
- No true northbound/southbound field exists on this endpoint — the
  dashboard shows Laden/Ballast instead, honestly labelled as such.
- No live per-vessel queue exists on this endpoint —
  `current_queue` is intentionally always `[]`.
- 5-year seasonal range isn't implemented for this data source yet
  (would cost ~250 API calls per band; not attempted).

**If Vortexa grants CanalTransit access later:** switch back — check
git history for the pre-pivot version of
`scripts/fetch_panama_wait_times.py`, which had the full 5-year seasonal
range and a live queue table already built. `site/index.html` would
also need `by_status` reverted to `by_direction` (Laden/Ballast ->
Northbound/Southbound) — search the file for `by_status` to find every
spot that would need updating back.

## Confirmed facts (verified against a real Vortexa account, live)

`scripts/fetch_panama_wait_times.py` was originally written from Vortexa's
*public* SDK docs, which were incomplete on the search() filter signature.
That's now been verified for real, via GitHub Actions logs against a live
API key:

- `CanalTransit` is the correct class (confirmed via `dir(vortexasdk)`).
- The real `search()` filter kwargs (this is the actual signature, not a
  guess): `filter_canal`, `filter_direction`, `filter_lock`,
  `filter_vessel_dead_weight_min` / `_max`,
  `filter_vessel_cubic_capacity_min` / `_max`, `filter_vessel_classes`,
  `filter_vessels`, `filter_queue_arrival_time_min` / `_max`,
  `filter_canal_entry_time_min` / `_max`,
  `filter_canal_exit_time_min` / `_max`,
  `filter_booked_time_min` / `_max`, `filter_booked_status`,
  `filter_voyage_status`, plus various `exclude_*` equivalents.
  **`filter_time_min` / `filter_time_max` do NOT exist on this endpoint**
  — don't reuse that pattern from other Vortexa endpoints here.
- `filter_canal` must be the exact string `'panama_canal'`.
- `filter_direction` must be `'northbound'` or `'southbound'`.
- `filter_lock` must be `'panamax'` or `'neopanamax'`.
- DWT filtering can be pushed server-side via
  `filter_vessel_dead_weight_min` / `_max` — no need to pull everything
  and filter locally in pandas.
- `packaging` must be installed alongside `vortexasdk` and `pandas` — the
  SDK imports it internally but doesn't always pull it in as a
  transitive dependency in every environment. Already added to
  `requirements.txt`.

## Still to verify

- Whether a full 5-year pull needs chunking/pagination, or if `to_df()`
  handles it in one call — untested at that volume so far.
- Whether real transits exist at all in the 88k/95k DWT bands (a probe
  run against a real window will confirm row counts).
- Whether `canal_entry_time`, `queue_arrival_time` etc. actually parse
  cleanly as datetimes in the returned DataFrame, or need explicit
  `pd.to_datetime()` handling for a particular format/timezone quirk.

## Suggested first session

1. Read `README.md` and this file.
2. Sanity-check `scripts/fetch_panama_wait_times.py` and
   `.github/workflows/update-and-deploy.yml` for obvious issues.
3. If asked to "get this working end to end": confirm with the user that
   they've completed the two manual GitHub UI steps in `README.md`
   (repo secret + Pages source) before assuming a workflow failure is a
   code bug — a missing secret or wrong Pages source produces a failure
   that looks like a bug but isn't one.
4. Trigger a run (`workflow_dispatch` from the Actions tab, or ask the
   user to), then read the logs. Iterate on the script based on the real
   error, commit, push, re-run.
5. Once a run succeeds, confirm the deployed Pages URL actually renders
   real (non-sample) data — `site/index.html` silently falls back to
   clearly-labeled sample data if `panama_wait_times.json` is missing or
   fails to fetch, so "the page loads and looks fine" is NOT sufficient
   evidence that real data is flowing. Check for the sample-data banner.

## Conventions

- DWT bands, lookback windows, and the week-of-year anchoring logic are
  all configured near the top of `fetch_panama_wait_times.py` under
  `CONFIG` — change values there rather than editing logic further down.
- The dashboard (`site/index.html`) is a single self-contained file (no
  build step) that fetches `panama_wait_times.json` from the same
  directory. Keep it that way — no bundler, no framework — so it keeps
  working as a plain GitHub Pages deployment.
- Don't commit `panama_wait_times.json` to git; it's generated fresh by
  the workflow on every run and deployed directly, not stored in the
  repo history.
