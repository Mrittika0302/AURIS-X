
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

ACCESS = ROOT / "data/gold/healthcare_accessibility_by_population_cell.csv"
IMPACT = ROOT / "reports/candidate_impact_top10_20261012.csv"

THRESHOLD_M = 5000.0

access = pd.read_csv(ACCESS, low_memory=False)
impact = pd.read_csv(IMPACT, low_memory=False)

candidate = impact.loc[impact["rank"] == 8].iloc[0]

drive_before = pd.to_numeric(
    access["driving_distance_m"], errors="coerce"
).to_numpy(dtype=float)

walk_before = pd.to_numeric(
    access["walking_distance_m"], errors="coerce"
).to_numpy(dtype=float)

print("Candidate:", candidate["candidate_zone_id"])
print("Population cells:", len(access))

print("\nBaseline threshold status:")
print("Driving over 5 km:", int((np.isfinite(drive_before) & (drive_before > THRESHOLD_M)).sum()))
print("Walking over 5 km:", int((np.isfinite(walk_before) & (walk_before > THRESHOLD_M)).sum()))

print("\nSimulation reported crossings:")
print("Driving:", int(candidate["driving_cells_moved_to_5km_or_less"]))
print("Walking:", int(candidate["walking_cells_moved_to_5km_or_less"]))

print("\nAccessibility data checks:")
print("Driving missing distances:", int((~np.isfinite(drive_before)).sum()))
print("Walking missing distances:", int((~np.isfinite(walk_before)).sum()))

if "population_cell_id" in access.columns:
    print("Unique population cell IDs:", int(access["population_cell_id"].nunique()))
