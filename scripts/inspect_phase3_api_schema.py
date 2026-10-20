import csv
from pathlib import Path

folder = Path("data/staging/category_ingestion")
files = [
    "transport_ingested_20261015T160811Z.csv",
    "parks_ingested_20261015T162230Z.csv",
    "water_ingested_20261015T160811Z.csv",
    "sanitation_ingested_20261015T160812Z.csv",
    "emergency_services_ingested_20261015T160812Z.csv",
]

for filename in files:
    path = folder / filename
    print(f"\n--- {filename} ---")
    if not path.exists():
        print("MISSING FILE")
        continue

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        print("Columns:", reader.fieldnames)
        first = next(reader, None)
        if first:
            print("Example service_domain:", first.get("service_domain"))
            print("Example facility_category:", first.get("facility_category"))
            print("Example source:", first.get("source"))
