
from pathlib import Path
from datetime import datetime, timezone
import glob
import json
import os

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "data" / "gold"
REPORTS = ROOT / "reports"

ZONE_SIZE = 10
TOP_N = 20

WEIGHTS = {
    "raster_value": 0.25,
    "flagged_cells": 0.25,
    "both_modes": 0.25,
    "distance": 0.25,
}


def latest_input():
    files = glob.glob(
        str(GOLD / "education_accessibility_flags_*.csv")
    )
    if not files:
        raise FileNotFoundError(
            "No education_accessibility_flags_*.csv found in data/gold."
        )
    return Path(max(files, key=os.path.getmtime))


def parse_bool(series):
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)

    return series.astype(str).str.strip().str.lower().isin(
        {"true", "1", "yes", "y", "t"}
    )


def minmax(series):
    """Scale valid values to 0-100, preserving missing values."""
    values = pd.to_numeric(series, errors="coerce")
    result = pd.Series(np.nan, index=series.index, dtype=float)
    valid = values.notna()

    if not valid.any():
        return result

    low = values[valid].min()
    high = values[valid].max()

    if np.isclose(low, high):
        result.loc[valid] = 0.0
    else:
        result.loc[valid] = (
            (values[valid] - low) / (high - low)
        ) * 100.0

    return result


