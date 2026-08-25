"""
VoyagesSearchEnriched's confirmed valid-columns list (obtained earlier
via a deliberate 400 error) has no draft field. VesselPositions (which
plausibly would have draft, being raw AIS-derived) is denied on this
account. This script checks whether CargoMovements — the other major
accessible endpoint — has anything draft-related, using the same trick:
deliberately request an invalid `columns` value so the API's own
validation error lists every real valid option. First prints the real
signature, since CargoMovements may not even have a `columns` param the
same way VoyagesSearchEnriched does.
"""

import inspect
from datetime import datetime, timedelta

from vortexasdk import CargoMovements


def main():
    now = datetime.utcnow()
    thirty_days_ago = now - timedelta(days=30)

    print("--- Real CargoMovements.search() signature ---")
    sig = inspect.signature(CargoMovements().search)
    print(sig)
    has_columns_param = "columns" in sig.parameters
    print(f"\nHas a 'columns' parameter: {has_columns_param}\n")

    if has_columns_param:
        print("--- Deliberately triggering a 400 to reveal valid columns ---")
        try:
            CargoMovements().search(
                filter_time_min=thirty_days_ago,
                filter_time_max=now,
                columns=["__deliberately_invalid_column__"],
            )
            print("No error raised — unexpected.")
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            print(msg)
            if "draft" in msg.lower():
                print("\n*** 'draft' appears in the valid columns list! ***")
            else:
                print("\nNo 'draft' mentioned in the valid columns list.")
    else:
        print("No 'columns' param on this endpoint's search() — the 400-error trick doesn't apply here.")
        print("Every parameter name from the real signature above, for manual scanning:")
        for pname in sig.parameters:
            flag = "  <-- possible draft field" if "draft" in pname.lower() else ""
            print(f"  {pname}{flag}")


if __name__ == "__main__":
    main()
