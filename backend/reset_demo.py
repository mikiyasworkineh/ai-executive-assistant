"""CLI wrapper around `backend.app.demo.reset_demo_data`.

Usage (from the repo root):

    python backend/reset_demo.py                 # dry run
    python backend/reset_demo.py --yes           # clear local tables
    python backend/reset_demo.py --yes --seed    # clear, then insert demo rows
    python backend/reset_demo.py --yes --keep-google   # default: Google untouched
    python backend/reset_demo.py --yes --include-google  # also delete mirrored Google events

The same logic powers the "Reset demo" button in the UI
(POST /api/demo/reset).
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.demo import demo_counts, reset_demo_data  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--yes", action="store_true", help="actually delete (otherwise dry run)")
    parser.add_argument("--seed", action="store_true", help="insert demo events and tasks afterwards")
    parser.add_argument(
        "--include-google",
        action="store_true",
        help="also delete Google events this app booked (default: leave Google alone)",
    )
    args = parser.parse_args()

    print("Current rows:", demo_counts())
    if not args.yes:
        print("\nDry run. Re-run with --yes to apply.")
        return 0

    result = reset_demo_data(seed=args.seed, include_google=args.include_google)
    for item in result["google_touched"]:
        print(f"  {'deleted' if item['deleted'] else 'skipped'}: {item['title']} ({item['detail']})")
        print("\nRemaining rows:", result["remaining"])
    print("Done." + (" Demo data seeded." if args.seed else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
