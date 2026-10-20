import csv, json
from pathlib import Path

root = Path.cwd()

def csv_rows(rel):
    with (root / rel).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def identity(r):
    return (r.get("osm_type", "").strip(), r.get("osm_id", "").strip())

for domain, staged_rel, test_rel in [
    ("TRANSPORT", "data/staging/category_ingestion/transport_ingested_20261015T160811Z.csv",
     "reports/phase3_test_transport/transport_ingested_20261017T054400Z.csv"),
    ("WATER", "data/staging/category_ingestion/water_ingested_20261015T160811Z.csv",
     "reports/phase3_test_water/water_ingested_20261017T054400Z.csv"),
]:
    staged, test = csv_rows(staged_rel), csv_rows(test_rel)
    old_ids = {identity(r) for r in staged}
    new_ids = {identity(r) for r in test}
    print(f"\n=== {domain}: DIFFERING RECORDS ===")
    for label, rows, other_ids in [
        ("STAGED ONLY", staged, new_ids),
        ("TEST ONLY", test, old_ids),
    ]:
        for r in rows:
            if identity(r) not in other_ids:
                print(label, json.dumps({
                    k: r.get(k, "") for k in [
                        "osm_type", "osm_id", "facility_name", "facility_category",
                        "latitude", "longitude", "source", "source_url",
                        "license", "source_file", "review_flags"
                    ]
                }, ensure_ascii=False))

print("\n=== EDUCATION RAW TAG LOOKUP ===")
register = csv_rows("reports/education_unmatched_review_register.csv")
raw_path = root / "data/raw/education_osm_20261013T085408Z.json"
raw = json.loads(raw_path.read_text(encoding="utf-8-sig"))
elements = raw.get("elements", []) if isinstance(raw, dict) else raw
raw_index = {
    (str(e.get("type", "")), str(e.get("id", ""))): e
    for e in elements if isinstance(e, dict)
}
for r in register:
    k = (r.get("osm_type", "").strip(), r.get("osm_id", "").strip())
    e = raw_index.get(k)
    print(k, r.get("name", ""), "| tags:",
          json.dumps((e or {}).get("tags", {}), ensure_ascii=False))
