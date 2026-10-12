
from pathlib import Path
import json

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

ACCESS_CSV = (
    ROOT / "data" / "gold"
    / "healthcare_accessibility_by_population_cell.csv"
)
SUMMARY_JSON = (
    ROOT / "reports"
    / "healthcare_accessibility_summary.json"
)
POP_CSV = ROOT / "data" / "silver" / "population_road_matches.csv"
FACILITY_CSV = (
    ROOT / "data" / "silver"
    / "healthcare_network_matches_20261011_122708.csv"
)


def report_distance_comparison(df):
    for mode in ("driving", "walking"):
        col = f"{mode}_distance_m"
        values = pd.to_numeric(df[col], errors="coerce")
        print(f"\n{mode.upper()}")
        print("Valid distances:", int(values.notna().sum()))
        print("Missing distances:", int(values.isna().sum()))
        print("Unique distances:", int(values.nunique()))
        print("Min / median / mean / max:",
              values.min(), values.median(),
              values.mean(), values.max())

    drive = pd.to_numeric(df["driving_distance_m"], errors="coerce")
    walk = pd.to_numeric(df["walking_distance_m"], errors="coerce")
    both = drive.notna() & walk.notna()

    delta = (drive[both] - walk[both]).abs()
    print("\nDRIVING VS WALKING")
    print("Cells reachable in both:", int(both.sum()))
    print("Exactly equal distances:", int((delta == 0).sum()))
    print("Equal percentage:",
          round(float((delta == 0).mean() * 100), 3))
    print("Within 1 metre:", int((delta <= 1).sum()))
    print("Within 100 metres:", int((delta <= 100).sum()))
    print("Absolute difference median:", delta.median())
    print("Absolute difference P90:", delta.quantile(0.90))
    print("Absolute difference maximum:", delta.max())

    cols = [
        c for c in [
            "population_cell_id",
            "cell_id",
            "latitude",
            "longitude",
            "drive_nearest_node_id",
            "walk_nearest_node_id",
            "driving_distance_m",
            "walking_distance_m",
            "driving_facility_id",
            "walking_facility_id",
        ]
        if c in df.columns
    ]

    print("\nEXAMPLE CELLS WITH IDENTICAL DISTANCES")
    equal_rows = df.loc[both & (drive == walk), cols].head(15)
    if equal_rows.empty:
        print("None")
    else:
        print(equal_rows.to_string(index=False))

    print("\nEXAMPLE CELLS WITH LARGEST DISTANCE DIFFERENCES")
    diff_rows = df.loc[both].copy()
    diff_rows["_abs_difference_m"] = delta
    print(
        diff_rows.nlargest(15, "_abs_difference_m")[cols
            + ["_abs_difference_m"]].to_string(index=False)
    )


def main():
    for path in [ACCESS_CSV, SUMMARY_JSON, POP_CSV, FACILITY_CSV]:
        print(f"{path.relative_to(ROOT)}: exists={path.exists()}")
        if not path.exists():
            raise FileNotFoundError(path)

    df = pd.read_csv(ACCESS_CSV)
    print("\nAccessibility output rows:", len(df))
    print("Accessibility columns:", list(df.columns))
    report_distance_comparison(df)

    with open(SUMMARY_JSON, encoding="utf-8") as f:
        summary = json.load(f)
    print("\nSAVED SUMMARY")
    print(json.dumps(summary, indent=2)[:6000])

    pop = pd.read_csv(POP_CSV)
    facilities = pd.read_csv(FACILITY_CSV)

    print("\nPOPULATION NODE MATCHES")
    for col in ["drive_nearest_node_id", "walk_nearest_node_id"]:
        if col in pop.columns:
            print(
                col,
                "unique nodes =", pop[col].nunique(),
                "missing =", int(pop[col].isna().sum())
            )

    print("\nFACILITY NODE MATCHES")
    for col in ["drive_nearest_node_id", "walk_nearest_node_id"]:
        if col in facilities.columns:
            print(
                col,
                "unique nodes =", facilities[col].nunique(),
                "missing =", int(facilities[col].isna().sum())
            )

    print("\nDONE — no files were changed.")


if __name__ == "__main__":
    main()
