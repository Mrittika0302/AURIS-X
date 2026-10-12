
"""
AURIS-X: Healthcare Underserved-Area Screening

Input:
  data/gold/healthcare_accessibility_by_population_cell.csv

Outputs:
  data/gold/healthcare_underserved_cells.csv
  data/gold/healthcare_underserved_summary_by_grid.csv
  reports/healthcare_underserved_summary.json

IMPORTANT:
- Distance thresholds are preliminary screening categories, not official standards.
- Population raster values have unverified units; do not assume they are headcounts.
- Coarse grid bins are not official neighbourhood boundaries.
"""

from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

INPUT_CSV = (
    ROOT / "data" / "gold"
    / "healthcare_accessibility_by_population_cell.csv"
)

OUTPUT_CELLS = (
    ROOT / "data" / "gold"
    / "healthcare_underserved_cells.csv"
)

OUTPUT_GRID = (
    ROOT / "data" / "gold"
    / "healthcare_underserved_summary_by_grid.csv"
)

OUTPUT_JSON = (
    ROOT / "reports"
    / "healthcare_underserved_summary.json"
)

# Configurable screening thresholds, in metres.
THRESHOLDS_M = [3000, 5000, 10000]

BANDS = [
    "Within 3 km",
    "Over 3 to 5 km",
    "Over 5 to 10 km",
    "Over 10 km",
    "Unreachable",
]

REQUIRED_COLUMNS = [
    "population_cell_id",
    "raster_row",
    "raster_col",
    "latitude",
    "longitude",
    "population_raster_value",
    "driving_distance_m",
    "driving_reachable",
    "walking_distance_m",
    "walking_reachable",
]


def parse_bool(series):
    """Convert common text and numeric representations to booleans."""
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)

    return (
        series.astype("string")
        .str.strip()
        .str.lower()
        .isin(["true", "1", "yes", "y"])
    )


def classify_distance(distance, reachable):
    """Assign a screening band without treating missing distance as zero."""
    if not reachable or pd.isna(distance):
        return "Unreachable"

    if not np.isfinite(distance) or distance < 0:
        return "Unreachable"

    if distance <= 3000:
        return "Within 3 km"

    if distance <= 5000:
        return "Over 3 to 5 km"

    if distance <= 10000:
        return "Over 5 to 10 km"

    return "Over 10 km"


def summarize_mode(df, mode):
    """Calculate cell counts and network-distance statistics."""
    distance_col = f"{mode}_distance_m"
    reachable_col = f"{mode}_reachable"
    band_col = f"{mode}_distance_band"

    valid = (
        df[reachable_col]
        & df[distance_col].notna()
        & np.isfinite(df[distance_col])
        & (df[distance_col] >= 0)
    )

    distances_km = df.loc[valid, distance_col] / 1000.0

    band_counts = (
        df[band_col]
        .value_counts()
        .reindex(BANDS, fill_value=0)
    )

    result = {
        "total_cells": int(len(df)),
        "reachable_cells": int(valid.sum()),
        "unreachable_cells": int((~valid).sum()),
        "reachable_cell_percentage": (
            round(float(valid.mean() * 100), 2)
            if len(df) else None
        ),
        "distance_band_cell_counts": {
            band: int(band_counts[band])
            for band in BANDS
        },
        "distance_statistics_km": {},
    }

    if not distances_km.empty:
        result["distance_statistics_km"] = {
            "minimum": round(float(distances_km.min()), 3),
            "median": round(float(distances_km.median()), 3),
            "mean": round(float(distances_km.mean()), 3),
            "p90": round(float(distances_km.quantile(0.90)), 3),
            "p95": round(float(distances_km.quantile(0.95)), 3),
            "maximum": round(float(distances_km.max()), 3),
        }

    return result


