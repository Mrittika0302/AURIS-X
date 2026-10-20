import csv
from pathlib import Path
from collections import Counter

root = Path.cwd()

files = {
    "education_review": root / "reports/education_unmatched_review_register.csv",
    "transport_staged": root / "data/staging/category_ingestion/transport_ingested_20261015T160811Z.csv",
    "transport_test": root / "reports/phase3_test_transport/transport_ingested_20261017T054400Z.csv",
    "water_staged": root / "data/staging/category_ingestion/water_ingested_20261015T160811Z.csv",
    "water_test": root / "reports/phase3_test_water/water_ingested_20261017T054400Z.csv",
}

def inspect(path):
    if not path.exists():
        print(f"\nMISSING: {path.relative_to(root)}")
        return
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        headers = reader.fieldnames or []
    print(f"\nFILE: {path.relative_to(root)}")
    print(f"Data rows: {len(rows)}")
    print(f"Columns ({len(headers)}): {headers}")

    if "education_review" in path.name:
        for col in headers:
            values = [str(r.get(col, "")).strip() for r in rows]
            if any(word in col.lower() for word in ("status", "reason", "decision", "match", "review")):
                print(f"  {col} values: {dict(Counter(v or '[blank]' for v in values))}")

for name, path in files.items():
    inspect(path)
