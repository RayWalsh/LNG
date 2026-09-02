# Uploading a fresh Vortexa report

Use the GitHub website; no command line or API key is required.

1. Open <https://github.com/RayWalsh/LNG>.
2. Open **uploads**, then **incoming**.
3. Select **Add file** → **Upload files**.
4. Drag the fresh Vortexa `.xlsx` report onto the page.
5. Keep **Commit directly to the `main` branch** selected.
6. Select **Commit changes**.
7. Open **Actions** and select **Import uploaded report and deploy dashboard**.

A green run means the workbook was validated, merged, and deployed. Open the
run's **Summary** to see records received, added, updated, deduplicated, and
retained.

The workbook is an input, not the source of truth. Completed historic rows are
upserted into `data/master_transits.csv` by Vortexa `id`. The latest `waiting`
and `future` sheets replace the previous snapshots. After success, the uploaded
workbook is removed from `uploads/incoming`; the consolidated CSV and import
report remain.

If the run is red, open the failed step. A structurally invalid workbook never
changes the master dataset or deployed dashboard.
