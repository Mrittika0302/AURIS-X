
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SILVER_DIR = ROOT / "data" / "silver"
GOLD_DIR = ROOT / "data" / "gold"
REPORT_DIR = ROOT / "reports"

SNAP_REVIEW_M = 250.0

# Names that appear to describe campus facilities rather than institutions.
CAMPUS_FEATURE_NAME_PATTERNS = (
    "cricket ground",
    "bus - parking",
)


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
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    source = latest_file(
        SILVER_DIR, "education_network_matches_*.csv"
    )
    df = pd.read_csv(source)

    required = {
        "osm_key", "name", "facility_type",
        "driving_snap_distance_m", "walking_snap_distance_m",
        "driving_match_status", "walking_match_status",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    names = df["name"].fillna("").astype(str).str.strip().str.casefold()
    driving = pd.to_numeric(
        df["driving_snap_distance_m"], errors="coerce"
    )
    walking = pd.to_numeric(
        df["walking_snap_distance_m"], errors="coerce"
    )

    df["review_high_driving_snap"] = driving > SNAP_REVIEW_M
    df["review_high_walking_snap"] = walking > SNAP_REVIEW_M

    df["review_missing_name"] = names.eq("")

    df["review_possible_campus_feature"] = names.apply(
        lambda name: any(
            pattern in name
            for pattern in CAMPUS_FEATURE_NAME_PATTERNS
        )
    )

    df["review_any_snap"] = (
        df["review_high_driving_snap"]
        | df["review_high_walking_snap"]
        | df["driving_match_status"].ne("matched")
        | df["walking_match_status"].ne("matched")
    )

    # Keep all records. This flag marks records needing classification
    # review; it does not claim that they are definitively non-institutions.
    df["review_classification"] = (
        df["review_possible_campus_feature"]
        | df["review_missing_name"]
    )

    df["include_in_primary_facility_analysis"] = (
        ~df["review_possible_campus_feature"]
        & df["driving_match_status"].isin(
            ["matched", "matched_review_snap"]
        )
        & df["walking_match_status"].isin(
            ["matched", "matched_review_snap"]
        )
    )

    df["analysis_note"] = "Retained; verify OSM data before interpretation"

    df.loc[
        df["review_possible_campus_feature"],
        "analysis_note"
    ] = "Possible campus sub-feature; review before counting as institution"

    df.loc[
        df["review_missing_name"],
        "analysis_note"
    ] = "Unnamed education-tagged feature; identity unverified"

    df.loc[
        df["review_any_snap"],
        "analysis_note"
    ] = df.loc[
        df["review_any_snap"], "analysis_note"
    ].astype(str) + "; network snap distance flagged"

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_csv = GOLD_DIR / f"education_analysis_ready_{timestamp}.csv"
    review_csv = REPORT_DIR / f"education_analysis_review_{timestamp}.csv"
    report_json = REPORT_DIR / f"education_analysis_preparation_{timestamp}.json"

    df.to_csv(output_csv, index=False, encoding="utf-8-sig")

    review_mask = (
        df["review_any_snap"]
        | df["review_classification"]
    )
    df.loc[review_mask].to_csv(
        review_csv, index=False, encoding="utf-8-sig"
    )

    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_file": str(source.relative_to(ROOT)),
        "analysis_ready_file": str(output_csv.relative_to(ROOT)),
        "review_file": str(review_csv.relative_to(ROOT)),
        "total_records_retained": int(len(df)),
        "high_driving_snap_count": int(df["review_high_driving_snap"].sum()),
        "high_walking_snap_count": int(df["review_high_walking_snap"].sum()),
        "missing_name_count": int(df["review_missing_name"].sum()),
        "possible_campus_feature_count": int(
            df["review_possible_campus_feature"].sum()
        ),
        "any_network_or_classification_review_count": int(review_mask.sum()),
        "primary_facility_flag_count": int(
            df["include_in_primary_facility_analysis"].sum()
        ),
        "threshold_snap_review_m": SNAP_REVIEW_M,
        "limitations": [
            "Flags are screening aids, not ground-truth classifications.",
            "OSM tags and names are not independently verified.",
            "A campus feature may be tagged as a college in OSM.",
            "Network snap distance does not measure route distance or travel time.",
            "No coordinates or source records were modified or deleted.",
        ],
    }

    with report_json.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("=" * 60)
    print("EDUCATION ANALYSIS PREPARATION")
    print("=" * 60)
    print(f"Source records: {len(df)}")
    print(f"Records retained: {len(df)}")
    print(f"High driving snap: {report['high_driving_snap_count']}")
    print(f"High walking snap: {report['high_walking_snap_count']}")
    print(f"Missing names: {report['missing_name_count']}")
    print(f"Possible campus sub-features: {report['possible_campus_feature_count']}")
    print(f"Records flagged for review: {report['any_network_or_classification_review_count']}")
    print(f"Primary facility flag: {report['primary_facility_flag_count']}")
    print(f"\nAnalysis-ready CSV: {output_csv}")
    print(f"Review CSV: {review_csv}")
    print(f"Report JSON: {report_json}")
    print("\nNo source records or coordinates were modified.")


if __name__ == "__main__":
    main()
