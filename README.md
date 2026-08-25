# Panama Canal LPG Wait Times

Tracks Panama Canal transit wait times for confirmed LPG carriers in three cubic-capacity bands
(~84,000, ~88,000, and ~95,000 CBM), sourced from Vortexa's Panama Canal Report,
and publishes a dashboard showing:

- current average wait time per band, by direction
- a weekly trend over the past year
- a 5-year seasonal range (min/max/avg by week-of-year) with the past year
  overlaid, so you can see where "now" sits against history
- a live snapshot of vessels currently in the queue

The working vessel groups are 84k CBM Panamax, 88k CBM Super Panamax,
and 95k CBM Neo Panamax. The dashboard filters on Vortexa's `LPG Carriers`
vessel type before applying these capacity bands. Because the report does not
include nameplate capacity, the maximum observed cargo cubic volume for each
vessel is used as a documented working proxy.

Everything runs in GitHub — no local machine required, so it works the
same from any computer.

## How it works

```
scripts/fetch_panama_wait_times.py   -> pulls data from Vortexa, writes site/panama_wait_times.json
site/index.html                      -> static dashboard that reads that JSON
.github/workflows/update-and-deploy.yml
                                      -> runs the script on a schedule (every 6h)
                                         and publishes site/ via GitHub Pages
```

Nothing is committed back to the repo by the workflow — each run rebuilds
the JSON fresh and deploys it straight to Pages. If a run fails (e.g. a
Vortexa API hiccup), the previous successful deployment just stays live
until the next run succeeds.

## One-time setup (does this once, in the GitHub web UI — nothing local)

1. **Add the Vortexa API key as a repository secret.**
   Repo → **Settings** → **Secrets and variables** → **Actions** →
   **New repository secret** → name it `VORTEXA_API_KEY`, paste your key,
   save.
   Do **not** put the real key in `.env`, in a commit, or in a Claude Code
   chat message — this is the only place it should ever live. Claude
   Code's cloud sessions have no secrets store of their own, so this
   repository secret is what the workflow uses to authenticate.

2. **Enable GitHub Pages, source = GitHub Actions.**
   Repo → **Settings** → **Pages** → under "Build and deployment", set
   **Source** to **GitHub Actions**. (Not "Deploy from a branch" — we
   want the workflow-driven deployment above.)

3. **Run the workflow once manually** to confirm it works end to end.
   Repo → **Actions** tab → **Update Panama Canal data and deploy
   dashboard** → **Run workflow**. Watch the logs — this is where you'll
   see whether `vortexasdk`'s `CanalTransit` class/filters match what the
   script assumes (see the note at the top of the script — this was
   built from public docs and not yet verified against a live account).

4. **Find your live URL.**
   Repo → **Settings** → **Pages** will show something like
   `https://<your-username>.github.io/<repo-name>/` once the first
   deployment succeeds.

After that, it just runs itself every 6 hours. Adjust the schedule in
`.github/workflows/update-and-deploy.yml` (the `cron` line) if you want
it more or less frequent.

## If the first run fails

Almost certainly it will, on the very first try — that's expected. The
script's data-fetching logic was written from Vortexa's *public* SDK
documentation, not tested against a real account. Common first-run fixes:

- **`ImportError: cannot import name 'CanalTransit'`** — the class name
  might differ in your installed SDK version. Check the Actions log, or
  ask Claude Code to run `python3 -c "from vortexasdk import *; print([x for x in dir() if 'anal' in x.lower()])"` inside a throwaway debug workflow step to find the real name.
- **A `search()` TypeError about unexpected keyword arguments** — the
  filter names on `CanalTransit().search()` weren't confirmed from public
  docs (see the note in `fetch_panama_wait_times.py`). Ask Claude Code to
  add a temporary debug step that runs
  `python3 -c "from vortexasdk import CanalTransit; help(CanalTransit().search)"`
  as a workflow step, read the real signature from the log, and fix the
  script.
- **Empty results / permissions error** — your Vortexa plan may not
  include canal-level transit data (some plans are cargo/flows only).
  Worth confirming with your Vortexa account contact.

See `CLAUDE.md` for how to hand this whole debugging loop to Claude Code.

## Local structure reference

- `scripts/fetch_panama_wait_times.py` — the data pull + aggregation logic
- `site/index.html` — the dashboard (falls back to clearly-labeled sample
  data if `panama_wait_times.json` isn't found, so it's never blank)
- `.github/workflows/update-and-deploy.yml` — the scheduler + deployer
- `requirements.txt` — Python dependencies
- `.env.example` — reference only, for optional local debugging
