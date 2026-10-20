
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SILVER_DIR = ROOT / "data" / "silver"
REPORT_DIR = ROOT / "reports"

SOUTH, WEST, NORTH, EAST = 10.85, 76.85, 11.15, 77.15


def main():
    files = sorted(
        SILVER_DIR.glob("education_clean_*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not files:
        raise FileNotFoundError(
            "No education_clean_*.csv found in data/silver."
        )

    csv_path = files[0]
    df = pd.read_csv(csv_path)

    required_columns = [
        "osm_type", "osm_id", "osm_key", "facility_type",
        "latitude", "longitude", "has_name", "has_coordinates",
    ]

    missing_columns = [
        col for col in required_columns if col not in df.columns
    ]

    if missing_columns:
        raise ValueError(f"Required columns missing: {missing_columns}")

    lat = pd.to_numeric(df["latitude"], errors="coerce")
    lon = pd.to_numeric(df["longitude"], errors="coerce")

    valid_coords = (
        lat.between(SOUTH, NORTH)
        & lon.between(WEST, EAST)
    )

    coord_present = lat.notna() & lon.notna()
    invalid_coords = coord_present & ~valid_coords

    duplicate_keys = int(df["osm_key"].duplicated().sum())
    missing_names = int(
        df["name"].isna().sum()
    ) if "name" in df.columns else None

    report = {
        "input_file": str(csv_path.relative_to(ROOT)),
        "record_count": int(len(df)),
        "duplicate_osm_key_count": duplicate_keys,
        "missing_name_count": missing_names,
        "missing_coordinate_count": int((~coord_present).sum()),
        "coordinates_inside_study_bbox_count": int(valid_coords.sum()),
        "coordinates_outside_study_bbox_count": int(invalid_coords.sum()),
        "facility_type_counts": {
            str(k): int(v)
            for k, v in df["facility_type"].value_counts(
                dropna=False
            ).items()
        },
        "osm_type_counts": {
            str(k): int(v)
            for k, v in df["osm_type"].value_counts(
                dropna=False
            ).items()
        },
        "checks": {
            "required_columns_present": len(missing_columns) == 0,
            "osm_keys_unique": duplicate_keys == 0,
            "coordinates_within_bbox": int(invalid_coords.sum()) == 0,
        },
        "note": (
            "This is a data-quality check, not verification of real-world "
            "institution existence, operation, or educational capacity."
        ),
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = REPORT_DIR / "education_validation_report.json"

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("=" * 55)
    print("AURIS-X EDUCATION VALIDATION")
    print("=" * 55)
    print(f"Input: {csv_path}")
    print(f"Records: {len(df)}")
    print(f"Duplicate OSM keys: {duplicate_keys}")
    print(f"Missing names: {missing_names}")
    print(f"Missing coordinates: {int((~coord_present).sum())}")
    print(f"Inside bounding box: {int(valid_coords.sum())}")
    print(f"Outside bounding box: {int(invalid_coords.sum())}")

    print("\nFacility types:")
    for kind, count in df["facility_type"].value_counts(
        dropna=False
    ).items():
        print(f"  {kind}: {count}")

    print("\nValidation checks:")
    for name, passed in report["checks"].items():
        print(f"  {name}: {'PASS' if passed else 'REVIEW'}")

    print(f"\nReport saved: {output_path}")


if __name__ == "__main__":
    main()
