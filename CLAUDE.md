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

## Known unknowns — verify, don't assume

`scripts/fetch_panama_wait_times.py` was written from Vortexa's *public*
SDK documentation (https://vortechsa.github.io/python-sdk/), which
confirms the `CanalTransitRecord` field names (`vessel_dead_weight`,
`queue_arrival_time`, `canal_entry_time`, `canal`, `lock`, `direction`,
etc.) but NOT:

- whether `CanalTransit` is the exact importable class name in the
  version of `vortexasdk` that gets installed
- the exact keyword arguments `CanalTransit().search()` accepts beyond
  `filter_time_min` / `filter_time_max` (which are a safe bet — every
  other endpoint in the SDK uses them)
- whether a ~5-year pull in one call is supported, or needs to be chunked
  into yearly requests and concatenated (check for pagination behavior /
  row limits in the Actions log — if `to_df()` silently truncates around
  a suspiciously round number of rows, that's the signal)
- whether the connected Vortexa account/plan actually includes
  canal-transit-level data at all (vs. only cargo movements)

Verified from Actions run 32489219895:

- `vortexasdk==1.0.29` imports the `packaging` module but does not
  install it as a transitive dependency. Keep `packaging` explicitly
  listed in `requirements.txt`.

When you get real signal on any of these (from an Actions run log, or
from the user pasting back an error), fix the script AND update this
section of CLAUDE.md with what's actually true, so the next session
doesn't re-discover it from scratch.

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
