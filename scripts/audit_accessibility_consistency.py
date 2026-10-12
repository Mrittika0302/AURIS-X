
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent

ACCESS_FILE = (
    ROOT / "data" / "gold"
    / "healthcare_accessibility_by_population_cell.csv"
)
FACILITY_FILE = (
    ROOT / "data" / "silver"
    / "healthcare_network_matches_20261011_122708.csv"
)

REPORT_FILE = (
    ROOT / "reports" / "accessibility_consistency_audit.json"
)
CELL_AUDIT_FILE = (
    ROOT / "data" / "silver"
    / "accessibility_consistency_audit.csv"
)

TOLERANCE_M = 0.01
EXAMPLE_COUNT = 15


def load_csv(path):
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    return pd.read_csv(path, dtype=str)


def number(series):
    return pd.to_numeric(series, errors="coerce")


def clean_ids(series):
    return series.fillna("").astype(str).str.strip()


def main():
    print("AURIS-X accessibility consistency audit")
    print("Existing accessibility outputs will not be modified.")

    access = load_csv(ACCESS_FILE)
    facilities = load_csv(FACILITY_FILE)

    required = [
        "population_cell_id",
        "driving_distance_m",
        "walking_distance_m",
        "driving_facility_id",
        "walking_facility_id",
        "driving_reachable",
        "walking_reachable",
    ]

    missing = [column for column in required
               if column not in access.columns]

    if missing:
        raise ValueError(
            f"Missing accessibility columns: {missing}"
        )

    if "osm_id" not in facilities.columns:
        raise ValueError("Facility source is missing osm_id.")

    if access["population_cell_id"].duplicated().any():
        raise ValueError(
            "Duplicate population_cell_id values found."
        )

    drive = number(access["driving_distance_m"])
    walk = number(access["walking_distance_m"])

    both_valid = drive.notna() & walk.notna()
    both_missing = drive.isna() & walk.isna()
    one_missing = drive.isna() ^ walk.isna()

    difference = (drive - walk).abs()
    equal = both_valid & (difference <= TOLERANCE_M)

    drive_id = clean_ids(access["driving_facility_id"])
    walk_id = clean_ids(access["walking_facility_id"])
    source_ids = set(clean_ids(facilities["osm_id"])) - {""}

    drive_assigned = drive_id.ne("") & drive_id.ne("nan")
    walk_assigned = walk_id.ne("") & walk_id.ne("nan")

    drive_known = drive_assigned & drive_id.isin(source_ids)
    walk_known = walk_assigned & walk_id.isin(source_ids)

    same_facility = (
        both_valid
        & drive_assigned
        & walk_assigned
        & drive_id.eq(walk_id)
    )

    drive_reachable = (
        access["driving_reachable"].str.strip().str.lower()
        .isin(["true", "1", "yes"])
    )
    walk_reachable = (
        access["walking_reachable"].str.strip().str.lower()
        .isin(["true", "1", "yes"])
    )

    report = {
        "title": "AURIS-X accessibility consistency audit",
        "rows": int(len(access)),
        "unique_population_cell_ids": int(
            access["population_cell_id"].nunique()
        ),
        "duplicate_population_cell_ids": int(
            access["population_cell_id"].duplicated().sum()
        ),
        "distance_tolerance_m": TOLERANCE_M,
        "driving": {
            "valid_distance_rows": int(drive.notna().sum()),
            "missing_distance_rows": int(drive.isna().sum()),
            "reachable_flag_rows": int(drive_reachable.sum()),
            "unique_distances_rounded_to_3_decimals": int(
                drive.dropna().round(3).nunique()
            ),
            "assigned_facility_ids_found_in_source": int(
                drive_known.sum()
            ),
            "assigned_facility_ids_not_found_in_source": int(
                (drive_assigned & ~drive_known).sum()
            ),
        },
        "walking": {
            "valid_distance_rows": int(walk.notna().sum()),
            "missing_distance_rows": int(walk.isna().sum()),
            "reachable_flag_rows": int(walk_reachable.sum()),
            "unique_distances_rounded_to_3_decimals": int(
                walk.dropna().round(3).nunique()
            ),
            "assigned_facility_ids_found_in_source": int(
                walk_known.sum()
            ),
            "assigned_facility_ids_not_found_in_source": int(
                (walk_assigned & ~walk_known).sum()
            ),
        },
        "distance_comparison": {
            "both_modes_valid": int(both_valid.sum()),
            "both_modes_missing": int(both_missing.sum()),
            "only_one_mode_valid": int(one_missing.sum()),
            "equal_within_tolerance": int(equal.sum()),
            "equal_fraction_of_both_valid": (
                float(equal.sum() / both_valid.sum())
                if both_valid.any() else None
            ),
            "median_absolute_difference_m": (
                float(difference[both_valid].median())
                if both_valid.any() else None
            ),
            "p90_absolute_difference_m": (
                float(difference[both_valid].quantile(0.90))
                if both_valid.any() else None
            ),
            "maximum_absolute_difference_m": (
                float(difference[both_valid].max())
                if both_valid.any() else None
            ),
            "same_facility_id_in_both_modes": int(
                same_facility.sum()
            ),
            "equal_distances_but_different_facility_ids": int(
                (
                    equal & drive_assigned & walk_assigned
                    & drive_id.ne(walk_id)
                ).sum()
            ),
        },
        
        "reachability_flag_checks": {
            "driving_flag_true_but_distance_missing": int(
                (drive_reachable & drive.isna()).sum()
            ),
            "driving_flag_false_but_distance_present": int(
                (~drive_reachable & drive.notna()).sum()
            ),
            "walking_flag_true_but_distance_missing": int(
                (walk_reachable & walk.isna()).sum()
            ),
            "walking_flag_false_but_distance_present": int(
                (~walk_reachable & walk.notna()).sum()
            ),
        },

    }

    audit = pd.DataFrame({
        "population_cell_id": access["population_cell_id"],
        "driving_distance_m": drive,
        "walking_distance_m": walk,
        "absolute_difference_m": difference,
        "distances_equal_within_tolerance": equal,
        "driving_facility_id": drive_id,
        "walking_facility_id": walk_id,
        "same_facility_id": (
            drive_assigned & walk_assigned & drive_id.eq(walk_id)
        ),
        "driving_facility_id_found_in_source": drive_known,
        "walking_facility_id_found_in_source": walk_known,
        "driving_reachable": drive_reachable,
        "walking_reachable": walk_reachable,
    })

    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CELL_AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)

    # These are new audit files, separate from the original results.
    audit.to_csv(CELL_AUDIT_FILE, index=False)

    with open(REPORT_FILE, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2, allow_nan=False)

    print("\n=== DISTANCE COMPARISON ===")
    print(json.dumps(report["distance_comparison"], indent=2))

    print("\n=== DRIVING CHECKS ===")
    print(json.dumps(report["driving"], indent=2))

    print("\n=== WALKING CHECKS ===")
    print(json.dumps(report["walking"], indent=2))

    print("\n=== REACHABILITY FLAG CHECKS ===")
    print(json.dumps(
        report["reachability_flag_checks"], indent=2
    ))

    print("\n=== LARGEST MODE DIFFERENCES ===")
    print(
        audit.nlargest(
            EXAMPLE_COUNT, "absolute_difference_m"
        ).to_string(index=False)
    )

    print("\n=== AUDIT FILES CREATED ===")
    print(REPORT_FILE)
    print(CELL_AUDIT_FILE)
    print("\nOriginal accessibility outputs were not changed.")


if __name__ == "__main__":
    main()
