
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SILVER_DIR = ROOT / "data" / "silver"
REPORT_DIR = ROOT / "reports"

REVIEW_THRESHOLD_M = 250.0


def main():
    files = sorted(
        SILVER_DIR.glob("education_network_matches_*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not files:
        raise FileNotFoundError(
            "No education_network_matches_*.csv file found."
        )

    source = files[0]
    df = pd.read_csv(source)

    required = {
        "osm_type", "osm_id", "osm_key", "name",
        "facility_type", "latitude", "longitude",
        "driving_snap_distance_m", "walking_snap_distance_m",
        "driving_match_status", "walking_match_status",
    }

    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    drive = pd.to_numeric(
        df["driving_snap_distance_m"], errors="coerce"
    )
    walk = pd.to_numeric(
        df["walking_snap_distance_m"], errors="coerce"
    )

    review_mask = (
        (drive > REVIEW_THRESHOLD_M)
        | (walk > REVIEW_THRESHOLD_M)
        | df["driving_match_status"].ne("matched")
        | df["walking_match_status"].ne("matched")
    )

    columns = [
        "osm_type", "osm_id", "osm_key", "name", "facility_type",
        "latitude", "longitude",
        "driving_node", "driving_snap_distance_m",
        "driving_match_status",
        "walking_node", "walking_snap_distance_m",
        "walking_match_status",
    ]

    review = df.loc[review_mask, columns].copy()

    # Add a concise explanation of why each row was flagged.
    def reason(row):
        reasons = []
        d = pd.to_numeric(
            pd.Series([row["driving_snap_distance_m"]]),
            errors="coerce",
        ).iloc[0]
        w = pd.to_numeric(
            pd.Series([row["walking_snap_distance_m"]]),
            errors="coerce",
        ).iloc[0]

        if pd.isna(d):
            reasons.append("missing_driving_distance")
        elif d > REVIEW_THRESHOLD_M:
            reasons.append("driving_snap_over_250m")

        if pd.isna(w):
            reasons.append("missing_walking_distance")
        elif w > REVIEW_THRESHOLD_M:
            reasons.append("walking_snap_over_250m")

        if row["driving_match_status"] != "matched":
            reasons.append("driving_status_" + str(row["driving_match_status"]))

        if row["walking_match_status"] != "matched":
            reasons.append("walking_status_" + str(row["walking_match_status"]))

        return ";".join(reasons)

    review["review_reason"] = review.apply(reason, axis=1)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_csv = REPORT_DIR / f"education_network_review_{timestamp}.csv"
    output_json = REPORT_DIR / f"education_network_review_{timestamp}.json"

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    review.to_csv(output_csv, index=False, encoding="utf-8-sig")

    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_file": str(source.relative_to(ROOT)),
        "facility_count": int(len(df)),
        "review_threshold_m": REVIEW_THRESHOLD_M,
        "facilities_flagged": int(len(review)),
        "driving_over_threshold": int((drive > REVIEW_THRESHOLD_M).sum()),
        "walking_over_threshold": int((walk > REVIEW_THRESHOLD_M).sum()),
        "flagged_in_both_modes": int(
            ((drive > REVIEW_THRESHOLD_M) & (walk > REVIEW_THRESHOLD_M)).sum()
        ),
        "review_csv": str(output_csv.relative_to(ROOT)),
        "note": (
            "Flags indicate a need for review, not necessarily incorrect matches. "
            "No source data or coordinates were modified."
        ),
    }

    with output_json.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("=" * 60)
    print("EDUCATION NETWORK MATCH REVIEW")
    print("=" * 60)
    print(f"Input facilities: {len(df)}")
    print(f"Flagged for review: {len(review)}")
    print(f"Driving over {REVIEW_THRESHOLD_M:.0f} m: {summary['driving_over_threshold']}")
    print(f"Walking over {REVIEW_THRESHOLD_M:.0f} m: {summary['walking_over_threshold']}")
    print(f"Over threshold in both modes: {summary['flagged_in_both_modes']}")

    if review.empty:
        print("\nNo records were flagged.")
    else:
        print("\nReview records:")
        print(
            review[
                ["osm_key", "name", "facility_type",
                 "driving_snap_distance_m", "walking_snap_distance_m",
                 "review_reason"]
            ].to_string(index=False)
        )

    print(f"\nReview CSV: {output_csv}")
    print(f"Summary JSON: {output_json}")


if __name__ == "__main__":
    main()
