
from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

ACCESS_FILE = ROOT / "data" / "gold" / "healthcare_accessibility_by_population_cell.csv"
FACILITY_FILE = ROOT / "data" / "silver" / "healthcare_network_matches_20261011_122708.csv"

AUDIT_FILE = ROOT / "data" / "silver" / "full_accessibility_audit.csv"
REPORT_FILE = ROOT / "reports" / "full_accessibility_audit_summary.json"


def normalize_id(value):
    if pd.isna(value):
        return None
    return str(value).strip().removesuffix(".0")


def main():
    print("AURIS-X Full Accessibility Audit")
    print("Read-only audit of existing results.")
    print("Original accessibility files will not be modified.")

    if not ACCESS_FILE.exists():
        raise FileNotFoundError(f"Missing input: {ACCESS_FILE}")
    if not FACILITY_FILE.exists():
        raise FileNotFoundError(f"Missing input: {FACILITY_FILE}")

    access = pd.read_csv(ACCESS_FILE)
    facilities = pd.read_csv(
        FACILITY_FILE,
        dtype={"osm_id": "string"},
    )

    required = [
        "population_cell_id",
        "driving_distance_m",
        "walking_distance_m",
        "driving_reachable",
        "walking_reachable",
        "driving_facility_id",
        "walking_facility_id",
    ]

    missing = [column for column in required if column not in access.columns]
    if missing:
        raise ValueError(
            "Accessibility file is missing required columns: "
            + ", ".join(missing)
        )

    facilities["osm_id_norm"] = facilities["osm_id"].map(normalize_id)
    known_facility_ids = set(facilities["osm_id_norm"].dropna())

    access["driving_facility_id_norm"] = (
        access["driving_facility_id"].map(normalize_id)
    )
    access["walking_facility_id_norm"] = (
        access["walking_facility_id"].map(normalize_id)
    )

    drive_distance = pd.to_numeric(
        access["driving_distance_m"], errors="coerce"
    )
    walk_distance = pd.to_numeric(
        access["walking_distance_m"], errors="coerce"
    )

    drive_reachable = access["driving_reachable"].astype("string").str.lower().map(
        {"true": True, "false": False, "1": True, "0": False}
    )
    walk_reachable = access["walking_reachable"].astype("string").str.lower().map(
        {"true": True, "false": False, "1": True, "0": False}
    )

    drive_has_distance = drive_distance.notna()
    walk_has_distance = walk_distance.notna()

    drive_flag_mismatch = (
        drive_reachable.notna()
        & (drive_reachable != drive_has_distance)
    )
    walk_flag_mismatch = (
        walk_reachable.notna()
        & (walk_reachable != walk_has_distance)
    )

    drive_has_id = access["driving_facility_id_norm"].notna()
    walk_has_id = access["walking_facility_id_norm"].notna()

    drive_id_unknown = (
        drive_has_id
        & ~access["driving_facility_id_norm"].isin(known_facility_ids)
    )
    walk_id_unknown = (
        walk_has_id
        & ~access["walking_facility_id_norm"].isin(known_facility_ids)
    )

    drive_distance_invalid = (
        drive_distance.notna() & (drive_distance < 0)
    )
    walk_distance_invalid = (
        walk_distance.notna() & (walk_distance < 0)
    )

    both_distances = drive_distance.notna() & walk_distance.notna()
    distance_difference = (drive_distance - walk_distance).abs()

    audit = pd.DataFrame({
        "population_cell_id": access["population_cell_id"],
        "driving_distance_m": drive_distance,
        "walking_distance_m": walk_distance,
        "driving_reachable": drive_reachable,
        "walking_reachable": walk_reachable,
        "driving_facility_id": access["driving_facility_id_norm"],
        "walking_facility_id": access["walking_facility_id_norm"],
        "driving_has_distance": drive_has_distance,
        "walking_has_distance": walk_has_distance,
        "driving_has_facility_id": drive_has_id,
        "walking_has_facility_id": walk_has_id,
        "driving_reachability_flag_mismatch": drive_flag_mismatch,
        "walking_reachability_flag_mismatch": walk_flag_mismatch,
        "driving_unknown_facility_id": drive_id_unknown,
        "walking_unknown_facility_id": walk_id_unknown,
        "driving_negative_distance": drive_distance_invalid,
        "walking_negative_distance": walk_distance_invalid,
        "both_modes_have_distance": both_distances,
        "absolute_mode_distance_difference_m": distance_difference,
        "distances_equal_within_1cm": (
            both_distances & (distance_difference <= 0.01)
        ),
    })

    audit["audit_issue_count"] = (
        audit[
            [
                "driving_reachability_flag_mismatch",
                "walking_reachability_flag_mismatch",
                "driving_unknown_facility_id",
                "walking_unknown_facility_id",
                "driving_negative_distance",
                "walking_negative_distance",
            ]
        ].fillna(False).astype(bool).sum(axis=1)
    )

    # Preserve existing outputs: write only to new audit destinations.
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(AUDIT_FILE, index=False)

    both_reachable = drive_has_distance & walk_has_distance
    only_drive = drive_has_distance & ~walk_has_distance
    only_walk = walk_has_distance & ~drive_has_distance
    neither = ~drive_has_distance & ~walk_has_distance

    valid_differences = distance_difference[both_distances]

    summary = {
        "title": "AURIS-X full accessibility consistency audit",
        "read_only_of_original_data": True,
        "input_rows": int(len(access)),
        "unique_population_cell_ids": int(
            access["population_cell_id"].nunique()
        ),
        "duplicate_population_cell_id_rows": int(
            access["population_cell_id"].duplicated().sum()
        ),
        "known_source_facility_ids": int(len(known_facility_ids)),
        "driving": {
            "rows_with_distance": int(drive_has_distance.sum()),
            "rows_without_distance": int((~drive_has_distance).sum()),
            "rows_with_facility_id": int(drive_has_id.sum()),
            "unknown_assigned_facility_ids": int(drive_id_unknown.sum()),
            "reachability_flag_mismatches": int(drive_flag_mismatch.sum()),
            "negative_distances": int(drive_distance_invalid.sum()),
        },
        "walking": {
            "rows_with_distance": int(walk_has_distance.sum()),
            "rows_without_distance": int((~walk_has_distance).sum()),
            "rows_with_facility_id": int(walk_has_id.sum()),
            "unknown_assigned_facility_ids": int(walk_id_unknown.sum()),
            "reachability_flag_mismatches": int(walk_flag_mismatch.sum()),
            "negative_distances": int(walk_distance_invalid.sum()),
        },
        "reachability_comparison": {
            "both_modes_have_distance": int(both_reachable.sum()),
            "driving_only_has_distance": int(only_drive.sum()),
            "walking_only_has_distance": int(only_walk.sum()),
            "neither_mode_has_distance": int(neither.sum()),
        },
        "distance_comparison": {
            "rows_with_both_distances": int(both_distances.sum()),
            "equal_within_0_01m": int(
                (both_distances & (distance_difference <= 0.01)).sum()
            ),
            "median_absolute_difference_m": (
                float(valid_differences.median())
                if len(valid_differences) else None
            ),
            "p90_absolute_difference_m": (
                float(valid_differences.quantile(0.90))
                if len(valid_differences) else None
            ),
            "maximum_absolute_difference_m": (
                float(valid_differences.max())
                if len(valid_differences) else None
            ),
        },
        "rows_with_any_detected_consistency_issue": int(
            (audit["audit_issue_count"] > 0).sum()
        ),
        "outputs": {
            "audit_csv": str(AUDIT_FILE.relative_to(ROOT)),
            "summary_json": str(REPORT_FILE.relative_to(ROOT)),
        },
        "limitations": [
            "This audit checks internal consistency, not real-world accuracy.",
            "A known facility ID does not prove that the facility is operational.",
            "Different driving and walking networks can legitimately yield similar distances.",
            "Identical distances require investigation but are not by themselves proof of an error.",
            "This audit does not recompute shortest paths for every population cell.",
        ],
    }

    REPORT_FILE.write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    print("\nAUDIT SUMMARY")
    print(json.dumps(summary, indent=2))
    print("\nCreated:")
    print(AUDIT_FILE)
    print(REPORT_FILE)
    print("\nExisting accessibility outputs were not modified.")


if __name__ == "__main__":
    main()
