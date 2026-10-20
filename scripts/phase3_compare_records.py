import csv
from pathlib import Path

root = Path.cwd()

def read_csv(rel):
    with (root / rel).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def key(r):
    return (r.get("osm_type", "").strip(), r.get("osm_id", "").strip())

pairs = [
    ("TRANSPORT",
     "data/staging/category_ingestion/transport_ingested_20261015T160811Z.csv",
     "reports/phase3_test_transport/transport_ingested_20261017T054400Z.csv"),
    ("WATER",
     "data/staging/category_ingestion/water_ingested_20261015T160811Z.csv",
     "reports/phase3_test_water/water_ingested_20261017T054400Z.csv"),
]

for label, old_path, new_path in pairs:
    old, new = read_csv(old_path), read_csv(new_path)
    old_keys, new_keys = {key(r) for r in old}, {key(r) for r in new}
    print(f"\n=== {label} ===")
    print("Staged:", len(old), "Test:", len(new))
    print("Only in staged:", len(old_keys - new_keys))
    for r in old:
        if key(r) in old_keys - new_keys:
            print("  STAGED ONLY:", key(r), r.get("facility_name", ""))
    print("Only in test:", len(new_keys - old_keys))
    for r in new:
        if key(r) in new_keys - old_keys:
            print("  TEST ONLY:", key(r), r.get("facility_name", ""))

edu = read_csv("reports/education_unmatched_review_register.csv")
print("\n=== EDUCATION REVIEW REGISTER ===")
for r in edu:
    print(
        r.get("osm_type", ""), r.get("osm_id", ""),
        "|", r.get("name", ""),
        "| disposition:", repr(r.get("disposition", "")),
        "| reason:", repr(r.get("reason", "")),
        "| frozen_dataset_changed:", repr(r.get("frozen_dataset_changed", ""))
    )
