"""Manual diagnostic for Turkish Straits coverage in the existing Vortexa account.

The goal is deliberately diagnostic rather than production: discover the exact
Geographies objects Vortexa exposes for the Bosphorus/Istanbul Strait and the
Dardanelles/Canakkale Strait, then test our already-confirmed-accessible
VoyagesCongestionBreakdown endpoint against each candidate.

No secrets are logged. VORTEXA_API_KEY is supplied by GitHub Actions.
"""

from datetime import datetime, timedelta, timezone
import inspect

from vortexasdk import Geographies, VoyagesCongestionBreakdown

SEARCH_TERMS = [
    "bosphorus",
    "istanbul strait",
    "istanbul",
    "dardanelles",
    "canakkale",
    "canakkale strait",
    "turkish straits",
]

TARGET_WORDS = ("bosph", "dard", "strait", "canakk", "istanbul")


def discover_geographies():
    found = {}
    print("=== VORTEXA GEOGRAPHY DISCOVERY ===")
    for term in SEARCH_TERMS:
        print(f"\n--- search term: {term!r} ---")
        try:
            df = Geographies().search(term=term).to_df()
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR {type(exc).__name__}: {exc}")
            continue
        print(f"{len(df)} matches")
        if not len(df):
            continue
        cols = [c for c in ["id", "name", "layer", "parent"] if c in df.columns]
        print(df[cols].head(50).to_string(index=False))
        for _, row in df.iterrows():
            name = str(row.get("name", ""))
            if any(word in name.lower() for word in TARGET_WORDS):
                found[str(row.get("id"))] = {
                    "id": row.get("id"),
                    "name": name,
                    "layer": row.get("layer"),
                }
    return list(found.values())


def probe_congestion(candidates):
    print("\n=== VOYAGES CONGESTION BREAKDOWN ===")
    try:
        print("search signature:", inspect.signature(VoyagesCongestionBreakdown().search))
    except Exception as exc:  # noqa: BLE001
        print("Could not inspect signature:", exc)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    start = now - timedelta(days=30)

    if not candidates:
        print("No Turkish Straits-like geographies found; no congestion calls attempted.")
        return

    for geo in candidates:
        print(f"\n--- {geo['name']} | layer={geo.get('layer')} | id={geo['id']} ---")
        try:
            df = VoyagesCongestionBreakdown().search(
                time_min=start,
                time_max=now,
                locations=geo["id"],
                breakdown_property="port",
            ).to_df()
            print(f"SUCCESS: {len(df)} rows")
            print("columns:", list(df.columns))
            if len(df):
                print(df.head(20).to_string(index=False))
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR {type(exc).__name__}: {exc}")


def main():
    candidates = discover_geographies()
    print("\n=== CANDIDATE SUMMARY ===")
    for geo in candidates:
        print(geo)
    probe_congestion(candidates)


if __name__ == "__main__":
    main()
