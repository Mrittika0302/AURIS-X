
from pathlib import Path
import argparse
import json
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

INPUT_CSV = ROOT / "data" / "gold" / "healthcare_underserved_cells.csv"
OUTPUT_CSV = ROOT / "data" / "gold" / "healthcare_candidate_sites.csv"
OUTPUT_JSON = ROOT / "reports" / "healthcare_candidate_sites_summary.json"

# These are raster-cell groupings for candidate-zone screening,
# not official neighbourhood boundaries or land parcels.
GRID_SIZE = 10
MAX_CANDIDATES = 100


def first_existing_column(df, names, required=True):
    for name in names:
        if name in df.columns:
            return name
    if required:
        raise ValueError(
            "Could not find any expected column. Tried: "
            + ", ".join(names)
            + "\nAvailable columns: "
            + ", ".join(df.columns)
        )
    return None


def as_numeric(df, column):
    if column is None:
        return pd.Series(np.nan, index=df.index, dtype=float)
    return pd.to_numeric(df[column], errors="coerce")


def minmax_0_100(series):
    values = pd.to_numeric(series, errors="coerce")
    valid = values.dropna()

    if valid.empty:
        return pd.Series(0.0, index=series.index)

    low = valid.min()
    high = valid.max()

    if math.isclose(float(low), float(high)):
        result = pd.Series(50.0, index=series.index)
        result[values.isna()] = 0.0
        return result

    result = ((values - low) / (high - low)) * 100.0
    return result.fillna(0.0).clip(0, 100)