def main():
    if not INPUT_CSV.exists():
        print("ERROR: Accessibility CSV not found:")
        print(INPUT_CSV)
        return 1

    print("=" * 68)
    print("AURIS-X HEALTHCARE UNDERSERVED-AREA SCREENING")
    print("=" * 68)
    print(f"Input: {INPUT_CSV}")

    df = pd.read_csv(INPUT_CSV, low_memory=False)

    print(f"\nRows loaded: {len(df):,}")
    print("\nDetected columns:")
    print(list(df.columns))

    missing = [
        col for col in REQUIRED_COLUMNS
        if col not in df.columns
    ]

    if missing:
        print("\nERROR: Required columns are missing:")
        for col in missing:
            print(f"  - {col}")
        return 1

    if df.empty:
        print("ERROR: Input CSV contains no rows.")
        return 1

    duplicate_ids = int(
        df["population_cell_id"].duplicated().sum()
    )

    if duplicate_ids:
        print(
            f"\nWARNING: {duplicate_ids:,} duplicate population "
            "cell IDs were found."
        )

    # Convert numeric columns safely.
    numeric_columns = [
        "raster_row",
        "raster_col",
        "latitude",
        "longitude",
        "population_raster_value",
        "driving_distance_m",
        "walking_distance_m",
        "drive_snap_distance_m",
        "walk_snap_distance_m",
    ]

    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col], errors="coerce"
            )

    # Parse the reachability flags.
    df["driving_reachable"] = parse_bool(
        df["driving_reachable"]
    )

    df["walking_reachable"] = parse_bool(
        df["walking_reachable"]
    )

    # Clean distances and create distance bands.
    for mode in ("driving", "walking"):
        distance_col = f"{mode}_distance_m"
        reachable_col = f"{mode}_reachable"

        distance = df[distance_col]

        valid_distance = (
            distance.notna()
            & np.isfinite(distance)
            & (distance >= 0)
        )

        inconsistent = (
            df[reachable_col] & ~valid_distance
        )

        if inconsistent.any():
            print(
                f"WARNING: {int(inconsistent.sum()):,} "
                f"{mode} rows were marked reachable but "
                "had invalid distances. Marking them unreachable."
            )

        df[reachable_col] = (
            df[reachable_col] & valid_distance
        )

        # Unreachable rows retain blank distance values.
        df.loc[~df[reachable_col], distance_col] = np.nan

        df[f"{mode}_distance_km"] = (
            df[distance_col] / 1000.0
        )

        df[f"{mode}_distance_band"] = [
            classify_distance(d, r)
            for d, r in zip(
                df[distance_col],
                df[reachable_col]
            )
        ]

        # Threshold flags are True only for reachable cells.
        for threshold in THRESHOLDS_M:
            threshold_km = threshold // 1000
            column = f"{mode}_over_{threshold_km}km"

            df[column] = (
                df[reachable_col]
                & (df[distance_col] > threshold)
            )

    # Preserve snap-review flags, parsing them consistently.
    review_columns = [
        "drive_review_over_100m",
        "drive_review_over_250m",
        "walk_review_over_100m",
        "walk_review_over_250m",
    ]

    for col in review_columns:
        if col in df.columns:
            df[col] = parse_bool(df[col])

    # Rank by distance: larger rank values identify longer distances.
    # Unreachable cells remain separately identifiable.
    for mode in ("driving", "walking"):
        df[f"{mode}_priority_rank"] = (
            df[f"{mode}_distance_m"]
            .rank(
                method="min",
                ascending=False,
                na_option="bottom",
            )
            .astype("Int64")
        )

    df["either_mode_unreachable"] = ~(
        df["driving_reachable"]
        | df["walking_reachable"]
    )

    df["both_modes_over_5km"] = (
        df["driving_reachable"]
        & df["walking_reachable"]
        & (df["driving_distance_m"] > 5000)
        & (df["walking_distance_m"] > 5000)
    )

    # Group cells into reproducible 10-row by 10-column bins.
    # These bins are not official neighbourhoods.
    df["grid_bin_row"] = (
        (df["raster_row"] // 10) * 10
    )

    df["grid_bin_col"] = (
        (df["raster_col"] // 10) * 10
    )

    df["coarse_grid_id"] = (
        "r"
        + df["grid_bin_row"].astype("Int64").astype(str)
        + "_c"
        + df["grid_bin_col"].astype("Int64").astype(str)
    )

    # Summarize every coarse grid bin.
    grid_rows = []

    for grid_id, group in df.groupby(
        "coarse_grid_id", dropna=False
    ):
        record = {
            "coarse_grid_id": str(grid_id),
            "cell_count": int(len(group)),
            "mean_latitude": (
                round(float(group["latitude"].mean()), 6)
                if group["latitude"].notna().any()
                else None
            ),
            "mean_longitude": (
                round(float(group["longitude"].mean()), 6)
                if group["longitude"].notna().any()
                else None
            ),
            "population_raster_value_sum_unverified_units": (
                round(
                    float(
                        group["population_raster_value"].sum()
                    ),
                    4,
                )
                if group["population_raster_value"].notna().any()
                else None
            ),
        }

        for mode in ("driving", "walking"):
            reachable_col = f"{mode}_reachable"
            distance_col = f"{mode}_distance_m"
            band_col = f"{mode}_distance_band"

            valid_distances = group.loc[
                group[reachable_col], distance_col
            ].dropna()

            record[f"{mode}_reachable_cells"] = int(
                group[reachable_col].sum()
            )

            record[f"{mode}_unreachable_cells"] = int(
                (~group[reachable_col]).sum()
            )

            record[f"{mode}_mean_distance_km"] = (
                round(
                    float(valid_distances.mean() / 1000),
                    3,
                )
                if len(valid_distances) else None
            )

            record[f"{mode}_p90_distance_km"] = (
                round(
                    float(
                        valid_distances.quantile(0.90) / 1000
                    ),
                    3,
                )
                if len(valid_distances) else None
            )

            for band_name in BANDS:
                key = (
                    band_name.lower()
                    .replace(" ", "_")
                    .replace("-", "_")
                )

                record[f"{mode}_{key}_cells"] = int(
                    (group[band_col] == band_name).sum()
                )

        grid_rows.append(record)

    grid_summary = pd.DataFrame(grid_rows)

    # Put bins with many very-long-distance cells near the top.
    grid_summary = grid_summary.sort_values(
        by=[
            "driving_over_10_km_cells",
            "walking_over_10_km_cells",
            "cell_count",
        ],
        ascending=[False, False, False],
        kind="stable",
    )

    # Write the outputs.
    OUTPUT_CELLS.parent.mkdir(
        parents=True, exist_ok=True
    )
    OUTPUT_JSON.parent.mkdir(
        parents=True, exist_ok=True
    )

    df.to_csv(
        OUTPUT_CELLS,
        index=False,
        na_rep="",
    )

    grid_summary.to_csv(
        OUTPUT_GRID,
        index=False,
        na_rep="",
    )

    summary = {
        "title": (
            "AURIS-X preliminary healthcare "
            "underserved-area screening"
        ),
        "input_file": str(INPUT_CSV),
        "output_cells_csv": str(OUTPUT_CELLS),
        "output_coarse_grid_csv": str(OUTPUT_GRID),
        "thresholds_m": THRESHOLDS_M,
        "thresholds_are_screening_categories_not_official_standards": True,
        "population_raster_units_verified": False,
        "coarse_grid_bins_are_official_neighbourhoods": False,
        "total_population_cells": int(len(df)),
        "unique_population_cell_ids": int(
            df["population_cell_id"].nunique(dropna=True)
        ),
        "driving": summarize_mode(df, "driving"),
        "walking": summarize_mode(df, "walking"),
        "cells_unreachable_in_both_modes": int(
            df["either_mode_unreachable"].sum()
        ),
        "cells_over_5km_in_both_modes": int(
            df["both_modes_over_5km"].sum()
        ),
        "snap_review_counts": {},
        "interpretation_notes": [
            "Distances are network distances to matched healthcare facility source nodes, not travel times.",
            "Reachability depends on graph connectivity, edge direction, snapping, and source records.",
            "OSM facility presence does not confirm operational status or service availability.",
            "Population raster values have unverified units and must not be called headcounts until verified.",
            "Coarse grid bins use raster row and column indices; they are not official neighbourhood boundaries.",
            "Snap review flags identify records for inspection, not proven access errors.",
        ],
    }

    for col in review_columns:
        if col in df.columns:
            summary["snap_review_counts"][col] = int(
                df[col].sum()
            )

    with OUTPUT_JSON.open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(
            summary,
            file,
            indent=2,
            ensure_ascii=False,
        )

    # Final console report.
    print("\n" + "=" * 68)
    print("AURIS-X UNDERSERVED-AREA SCREENING COMPLETE")
    print("=" * 68)
    print(f"Population cells: {len(df):,}")
    print(f"Coarse grid bins: {len(grid_summary):,}")
    print(
        "Unreachable in both modes: "
        f"{summary['cells_unreachable_in_both_modes']:,}"
    )
    print(
        "Over 5 km in both modes: "
        f"{summary['cells_over_5km_in_both_modes']:,}"
    )

    for mode in ("driving", "walking"):
        stats = summary[mode]

        print(f"\n{mode.title()}:")
        print(
            f"  Reachable: {stats['reachable_cells']:,} "
            f"({stats['reachable_cell_percentage']}%)"
        )
        print(
            f"  Unreachable: {stats['unreachable_cells']:,}"
        )

        for band_name in BANDS:
            count = stats["distance_band_cell_counts"].get(
                band_name, 0
            )
            print(f"  {band_name}: {count:,} cells")

        distance_stats = stats["distance_statistics_km"]

        if distance_stats:
            print(
                "  Median distance: "
                f"{distance_stats['median']:.3f} km"
            )
            print(
                "  P90 distance: "
                f"{distance_stats['p90']:.3f} km"
            )

    print("\nCreated outputs:")
    print(f"  {OUTPUT_CELLS}")
    print(f"  {OUTPUT_GRID}")
    print(f"  {OUTPUT_JSON}")
    print(
        "\nReminder: screening thresholds are not official "
        "healthcare standards."
    )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        raise
