"""Copy bundled fixtures into the local staging area used by sample sources.

After running this, `config/sources.yaml`'s `sample_csv` and `sample_json`
sources can be ingested via:

    benchlens ingest --source sample_csv
    benchlens ingest --source sample_json
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
RAW_DIR = ROOT / "data" / "raw"


def main() -> int:
    csv_target = RAW_DIR / "sample_csv"
    json_target = RAW_DIR / "sample_json"
    csv_target.mkdir(parents=True, exist_ok=True)
    json_target.mkdir(parents=True, exist_ok=True)

    csv_src = FIXTURES / "sample_results.csv"
    json_src = FIXTURES / "sample_results.json"

    if not csv_src.exists() or not json_src.exists():
        print(f"Fixtures missing under {FIXTURES}.", file=sys.stderr)
        return 1

    shutil.copy(csv_src, csv_target / "sample_results.csv")
    shutil.copy(json_src, json_target / "sample_results.json")

    print(f"Staged CSV  -> {csv_target}")
    print(f"Staged JSON -> {json_target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
