import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from app.db.seed_data import seed_demo_data


def main() -> None:
    stats = seed_demo_data(reset=True)
    print(json.dumps({"status": "ok", "seeded": stats, "reset": True}, indent=2))


if __name__ == "__main__":
    main()