def main():
    parser = argparse.ArgumentParser(
        description="Screen and rank preliminary AURIS-X healthcare candidate zones."
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=None,
        help="Maximum budget per planning period, in the same currency units as site cost.",
    )
    parser.add_argument(
        "--estimated-cost-per-site",
        type=float,
        default=None,
        help=(
            "Optional assumed cost per candidate. This is a uniform scenario "
            "assumption, not a location-specific cost estimate."
        ),
    )
    parser.add_argument(
        "--grid-size",
        type=int,
        default=GRID_SIZE,
        help="Raster cells per side of a candidate zone (default: 10).",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=MAX_CANDIDATES,
        help="Maximum number of ranked candidate zones to export.",
    )
    args = parser.parse_args()

    if args.grid_size < 1:
        raise ValueError("--grid-size must be at least 1.")
    if args.max_candidates < 1:
        raise ValueError("--max-candidates must be at least 1.")
    if args.budget is not None and args.budget < 0:
        raise ValueError("--budget cannot be negative.")
    if args.estimated_cost_per_site is not None and args.estimated_cost_per_site < 0:
        raise ValueError("--estimated-cost-per-site cannot be negative.")

    if not INPUT_CSV.exists():
        raise FileNotFoundError(f"Missing input CSV: {INPUT_CSV}")

    print("Loading underserved healthcare cells...")
    df = pd.read_csv(INPUT_CSV, low_memory=False)

    if df.empty:
        raise ValueError("The underserved-cells CSV contains no rows.")

    row_col = first_existing_column(df, ["raster_row"])
    col_col = first_existing_column(df, ["raster_col"])
    lat_col = first_existing_column(df, ["latitude", "lat"])
    lon_col = first_existing_column(df, ["longitude", "lon", "lng"])

    drive_dist_col = first_existing_column(
        df, ["driving_distance_m", "driving_distance", "drive_distance_m"],
        required=False
    )
    walk_dist_col = first_existing_column(
        df, ["walking_distance_m", "walking_distance", "walk_distance_m"],
        required=False
    )
    drive_reach_col = first_existing_column(
        df, ["driving_reachable", "drive_reachable"], required=False
    )
    walk_reach_col = first_existing_column(
        df, ["walking_reachable", "walk_reachable"], required=False
    )
    both_gap_col = first_existing_column(
        df,
        [
            "over_5km_both_modes",
            "over_5km_in_both_modes",
            "both_modes_over_5km",
        ],
        required=False,
    )
    both_unreachable_col = first_existing_column(
        df,
        [
            "unreachable_both_modes",
            "unreachable_in_both_modes",
            "both_modes_unreachable",
        ],
        required=False,
    )
    raster_value_col = first_existing_column(
        df,
        ["population_raster_value", "population_value", "raster_value"],
        required=False,
    )
    drive_snap_col = first_existing_column(
        df, ["drive_snap_distance_m"], required=False
    )
    walk_snap_col = first_existing_column(
        df, ["walk_snap_distance_m"], required=False
    )

    # Validate coordinates and raster indices.
    df["_row"] = pd.to_numeric(df[row_col], errors="coerce")
    df["_col"] = pd.to_numeric(df[col_col], errors="coerce")
    df["_lat"] = pd.to_numeric(df[lat_col], errors="coerce")
    df["_lon"] = pd.to_numeric(df[lon_col], errors="coerce")

    valid = (
        df["_row"].notna()
        & df["_col"].notna()
        & df["_lat"].between(-90, 90)
        & df["_lon"].between(-180, 180)
    )
    invalid_rows = int((~valid).sum())
    df = df.loc[valid].copy()

    if df.empty:
        raise ValueError("No rows have valid raster indices and coordinates.")

    df["_drive_m"] = as_numeric(df, drive_dist_col)
    df["_walk_m"] = as_numeric(df, walk_dist_col)

    # Unreachable values remain missing in distance statistics.
    if drive_reach_col:
        drive_reachable = df[drive_reach_col].astype(str).str.lower().isin(
            ["true", "1", "yes"]
        )
        df["_drive_reachable"] = drive_reachable
    else:
        df["_drive_reachable"] = df["_drive_m"].notna()

    if walk_reach_col:
        walk_reachable = df[walk_reach_col].astype(str).str.lower().isin(
            ["true", "1", "yes"]
        )
        df["_walk_reachable"] = walk_reachable
    else:
        df["_walk_reachable"] = df["_walk_m"].notna()

    df["_drive_gap5"] = df["_drive_m"].gt(5000)
    df["_walk_gap5"] = df["_walk_m"].gt(5000)

    if both_gap_col:
        df["_both_gap5"] = df[both_gap_col].astype(str).str.lower().isin(
            ["true", "1", "yes"]
        )
    else:
        df["_both_gap5"] = df["_drive_gap5"] & df["_walk_gap5"]

    if both_unreachable_col:
        df["_both_unreachable"] = (
            df[both_unreachable_col].astype(str).str.lower().isin(
                ["true", "1", "yes"]
            )
        )
    else:
        df["_both_unreachable"] = (
            ~df["_drive_reachable"] & ~df["_walk_reachable"]
        )

    if raster_value_col:
        df["_raster_proxy"] = as_numeric(df, raster_value_col)
    else:
        df["_raster_proxy"] = np.nan

    df["_drive_snap_m"] = as_numeric(df, drive_snap_col)
    df["_walk_snap_m"] = as_numeric(df, walk_snap_col)

    # Group cells into candidate zones by raster row/column indices.
    df["_zone_row"] = (df["_row"].astype(int) // args.grid_size)
    df["_zone_col"] = (df["_col"].astype(int) // args.grid_size)
    df["_zone_id"] = (
        "Z_R" + df["_zone_row"].astype(str)
        + "_C" + df["_zone_col"].astype(str)
    )

    print("Aggregating candidate zones...")
    grouped = df.groupby("_zone_id", sort=False)

    candidates = grouped.agg(
        zone_row=("_zone_row", "first"),
        zone_col=("_zone_col", "first"),
        cells_in_zone=("_lat", "size"),
        centroid_latitude=("_lat", "mean"),
        centroid_longitude=("_lon", "mean"),
        cells_over_5km_both_modes=("_both_gap5", "sum"),
        cells_unreachable_both_modes=("_both_unreachable", "sum"),
        driving_unreachable_cells=("_drive_reachable", lambda s: (~s).sum()),
        walking_unreachable_cells=("_walk_reachable", lambda s: (~s).sum()),
        mean_driving_distance_m=("_drive_m", "mean"),
        mean_walking_distance_m=("_walk_m", "mean"),
        mean_raster_value_proxy=("_raster_proxy", "mean"),
        median_driving_snap_m=("_drive_snap_m", "median"),
        median_walking_snap_m=("_walk_snap_m", "median"),
    ).reset_index(names="candidate_zone_id")

    candidates["both_modes_gap_fraction"] = (
        candidates["cells_over_5km_both_modes"]
        / candidates["cells_in_zone"].clip(lower=1)
    )
    candidates["both_modes_unreachable_fraction"] = (
        candidates["cells_unreachable_both_modes"]
        / candidates["cells_in_zone"].clip(lower=1)
    )

    # Build transparent component scores. These are relative ranks among
    # the zones in this run, not calibrated estimates of public benefit.
    candidates["gap_score"] = minmax_0_100(
        candidates["both_modes_gap_fraction"]
    )
    candidates["unreachable_score"] = minmax_0_100(
        candidates["both_modes_unreachable_fraction"]
    )
    candidates["distance_score"] = minmax_0_100(
        candidates[
            ["mean_driving_distance_m", "mean_walking_distance_m"]
        ].mean(axis=1)
    )

    # Raster values have unverified units. Use only as a relative proxy.
    candidates["demand_proxy_score"] = minmax_0_100(
        candidates["mean_raster_value_proxy"]
    )

    # Missing snap distances stay missing. Unknown confidence is not treated
    # as perfect matching or as a confirmed error.
    snap_median = candidates[
        ["median_driving_snap_m", "median_walking_snap_m"]
    ].mean(axis=1, skipna=True)
    candidates["snap_review_score"] = (100 - snap_median / 10).clip(0, 100)
    candidates.loc[snap_median.isna(), "snap_review_score"] = np.nan

    # Score uses only currently available components. Weights are explicit.
    weights = {
        "gap_score": 0.40,
        "unreachable_score": 0.20,
        "distance_score": 0.25,
        "demand_proxy_score": 0.10,
        "snap_review_score": 0.05,
    }

    weighted_sum = pd.Series(0.0, index=candidates.index)
    available_weight = pd.Series(0.0, index=candidates.index)

    for column, weight in weights.items():
        values = candidates[column]
        available = values.notna()
        weighted_sum.loc[available] += values.loc[available] * weight
        available_weight.loc[available] += weight

    candidates["screening_score"] = (
        weighted_sum / available_weight.replace(0, np.nan) * 1.0
    ).fillna(0).round(2)

    candidates["score_type"] = (
        "Relative screening score; not incremental benefit or a validated probability"
    )
    candidates["buildable_land_verified"] = False
    candidates["population_units_verified"] = False

    if args.estimated_cost_per_site is not None:
        candidates["assumed_site_cost"] = args.estimated_cost_per_site
        if args.budget is not None:
            candidates["within_budget"] = (
                candidates["assumed_site_cost"] <= args.budget
            )
            candidates = candidates[candidates["within_budget"]].copy()
        else:
            candidates["within_budget"] = pd.NA
    else:
        candidates["assumed_site_cost"] = np.nan
        candidates["within_budget"] = pd.NA

    candidates = candidates.sort_values(
        [
            "screening_score",
            "cells_over_5km_both_modes",
            "cells_unreachable_both_modes",
        ],
        ascending=[False, False, False],
    ).head(args.max_candidates).reset_index(drop=True)

    candidates.insert(0, "rank", np.arange(1, len(candidates) + 1))

    candidates["review_flags"] = candidates.apply(
        lambda r: "; ".join(
            [
                flag for flag, condition in [
                    (
                        "Raster units unverified",
                        True,
                    ),
                    (
                        "Candidate zone is not a land parcel",
                        True,
                    ),
                    (
                        "Network snap review recommended",
                        pd.isna(r["median_driving_snap_m"])
                        or pd.isna(r["median_walking_snap_m"])
                        or r["median_driving_snap_m"] > 100
                        or r["median_walking_snap_m"] > 100,
                    ),
                    (
                        "Unreachable cells require connectivity review",
                        r["cells_unreachable_both_modes"] > 0,
                    ),
                    (
                        "No site-specific cost data",
                        args.estimated_cost_per_site is None,
                    ),
                    (
                        "No before/after network simulation yet",
                        True,
                    ),
                ]
                if condition
            ]
        ),
        axis=1,
    )

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)

    candidates.to_csv(OUTPUT_CSV, index=False)

    summary = {
        "title": "AURIS-X preliminary healthcare candidate-zone screening",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_file": str(INPUT_CSV),
        "output_csv": str(OUTPUT_CSV),
        "candidate_zone_grid_size_cells": args.grid_size,
        "candidate_zones_exported": int(len(candidates)),
        "valid_input_cells": int(len(df)),
        "invalid_input_rows_skipped": invalid_rows,
        "budget": args.budget,
        "estimated_cost_per_site_assumption": args.estimated_cost_per_site,
        "budget_is_hard_constraint": args.budget is not None
        and args.estimated_cost_per_site is not None,
        "score_weights": weights,
        "score_interpretation": (
            "Relative screening score among candidate zones. "
            "It does not estimate incremental public benefit."
        ),
        "population_raster_units_verified": False,
        "candidate_zones_are_buildable_land_parcels": False,
        "network_before_after_simulation_completed": False,
        "education_data_used": False,
        "limitations": [
            "Distance thresholds are preliminary screening categories, not official standards.",
            "Raster values have unverified units and are not headcounts.",
            "Candidate zones are row/column grid groupings, not official neighbourhoods or land parcels.",
            "OSM facility presence does not confirm operational status or service availability.",
            "Network snap distances require review and are not proof of access errors.",
            "No road-network before/after simulation was performed.",
            "If a uniform site cost is supplied, it is an assumption and does not differentiate site-specific costs.",
            "This ranking is not a validated public-benefit score.",
        ],
    }

    OUTPUT_JSON.write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    print("\nCandidate screening completed.")
    print(f"Input cells used: {len(df):,}")
    print(f"Candidate zones exported: {len(candidates):,}")
    print(f"CSV: {OUTPUT_CSV}")
    print(f"Summary: {OUTPUT_JSON}")

    if args.budget is not None and args.estimated_cost_per_site is None:
        print(
            "\nWARNING: Budget was supplied without a site cost assumption. "
            "No budget filtering was applied."
        )

    print(
        "\nReminder: these are preliminary candidate zones. "
        "Do not treat the ranking as proof of incremental benefit or land suitability."
    )


if __name__ == "__main__":
    main()
