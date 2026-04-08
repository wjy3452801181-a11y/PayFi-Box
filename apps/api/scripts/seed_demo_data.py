import argparse
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from app.db.seed_data import seed_demo_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo data for PayFi Box.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear existing data before seeding.",
    )
    args = parser.parse_args()

    stats = seed_demo_data(reset=args.reset)
    print(json.dumps({"status": "ok", "seeded": stats, "reset": args.reset}, indent=2))


if __name__ == "__main__":
    main()
