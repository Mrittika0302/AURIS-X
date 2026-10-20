
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
GOLD = ROOT / "data" / "gold"
REPORTS = ROOT / "reports"

THRESHOLD_M = 5000.0


def latest_file(folder, pattern):
    files = sorted(
        folder.glob(pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise FileNotFoundError(f"No file found: {folder / pattern}")
    return files[0]


def main():
    source = latest_file(
        GOLD, "education_accessibility_by_population_cell_*.csv"
    )

    df = pd.read_csv(source)

    required = {
        "population_cell_id",
        "raster_row",
        "raster_col",
        "latitude",
        "longitude",
        "population_raster_value",
        "driving_distance_m",
        "walking_distance_m",
        "driving_reachable",
        "walking_reachable",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    drive_dist = pd.to_numeric(df["driving_distance_m"], errors="coerce")
    walk_dist = pd.to_numeric(df["walking_distance_m"], errors="coerce")

    drive_reachable = drive_dist.notna()
    walk_reachable = walk_dist.notna()

    df["driving_unreachable"] = ~drive_reachable
    df["walking_unreachable"] = ~walk_reachable

    df["driving_over_5km"] = drive_reachable & (drive_dist > THRESHOLD_M)
    df["walking_over_5km"] = walk_reachable & (walk_dist > THRESHOLD_M)

    df["driving_screen_flag"] = (
        df["driving_unreachable"] | df["driving_over_5km"]
    )
    df["walking_screen_flag"] = (
        df["walking_unreachable"] | df["walking_over_5km"]
    )

    df["unreachable_both_modes"] = (
        df["driving_unreachable"] & df["walking_unreachable"]
    )

    df["over_5km_both_modes"] = (
        df["driving_over_5km"] & df["walking_over_5km"]
    )

    df["screen_flag_both_modes"] = (
        df["driving_screen_flag"] & df["walking_screen_flag"]
    )

    df["screen_flag_either_mode"] = (
        df["driving_screen_flag"] | df["walking_screen_flag"]
    )

    # Keep all population cells in the full results; create a separate
    # review list for cells flagged in either travel mode.
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    full_output = GOLD / f"education_accessibility_flags_{timestamp}.csv"
    flagged_output = GOLD / f"education_underserved_cells_{timestamp}.csv"
    summary_output = REPORTS / f"education_underserved_summary_{timestamp}.json"

    df.to_csv(full_output, index=False, encoding="utf-8-sig")

    flagged = df[df["screen_flag_either_mode"]].copy()
    flagged.to_csv(flagged_output, index=False, encoding="utf-8-sig")

    def count(mask):
        return int(mask.sum())

    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_file": str(source.relative_to(ROOT)),
        "full_flags_file": str(full_output.relative_to(ROOT)),
        "flagged_cells_file": str(flagged_output.relative_to(ROOT)),
        "population_cells": int(len(df)),
        "threshold_m": THRESHOLD_M,
        "driving_unreachable": count(df["driving_unreachable"]),
        "walking_unreachable": count(df["walking_unreachable"]),
        "unreachable_both_modes": count(df["unreachable_both_modes"]),
        "driving_over_5km_reachable": count(df["driving_over_5km"]),
        "walking_over_5km_reachable": count(df["walking_over_5km"]),
        "over_5km_both_modes": count(df["over_5km_both_modes"]),
        "screen_flag_both_modes": count(df["screen_flag_both_modes"]),
        "screen_flag_either_mode": count(df["screen_flag_either_mode"]),
        "interpretation": [
            "Flags are preliminary screening results, not proof of inadequate access.",
            "Unreachable means no directed network path was found in the model.",
            "Distance is network length in metres, not travel time.",
            "Population raster values have not been verified as headcounts.",
            "The 5 km threshold is an analytical assumption, not an official standard.",
            "Endpoint snapping offsets are not added to the network distance.",
        ],
    }

    with summary_output.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("=" * 64)
    print("EDUCATION UNDERSERVED-CELL SCREENING")
    print("=" * 64)
    print(f"Population cells: {len(df):,}")
    print(f"Driving unreachable: {summary['driving_unreachable']:,}")
    print(f"Walking unreachable: {summary['walking_unreachable']:,}")
    print(f"Unreachable in both modes: {summary['unreachable_both_modes']:,}")
    print(f"Driving over 5 km: {summary['driving_over_5km_reachable']:,}")
    print(f"Walking over 5 km: {summary['walking_over_5km_reachable']:,}")
    print(f"Over 5 km in both modes: {summary['over_5km_both_modes']:,}")
    print(f"Flagged in both modes: {summary['screen_flag_both_modes']:,}")
    print(f"Flagged in either mode: {summary['screen_flag_either_mode']:,}")
    print(f"\nFull flags: {full_output}")
    print(f"Flagged cells: {flagged_output}")
    print(f"Summary report: {summary_output}")
    print("\nNo healthcare files or source data were modified.")


if __name__ == "__main__":
    main()
