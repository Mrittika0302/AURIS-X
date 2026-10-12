
import json
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]

INPUT_CSV = (
    BASE_DIR / "data" / "silver"
    / "population_road_matches.csv"
)

OUTPUT_CSV = (
    BASE_DIR / "data" / "silver"
    / "population_road_match_audit.csv"
)

OUTPUT_JSON = (
    BASE_DIR / "reports"
    / "population_road_match_audit.json"
)

REVIEW_M = 100.0
HIGH_REVIEW_M = 250.0

OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)


def summarize(values):
    values = pd.to_numeric(values, errors="coerce").dropna()

    if values.empty:
        return {"count": 0}

    return {
        "count": int(len(values)),
        "minimum_m": round(float(values.min()), 2),
        "median_m": round(float(values.median()), 2),
        "p90_m": round(float(values.quantile(0.90)), 2),
        "p95_m": round(float(values.quantile(0.95)), 2),
        "p99_m": round(float(values.quantile(0.99)), 2),
        "maximum_m": round(float(values.max()), 2),
        "over_100m": int((values > REVIEW_M).sum()),
        "over_250m": int((values > HIGH_REVIEW_M).sum()),
        "over_100m_percent": round(
            float((values > REVIEW_M).mean() * 100), 2
        ),
    }


def main():
    if not INPUT_CSV.exists():
        raise FileNotFoundError(
            f"Input CSV not found: {INPUT_CSV}"
        )

    df = pd.read_csv(INPUT_CSV)

    required = [
        "population_cell_id",
        "latitude",
        "longitude",
        "drive_snap_distance_m",
        "walk_snap_distance_m",
        "drive_nearest_node_id",
        "walk_nearest_node_id",
    ]

    missing = [column for column in required if column not in df.columns]

    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    for column in [
        "latitude",
        "longitude",
        "drive_snap_distance_m",
        "walk_snap_distance_m",
    ]:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df["drive_review_status"] = np.select(
        [
            df["drive_snap_distance_m"] > HIGH_REVIEW_M,
            df["drive_snap_distance_m"] > REVIEW_M,
        ],
        [
            "HIGH_REVIEW_OVER_250M",
            "REVIEW_OVER_100M",
        ],
        default="WITHIN_100M",
    )

    df["walk_review_status"] = np.select(
        [
            df["walk_snap_distance_m"] > HIGH_REVIEW_M,
            df["walk_snap_distance_m"] > REVIEW_M,
        ],
        [
            "HIGH_REVIEW_OVER_250M",
            "REVIEW_OVER_100M",
        ],
        default="WITHIN_100M",
    )

    # Coarse 0.01-degree bins are for screening only.
    # They are not official administrative boundaries.
    df["screening_lat_bin"] = (
        np.floor(df["latitude"] * 100) / 100
    ).round(2)

    df["screening_lon_bin"] = (
        np.floor(df["longitude"] * 100) / 100
    ).round(2)

    grouped = df.groupby(
        ["screening_lat_bin", "screening_lon_bin"],
        dropna=False,
    )

    area_rows = []

    for (lat_bin, lon_bin), group in grouped:
        area_rows.append({
            "screening_lat_bin": lat_bin,
            "screening_lon_bin": lon_bin,
            "cell_count": int(len(group)),
            "drive_median_snap_m": round(
                float(group["drive_snap_distance_m"].median()), 2
            ),
            "drive_over_100m_count": int(
                (group["drive_snap_distance_m"] > REVIEW_M).sum()
            ),
            "drive_over_100m_percent": round(
                float(
                    (group["drive_snap_distance_m"] > REVIEW_M).mean()
                    * 100
                ),
                2,
            ),
            "walk_median_snap_m": round(
                float(group["walk_snap_distance_m"].median()), 2
            ),
            "walk_over_100m_count": int(
                (group["walk_snap_distance_m"] > REVIEW_M).sum()
            ),
            "walk_over_100m_percent": round(
                float(
                    (group["walk_snap_distance_m"] > REVIEW_M).mean()
                    * 100
                ),
                2,
            ),
        })

    area_df = pd.DataFrame(area_rows)

    area_df.to_csv(OUTPUT_CSV, index=False)

    summary = {
        "project": "AURIS-X",
        "audit": "Population-to-road snap-distance audit",
        "input_rows": int(len(df)),
        "unique_population_cell_ids": int(
            df["population_cell_id"].nunique()
        ),
        "missing_driving_node_ids": int(
            df["drive_nearest_node_id"].isna().sum()
        ),
        "missing_walking_node_ids": int(
            df["walk_nearest_node_id"].isna().sum()
        ),
        "driving_distance_summary": summarize(
            df["drive_snap_distance_m"]
        ),
        "walking_distance_summary": summarize(
            df["walk_snap_distance_m"]
        ),
        "screening_grid": {
            "method": "0.01-degree latitude/longitude bins",
            "official_boundary": False,
            "warning": (
                "Bins are for screening only, not administrative areas."
            ),
        },
        "outputs": {
            "area_screening_csv": str(OUTPUT_CSV),
            "audit_json": str(OUTPUT_JSON),
        },
        "limitations": [
            "Straight-line snapping distance is not network travel distance.",
            "Nearest-node matching does not prove safe or legal access.",
            "Area bins are not official neighbourhood boundaries.",
            "Population raster values have not been confirmed as headcounts.",
        ],
    }

    OUTPUT_JSON.write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    print("\nPOPULATION-TO-ROAD AUDIT COMPLETE")
    print("=" * 45)
    print("Rows audited:", len(df))
    print("Unique population cells:", df["population_cell_id"].nunique())
    print("Screening area bins:", len(area_df))
    print(
        "Driving missing node IDs:",
        df["drive_nearest_node_id"].isna().sum(),
    )
    print(
        "Walking missing node IDs:",
        df["walk_nearest_node_id"].isna().sum(),
    )
    print("\nDriving distance summary:")
    print(json.dumps(summary["driving_distance_summary"], indent=2))
    print("\nWalking distance summary:")
    print(json.dumps(summary["walking_distance_summary"], indent=2))
    print("\nArea screening CSV:", OUTPUT_CSV)
    print("Audit report:", OUTPUT_JSON)


if __name__ == "__main__":
    main()
