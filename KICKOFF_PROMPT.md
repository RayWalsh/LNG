Paste the text below as your first message to Claude Code, once you've:

  1. Created a new (empty) GitHub repo
  2. Copied all the files from this package into it and pushed an initial
     commit (or just pushed this whole folder as the first commit)
  3. Opened that repo in Claude Code on the web (claude.ai/code) — no
     local install needed

------------------------------------------------------------------------
PROMPT TO PASTE INTO CLAUDE CODE:
------------------------------------------------------------------------

Read CLAUDE.md and README.md in this repo first — they explain the
project and the constraints.

This repo pulls Panama Canal LPG wait-time data from Vortexa reports on
a schedule via GitHub Actions and publishes a dashboard to GitHub Pages.
The code is a first draft written from public documentation and has
never been run against a real Vortexa account, so some of it is
probably wrong.

I've already completed the two manual GitHub setup steps from the
README (added VORTEXA_API_KEY as a repo secret, and set Pages source to
"GitHub Actions"). [Only include this line once you've actually done
both — otherwise tell Claude Code you haven't yet, and ask it to wait /
remind you before triggering a run.]

Please:

1. Review scripts/fetch_panama_wait_times.py and
   .github/workflows/update-and-deploy.yml for obvious problems.
2. Trigger the workflow (workflow_dispatch) and read the run logs.
3. If it fails, diagnose from the actual error in the logs — not from
   guessing — and fix the script. Common likely issues are listed in
   CLAUDE.md under "Known unknowns."
4. Iterate: fix, commit, push, re-run, re-read logs, until a run
   succeeds end to end.
5. Once it succeeds, check the deployed Pages URL and confirm it's
   showing real data, not the sample-data fallback (there's a visible
   banner when it's sample data).
6. Update the "Known unknowns" section of CLAUDE.md with whatever you
   learned that turned out to be different from what was assumed, so
   future sessions don't have to rediscover it.

Do not put the Vortexa API key anywhere in this session, in any file, or
in the Claude Code environment variables field — it should only ever be
read by the GitHub Actions workflow from the repo secret. If you need to
see what a real API response looks like, get it from the Actions run
logs, not by running the script directly in this session.

Open a PR with your changes rather than pushing straight to main, so I
can review before it goes live.

------------------------------------------------------------------------

A couple of tips for the session itself:

- If Claude Code asks you to add temporary debug print statements to a
  workflow step (e.g. to print `dir(vortexasdk)` or a real search()
  signature) — that's expected and fine. Just make sure it removes them
  again once the real answer is known, and folds the answer into
  CLAUDE.md instead.
- If the very first run fails because of the two manual setup steps
  (missing secret / wrong Pages source) rather than a code bug, go back
  and do those in the GitHub UI, then re-trigger.