def main():
    GOLD.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    source = latest_input()
    df = pd.read_csv(source)

    required = [
        "raster_row",
        "raster_col",
        "population_raster_value",
        "driving_distance_m",
        "walking_distance_m",
        "driving_unreachable",
        "walking_unreachable",
        "driving_screen_flag",
        "walking_screen_flag",
        "screen_flag_both_modes",
        "screen_flag_either_mode",
    ]

    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(
            "Missing required columns: " + ", ".join(missing)
        )

    numeric_columns = [
        "raster_row",
        "raster_col",
        "population_raster_value",
        "driving_distance_m",
        "walking_distance_m",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    if df[["raster_row", "raster_col"]].isna().any().any():
        raise ValueError("Raster row or column contains invalid values.")

    boolean_columns = [
        "driving_unreachable",
        "walking_unreachable",
        "driving_screen_flag",
        "walking_screen_flag",
        "screen_flag_both_modes",
        "screen_flag_either_mode",
    ]

    for column in boolean_columns:
        df[column] = parse_bool(df[column])

    # Create analytical zones from 10x10 raster-cell blocks.
    df["zone_row"] = df["raster_row"].astype(int) // ZONE_SIZE
    df["zone_col"] = df["raster_col"].astype(int) // ZONE_SIZE

    df["zone_id"] = (
        "ER"
        + df["zone_row"].astype(str)
        + "_EC"
        + df["zone_col"].astype(str)
    )

    # Raster values are relative weights, not verified headcounts.
    raster = df["population_raster_value"].fillna(0).clip(lower=0)

    df["_flagged_raster"] = np.where(
        df["screen_flag_either_mode"], raster, 0.0
    )

    df["_both_raster"] = np.where(
        df["screen_flag_both_modes"], raster, 0.0
    )

    # Calculate maximum available network distance per cell.
    # Distances are metres of network length, not travel times.
    drive = df["driving_distance_m"]
    walk = df["walking_distance_m"]

    drive_ok = drive.notna() & np.isfinite(drive) & (drive >= 0)
    walk_ok = walk.notna() & np.isfinite(walk) & (walk >= 0)

    df["_max_distance"] = np.nan

    both_valid = drive_ok & walk_ok
    df.loc[both_valid, "_max_distance"] = np.maximum(
        drive.loc[both_valid],
        walk.loc[both_valid],
    )

    drive_only = drive_ok & ~walk_ok
    df.loc[drive_only, "_max_distance"] = drive.loc[drive_only]

    walk_only = walk_ok & ~drive_ok
    df.loc[walk_only, "_max_distance"] = walk.loc[walk_only]

    df["_flagged_distance"] = df["_max_distance"].where(
        df["screen_flag_either_mode"]
    )

    # Aggregate cell-level information into zones.
    grouped = df.groupby(
        ["zone_id", "zone_row", "zone_col"],
        sort=False,
    )

    zones = grouped.agg(
        total_cells=("zone_id", "size"),
        flagged_either_mode_cells=("screen_flag_either_mode", "sum"),
        flagged_both_modes_cells=("screen_flag_both_modes", "sum"),
        driving_flagged_cells=("driving_screen_flag", "sum"),
        walking_flagged_cells=("walking_screen_flag", "sum"),
        driving_unreachable_cells=("driving_unreachable", "sum"),
        walking_unreachable_cells=("walking_unreachable", "sum"),
        flagged_positive_raster_value_sum=("_flagged_raster", "sum"),
        both_modes_positive_raster_value_sum=("_both_raster", "sum"),
        mean_flagged_max_reachable_distance_m=("_flagged_distance", "mean"),
        max_flagged_reachable_distance_m=("_flagged_distance", "max"),
    ).reset_index()

    # Count cells unreachable in both driving and walking modes.
    df["_unreachable_both"] = (
        df["driving_unreachable"] & df["walking_unreachable"]
    )

    both_unreachable = df.groupby("zone_id")["_unreachable_both"].sum()

    zones["unreachable_both_modes_cells"] = (
        zones["zone_id"]
        .map(both_unreachable)
        .fillna(0)
        .astype(int)
    )

    count_columns = [
        "total_cells",
        "flagged_either_mode_cells",
        "flagged_both_modes_cells",
        "driving_flagged_cells",
        "walking_flagged_cells",
        "driving_unreachable_cells",
        "walking_unreachable_cells",
        "unreachable_both_modes_cells",
    ]

    for column in count_columns:
        zones[column] = zones[column].fillna(0).astype(int)

    # Normalize each component to a 0-100 scale.
    zones["score_raster_value"] = minmax(
        zones["flagged_positive_raster_value_sum"]
    )

    zones["score_flagged_cells"] = minmax(
        zones["flagged_either_mode_cells"]
    )

    zones["score_both_modes"] = minmax(
        zones["flagged_both_modes_cells"]
    )

    zones["score_distance"] = minmax(
        zones["mean_flagged_max_reachable_distance_m"]
    )

    # FIX: A zone with no usable reachable-distance statistic receives
    # zero for this component. This does not mean its actual distance
    # is zero; unreachable counts remain separately reported.
    zones["score_distance"] = zones["score_distance"].fillna(0.0)

    zones["priority_score"] = (
        zones["score_raster_value"] * WEIGHTS["raster_value"]
        + zones["score_flagged_cells"] * WEIGHTS["flagged_cells"]
        + zones["score_both_modes"] * WEIGHTS["both_modes"]
        + zones["score_distance"] * WEIGHTS["distance"]
    )

    # Validate scores before writing any ranking files.
    if zones["zone_id"].duplicated().any():
        raise ValueError("Duplicate zone IDs detected.")

    if zones["priority_score"].isna().any():
        raise ValueError("Priority scores still contain missing values.")

    if not np.isfinite(zones["priority_score"]).all():
        raise ValueError("Non-finite priority scores detected.")

    if not zones["priority_score"].between(0, 100).all():
        raise ValueError("Priority scores are outside the 0-100 range.")

    # Highest score first; use counts as deterministic tie-breakers.
    zones = zones.sort_values(
        [
            "priority_score",
            "flagged_both_modes_cells",
            "flagged_either_mode_cells",
        ],
        ascending=[False, False, False],
        kind="mergesort",
    ).reset_index(drop=True)

    zones.insert(0, "rank", range(1, len(zones) + 1))

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    full_path = GOLD / f"education_priority_zones_{timestamp}.csv"
    top_path = GOLD / f"education_priority_top20_{timestamp}.csv"
    summary_path = REPORTS / f"education_priority_summary_{timestamp}.json"

    zones.to_csv(full_path, index=False)
    zones.head(TOP_N).to_csv(top_path, index=False)

    top10_columns = [
        "rank",
        "zone_id",
        "priority_score",
        "flagged_either_mode_cells",
        "flagged_both_modes_cells",
        "flagged_positive_raster_value_sum",
        "mean_flagged_max_reachable_distance_m",
        "unreachable_both_modes_cells",
    ]

    top10_records = (
        zones.head(10)[top10_columns]
        .astype(object)
        .where(pd.notna(zones.head(10)[top10_columns]), None)
        .to_dict(orient="records")
    )

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_file": str(source.relative_to(ROOT)),
        "full_ranking_file": str(full_path.relative_to(ROOT)),
        "top20_file": str(top_path.relative_to(ROOT)),
        "population_cells": int(len(df)),
        "zone_count": int(len(zones)),
        "zone_size_raster_cells": ZONE_SIZE,
        "missing_priority_scores": int(
            zones["priority_score"].isna().sum()
        ),
        "priority_score_min": float(zones["priority_score"].min()),
        "priority_score_max": float(zones["priority_score"].max()),
        "priority_score_mean": float(zones["priority_score"].mean()),
        "score_weights": WEIGHTS,
        "missing_distance_score_policy": (
            "Missing distance component is assigned zero in the composite "
            "score. No distance is imputed; unreachable counts are reported "
            "separately."
        ),
        "top_10_zones": top10_records,
        "limitations": [
            "Zones are analytical raster blocks, not official neighbourhoods or parcels.",
            "Population raster units are unverified; values are not verified headcounts.",
            "The 5 km threshold is preliminary, not an official standard.",
            "Network distances are path lengths in metres, not travel times.",
            "OSM facility data and network matching are not independently ground-validated.",
            "Some education features may represent campus sub-features.",
            "Scores are exploratory screening indicators, not validated site-selection recommendations.",
        ],
    }

    with summary_path.open("w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2, ensure_ascii=False)

    print("=" * 64)
    print("EDUCATION PRIORITY ZONE RANKING")
    print("=" * 64)
    print(f"Input file: {source}")
    print(f"Population cells: {len(df):,}")
    print(f"Grid zones: {len(zones):,}")
    print(f"Zone size: {ZONE_SIZE} x {ZONE_SIZE} raster cells")
    print(f"Missing priority scores: {zones['priority_score'].isna().sum()}")
    print(
        f"Priority score range: "
        f"{zones['priority_score'].min():.2f} to "
        f"{zones['priority_score'].max():.2f}"
    )

    print("\nTop 10 zones:")
    print(
        zones.head(10)[
            [
                "rank",
                "zone_id",
                "priority_score",
                "flagged_either_mode_cells",
                "flagged_both_modes_cells",
                "flagged_positive_raster_value_sum",
            ]
        ].to_string(index=False, float_format=lambda x: f"{x:.6f}")
    )

    print(f"\nFull ranking: {full_path}")
    print(f"Top 20 CSV: {top_path}")
    print(f"Summary JSON: {summary_path}")
    print("\nNo healthcare files or source data were modified.")


if __name__ == "__main__":
    main()
