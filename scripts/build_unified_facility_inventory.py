
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent

INPUTS = {
    "healthcare": ROOT / "data/silver/healthcare_network_matches_20261011_120504.csv",
    "education": ROOT / "data/silver/education_network_matches_20261013T085941Z.csv",
}

OUTPUT_DIR = ROOT / "data/gold"
REPORT_DIR = ROOT / "reports"


def clean_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def first_existing(row, columns):
    for column in columns:
        if column in row.index:
            value = clean_text(row[column])
            if value:
                return value
    return ""


def truthy(value):
    return clean_text(value).lower() in {"true", "1", "yes"}


def normalize_domain(domain, source):
    records = []

    for _, row in source.iterrows():
        osm_type = clean_text(row.get("osm_type", "")).lower()
        osm_id = clean_text(row.get("osm_id", ""))
        name = clean_text(row.get("name", ""))

        category = first_existing(
            row, ["category", "facility_type", "amenity", "education_tag"]
        )

        latitude = pd.to_numeric(
            pd.Series([row.get("latitude")]), errors="coerce"
        ).iloc[0]
        longitude = pd.to_numeric(
            pd.Series([row.get("longitude")]), errors="coerce"
        ).iloc[0]

        if domain == "healthcare":
            drive_node = clean_text(row.get("drive_nearest_node_id", ""))
            walk_node = clean_text(row.get("walk_nearest_node_id", ""))
            drive_snap = row.get("drive_snap_distance_m")
            walk_snap = row.get("walk_snap_distance_m")
            drive_status = "matched" if drive_node else "missing_node"
            walk_status = "matched" if walk_node else "missing_node"

            if truthy(row.get("drive_review_over_100m", False)):
                drive_status = "review"
            if truthy(row.get("walk_review_over_100m", False)):
                walk_status = "review"

            source_name = clean_text(row.get("source", ""))
            source_url = clean_text(row.get("source_url", ""))
            license_name = clean_text(row.get("license", ""))
            source_file = str(INPUTS[domain].relative_to(ROOT))

        else:
            drive_node = clean_text(row.get("driving_node", ""))
            walk_node = clean_text(row.get("walking_node", ""))
            drive_snap = row.get("driving_snap_distance_m")
            walk_snap = row.get("walking_snap_distance_m")
            drive_status = clean_text(row.get("driving_match_status", "unknown"))
            walk_status = clean_text(row.get("walking_match_status", "unknown"))

            source_name = "OpenStreetMap"
            source_url = ""
            license_name = ""
            source_file = first_existing(
                row, ["source_raw_file"]
            ) or str(INPUTS[domain].relative_to(ROOT))

        review_flags = []

        if not osm_type or not osm_id:
            review_flags.append("missing_osm_identity")
        if not name:
            review_flags.append("missing_name")
        if pd.isna(latitude) or pd.isna(longitude):
            review_flags.append("missing_coordinates")
        elif not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            review_flags.append("coordinates_out_of_range")

        if not drive_node:
            review_flags.append("missing_driving_node")
        if not walk_node:
            review_flags.append("missing_walking_node")
        if drive_status.lower() not in {"matched", "ok"}:
            review_flags.append("driving_match_review")
        if walk_status.lower() not in {"matched", "ok"}:
            review_flags.append("walking_match_review")

        facility_uid = (
            f"{domain}:{osm_type}:{osm_id}"
            if osm_type and osm_id
            else ""
        )

        records.append({
            "facility_uid": facility_uid,
            "service_domain": domain,
            "osm_type": osm_type,
            "osm_id": osm_id,
            "facility_name": name,
            "facility_category": category,
            "latitude": latitude,
            "longitude": longitude,
            "source": source_name,
            "source_url": source_url,
            "license": license_name,
            "source_file": source_file,
            "driving_node_id": drive_node,
            "driving_snap_distance_m": drive_snap,
            "driving_match_status": drive_status,
            "walking_node_id": walk_node,
            "walking_snap_distance_m": walk_snap,
            "walking_match_status": walk_status,
            "review_flags": ";".join(review_flags),
        })

    return pd.DataFrame(records)


def main():
    for path in INPUTS.values():
        if not path.is_file():
            raise FileNotFoundError(f"Required input not found: {path}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    healthcare_raw = pd.read_csv(INPUTS["healthcare"], dtype=str)
    education_raw = pd.read_csv(INPUTS["education"], dtype=str)

    healthcare = normalize_domain("healthcare", healthcare_raw)
    education = normalize_domain("education", education_raw)

    unified = pd.concat([healthcare, education], ignore_index=True)

    # Flag repeated source identities within each service domain.
    duplicate_mask = unified.duplicated(
        subset=["service_domain", "osm_type", "osm_id"],
        keep=False,
    )

    for index in unified.index[duplicate_mask]:
        existing = unified.at[index, "review_flags"]
        flag = "duplicate_domain_osm_identity"
        unified.at[index, "review_flags"] = (
            f"{existing};{flag}" if existing else flag
        )

    # Keep output filenames unique and never overwrite a prior run.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_csv = OUTPUT_DIR / f"unified_facility_inventory_{stamp}.csv"
    output_json = REPORT_DIR / f"unified_facility_inventory_report_{stamp}.json"

    if output_csv.exists() or output_json.exists():
        raise FileExistsError("Output already exists; rerun after the timestamp changes.")

    unified.to_csv(output_csv, index=False)

    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            domain: str(path.relative_to(ROOT))
            for domain, path in INPUTS.items()
        },
        "output_csv": str(output_csv.relative_to(ROOT)),
        "total_records": int(len(unified)),
        "records_by_domain": {
            str(key): int(value)
            for key, value in unified["service_domain"].value_counts().items()
        },
        "missing_name_records": int(
            unified["facility_name"].fillna("").str.strip().eq("").sum()
        ),
        "missing_coordinate_records": int(
            (unified["latitude"].isna() | unified["longitude"].isna()).sum()
        ),
        "duplicate_domain_osm_identity_rows": int(duplicate_mask.sum()),
        "records_with_review_flags": int(
            unified["review_flags"].fillna("").str.strip().ne("").sum()
        ),
        "limitations": [
            "This inventory does not recalculate accessibility.",
            "Education source URL and license are left blank when not present in the input.",
            "A matched road node does not establish accurate travel time.",
            "Facility capacity, buildable land, and construction cost are not inferred.",
            "Source datasets and existing healthcare and education outputs are not modified.",
        ],
    }

    output_json.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("Unified facility inventory created.")
    print(f"CSV report: {output_csv}")
    print(f"JSON summary: {output_json}")
    print(f"Total records: {len(unified)}")
    print("\nRecords by domain:")
    print(unified["service_domain"].value_counts().to_string())
    print(f"\nRows with review flags: {report['records_with_review_flags']}")
    print(f"Duplicate identity rows: {report['duplicate_domain_osm_identity_rows']}")


if __name__ == "__main__":
    main()
