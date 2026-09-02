# Panama Canal Intelligence

GitHub-hosted dashboard for LPG, LNG, and tanker Panama Canal wait times from
Vortexa's periodic Panama Canal Excel report.

## Upload fresh data

Upload a new `.xlsx` report to `uploads/incoming/` on GitHub. The workflow
validates and merges it into the persistent dataset, rebuilds the dashboard,
and deploys GitHub Pages. See **[UPLOAD_DATA.md](UPLOAD_DATA.md)** for exact
click-by-click instructions.

The workbook is not the source of truth:

- `historic` is cumulatively upserted by Vortexa's stable transit `id`.
- `waiting` replaces the previous live-waiting snapshot.
- `future` replaces the previous future-transits snapshot.
- `data/master_transits.csv` is the consolidated source of truth.
- `reports/latest-import.json` records the latest successful import.

Structural validation happens before persistent data is changed.

## Project structure

```text
uploads/incoming/                 Fresh .xlsx upload location
scripts/ingest_vortexa_report.py  Validation, snapshot replacement, and upsert
scripts/build_dashboard_data.py   Dashboard aggregation
data/master_transits.csv          Persistent consolidated dataset
reports/latest-import.json        Latest successful import report
site/index.html                   Static dashboard
.github/workflows/ingest-and-deploy.yml
                                  Test, import, commit, and Pages deployment
```

## Local verification

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/ingest_vortexa_report.py path/to/report.xlsx
python scripts/build_dashboard_data.py
```

The older Vortexa API probes are diagnostic only. Normal uploads do not use
`VORTEXA_API_KEY`.
