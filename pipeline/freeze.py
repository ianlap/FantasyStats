"""Mark a season's raw data as finalized so pulls never touch it again.

Run after a season fully ends: uv run python -m pipeline.freeze 2025
The flag lives in the committed meta.json, so CI respects it too.
"""

import argparse
import json

from pipeline.config import RAW_DIR


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("season", type=int)
    args = parser.parse_args()
    path = RAW_DIR / str(args.season) / "meta.json"
    if not path.exists():
        raise SystemExit(f"No meta.json for season {args.season} at {path}")
    meta = json.loads(path.read_text())
    meta["finalized"] = True
    path.write_text(json.dumps(meta, indent=1))
    print(f"Season {args.season} finalized: pulls will skip it from now on.")


if __name__ == "__main__":
    main()
