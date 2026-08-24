"""
Vortexa API Access Audit
=========================

There's no dedicated "list my permissions" endpoint in the Vortexa API,
so this script empirically tests access to every read-type endpoint
exposed by the installed vortexasdk: for each endpoint class with a
.search() method, it inspects the REAL method signature (via
inspect.signature — no guessing at param names), builds a minimal
request (setting any obviously time-range-shaped parameters to a small
recent window, leaving everything else at its default), and classifies
the result:

  ACCESSIBLE        the call succeeded (may return 0 rows — that's fine,
                     it means the endpoint itself is authorised)
  DENIED (401/403)  the API explicitly rejected the request on
                     permissions grounds — not included in your plan
  ERROR             some other exception (bad params, network, etc.) —
                     inconclusive, read the message
  SKIPPED           either the search() method requires an argument this
                     script can't safely guess (e.g. a specific
                     product/vessel ID), or the endpoint looks like it
                     WRITES data (name contains "Post") and has been
                     deliberately excluded for safety

Run via GitHub Actions (see .github/workflows/audit-vortexa-access.yml)
so VORTEXA_API_KEY is only ever read from the repo secret, never typed
anywhere else.
"""

import inspect
from datetime import datetime, timedelta

import vortexasdk

# Endpoint names containing any of these substrings are skipped
# automatically without being called at all — they look like they
# submit/write data rather than just read it, and we never want a
# permissions probe to have side effects.
WRITE_LIKE_SUBSTRINGS = ["Post", "Create", "Update", "Delete", "Submit"]


def find_endpoint_classes():
    classes = []
    for name in dir(vortexasdk):
        if name.startswith("_"):
            continue
        obj = getattr(vortexasdk, name)
        if inspect.isclass(obj) and hasattr(obj, "search"):
            classes.append((name, obj))
    return classes


def build_kwargs_for(search_method):
    """
    Best-effort: fill in any *_time_min / *_time_max-shaped parameters
    with a small recent window, leave everything else at default. If any
    OTHER parameter is required (no default), we can't safely guess a
    value for it — signal that by returning None so the caller can mark
    this endpoint as SKIPPED rather than send a bogus request.
    """
    sig = inspect.signature(search_method)
    kwargs = {}
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)

    for pname, param in sig.parameters.items():
        if pname == "self":
            continue
        has_default = param.default is not inspect.Parameter.empty
        looks_like_time_window = "time" in pname and (
            pname.endswith("_min") or pname.endswith("_max")
        )
        if looks_like_time_window:
            kwargs[pname] = week_ago if pname.endswith("_min") else now
        elif not has_default:
            return None  # required param we can't safely guess

    return kwargs


def classify(bound_search_method):
    try:
        kwargs = build_kwargs_for(bound_search_method)
        if kwargs is None:
            return "SKIPPED", "requires a specific argument this script can't safely guess"

        result = bound_search_method(**kwargs)
        df = result.to_df()
        return "ACCESSIBLE", f"{len(df)} rows returned"

    except ValueError as e:
        msg = str(e)
        if "403" in msg or "401" in msg or "permission" in msg.lower():
            return "DENIED", msg
        return "ERROR", msg

    except TypeError as e:
        return "ERROR", f"TypeError: {e}"

    except Exception as e:  # noqa: BLE001 - deliberately broad, this is a diagnostic script
        return "ERROR", f"{type(e).__name__}: {e}"


def main():
    all_classes = find_endpoint_classes()
    print(f"Found {len(all_classes)} endpoint classes with a .search() method.\n")

    results = []
    for name, cls in all_classes:
        if any(w in name for w in WRITE_LIKE_SUBSTRINGS):
            results.append((name, "SKIPPED", "looks like a write/submit endpoint — excluded for safety"))
            continue

        try:
            instance = cls()
        except Exception as e:  # noqa: BLE001
            results.append((name, "ERROR", f"could not instantiate: {e}"))
            continue

        status, detail = classify(instance.search)
        results.append((name, status, detail))

    width = max(len(r[0]) for r in results) + 2
    print(f"{'Endpoint':<{width}}{'Status':<12}Detail")
    print("-" * 100)
    for name, status, detail in sorted(results, key=lambda r: (r[1], r[0])):
        print(f"{name:<{width}}{status:<12}{detail}")

    accessible = [r for r in results if r[1] == "ACCESSIBLE"]
    denied = [r for r in results if r[1] == "DENIED"]
    other = len(results) - len(accessible) - len(denied)
    print(
        f"\n{len(accessible)} accessible, {len(denied)} explicitly denied, "
        f"{other} inconclusive/skipped (see SKIPPED/ERROR rows above)."
    )


if __name__ == "__main__":
    main()
