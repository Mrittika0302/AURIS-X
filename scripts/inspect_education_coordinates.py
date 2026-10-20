
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
        raise FileNotFoundError("No cleaned Education CSV found.")

    csv_path = files[0]
    df = pd.read_csv(csv_path)

    lat = pd.to_numeric(df["latitude"], errors="coerce")
    lon = pd.to_numeric(df["longitude"], errors="coerce")

    inside = (
        lat.between(SOUTH, NORTH)
        & lon.between(WEST, EAST)
    )

    outside = df.loc[~inside].copy()
    outside["latitude"] = lat.loc[~inside]
    outside["longitude"] = lon.loc[~inside]

    print("=" * 60)
    print("EDUCATION COORDINATE REVIEW")
    print("=" * 60)
    print(f"Source: {csv_path}")
    print(f"Records outside bounding box: {len(outside)}")

    columns = [
        col for col in [
            "osm_type", "osm_id", "osm_key", "name", "name_en",
            "facility_type", "latitude", "longitude"
        ]
        if col in outside.columns
    ]

    if outside.empty:
        print("No out-of-bounds records found.")
    else:
        print("\nReview these records:")
        print(outside[columns].to_string(index=False))

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = REPORT_DIR / "education_out_of_bounds_review.csv"
    outside[columns].to_csv(output_path, index=False, encoding="utf-8-sig")

    summary = {
        "source_file": str(csv_path.relative_to(ROOT)),
        "total_records": int(len(df)),
        "inside_bbox": int(inside.sum()),
        "outside_bbox": int((~inside).sum()),
        "bbox": {
            "south": SOUTH,
            "west": WEST,
            "north": NORTH,
            "east": EAST,
        },
        "review_file": str(output_path.relative_to(ROOT)),
        "decision": "No records removed or coordinates modified.",
    }

    summary_path = REPORT_DIR / "education_coordinate_review.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nReview CSV saved: {output_path}")
    print(f"Review summary saved: {summary_path}")
    print("\nNo source data was modified.")


if __name__ == "__main__":
    main()
