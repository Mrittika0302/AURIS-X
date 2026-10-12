
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

facility_path = (
    ROOT / "data" / "silver" /
    "healthcare_network_matches_20261011_122708.csv"
)

access_path = (
    ROOT / "data" / "gold" /
    "healthcare_accessibility_by_population_cell.csv"
)

facilities = pd.read_csv(facility_path, dtype=str)
access = pd.read_csv(access_path, dtype=str)

print("\n=== FACILITY MATCH FILE ===")
print("Columns:", facilities.columns.tolist())

for col in ["osm_id", "osm_type", "drive_nearest_node_id",
            "walk_nearest_node_id"]:
    if col in facilities.columns:
        print(f"\n{col}:")
        print(facilities[col].dropna().head(10).to_list())

print("\n=== ACCESSIBILITY FILE ===")
print("Columns:", access.columns.tolist())

for col in ["driving_facility_id", "walking_facility_id"]:
    if col in access.columns:
        print(f"\n{col}:")
        print(access[col].dropna().head(10).to_list())

print("\n=== RAW STRING MATCH COUNTS ===")

if "osm_id" in facilities.columns:
    source_ids = set(facilities["osm_id"].dropna().str.strip())

    for col in ["driving_facility_id", "walking_facility_id"]:
        if col in access.columns:
            result_ids = access[col].dropna().str.strip()
            matches = result_ids.isin(source_ids)

            print(
                f"{col}: {int(matches.sum())} matching rows "
                f"out of {len(result_ids)} non-null values"
            )

print("\n=== DONE: READ-ONLY INSPECTION ===")
