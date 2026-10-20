
import csv
import json
import re
import sys
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "data" / "staging" / "category_ingestion"
REPORT_DIR = ROOT / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

FILES = {
    "transport": "transport_ingested_20261015T160811Z.csv",
    "parks": "parks_ingested_20261015T162230Z.csv",
    "water": "water_ingested_20261015T160811Z.csv",
    "sanitation": "sanitation_ingested_20261015T160812Z.csv",
    "emergency_services": "emergency_services_ingested_20261015T160812Z.csv",
}

BBOX = {
    "south": 10.85, "west": 76.85,
    "north": 11.15, "east": 77.15,
}

REQUIRED_COLUMNS = {
    "facility_uid", "service_domain", "osm_type", "osm_id",
    "facility_name", "facility_category", "latitude", "longitude",
    "source", "source_url", "license", "source_file", "review_flags",
}

PROVENANCE_COLUMNS = {"source", "source_url", "license", "source_file"}
VALID_OSM_TYPES = {"node", "way", "relation"}


def clean(value):
    return str(value or "").strip()


def parse_coordinate(value):
    try:
        number = float(value)
        if not (-float("inf") < number < float("inf")):
            return None
        return number
    except (ValueError, TypeError):
        return None


def expected_uid(domain, osm_type, osm_id):
    return f"{domain}:{osm_type}:{osm_id}"


report = {
    "generated_utc": datetime.now(timezone.utc).isoformat(),
    "validator_version": "2.0",
    "source": "Existing staged OpenStreetMap category CSVs",
    "study_bbox": BBOX,
    "required_columns": sorted(REQUIRED_COLUMNS),
    "policy": {
        "missing_names": "warning; retain record for review",
        "outside_bbox": "warning; retain record for boundary review",
        "critical_integrity_errors": "fail validation",
        "source_datasets_modified": False,
    },
    "categories": {},
}

critical_errors = []
warning_count = 0
total_records = 0

for domain, filename in FILES.items():
    path = STAGING / filename

    if not path.exists():
        message = f"{domain}: missing input file: {path}"
        report["categories"][domain] = {
            "status": "FAIL",
            "file": str(path),
            "errors": [message],
        }
        critical_errors.append(message)
        continue

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = set(reader.fieldnames or [])
        rows = list(reader)

    total_records += len(rows)
    missing_columns = sorted(REQUIRED_COLUMNS - headers)

    if missing_columns:
        message = f"{domain}: missing required columns: {missing_columns}"
        report["categories"][domain] = {
            "status": "FAIL",
            "file": filename,
            "records": len(rows),
            "missing_columns": missing_columns,
            "errors": [message],
        }
        critical_errors.append(message)
        # Cannot safely validate fields that do not exist.
        continue

    errors = []
    warnings = []
    seen_uid = Counter()
    seen_osm_identity = Counter()
    missing_names = 0
    missing_ids = 0
    invalid_coordinates = 0
    outside_bbox = 0
    domain_mismatches = 0
    invalid_osm_types = 0
    uid_mismatches = 0
    missing_provenance = Counter()
    flags_distribution = Counter()
    rows_with_flags = 0

    for line_number, row in enumerate(rows, start=2):
        uid = clean(row.get("facility_uid"))
        row_domain = clean(row.get("service_domain"))
        osm_type = clean(row.get("osm_type")).lower()
        osm_id = clean(row.get("osm_id"))

        if not clean(row.get("facility_name")):
            missing_names += 1

        if not uid or not osm_id:
            missing_ids += 1

        if osm_type not in VALID_OSM_TYPES:
            invalid_osm_types += 1

        if row_domain != domain:
            domain_mismatches += 1

        if uid:
            seen_uid[uid] += 1

        if osm_type in VALID_OSM_TYPES and osm_id:
            seen_osm_identity[(osm_type, osm_id)] += 1

        if uid and osm_type in VALID_OSM_TYPES and osm_id:
            if uid != expected_uid(row_domain, osm_type, osm_id):
                uid_mismatches += 1

        lat = parse_coordinate(row.get("latitude"))
        lon = parse_coordinate(row.get("longitude"))

        if (
            lat is None or lon is None
            or not (-90 <= lat <= 90)
            or not (-180 <= lon <= 180)
        ):
            invalid_coordinates += 1
        elif not (
            BBOX["south"] <= lat <= BBOX["north"]
            and BBOX["west"] <= lon <= BBOX["east"]
        ):
            outside_bbox += 1

        for column in PROVENANCE_COLUMNS:
            if not clean(row.get(column)):
                missing_provenance[column] += 1

        flags = clean(row.get("review_flags")) or "(none)"
        flags_distribution[flags] += 1
        if flags != "(none)":
            rows_with_flags += 1

    duplicate_uid_rows = sum(
        count - 1 for count in seen_uid.values() if count > 1
    )
    duplicate_osm_identity_rows = sum(
        count - 1 for count in seen_osm_identity.values() if count > 1
    )

    # Critical integrity failures.
    critical_metrics = {
        "missing_ids": missing_ids,
        "invalid_osm_types": invalid_osm_types,
        "invalid_coordinates": invalid_coordinates,
        "duplicate_uid_rows": duplicate_uid_rows,
        "duplicate_osm_identity_rows": duplicate_osm_identity_rows,
        "domain_mismatches": domain_mismatches,
        "uid_mismatches": uid_mismatches,
    }

    for metric, count in critical_metrics.items():
        if count:
            errors.append(f"{metric}: {count}")

    # Review warnings do not automatically reject a record.
    if missing_names:
        warnings.append(f"missing_names: {missing_names}")
    if outside_bbox:
        warnings.append(f"outside_approximate_bbox: {outside_bbox}")
    if sum(missing_provenance.values()):
        warnings.append("some provenance fields are blank")

    status = "FAIL" if errors else ("WARN" if warnings else "PASS")

    result = {
        "file": filename,
        "status": status,
        "records": len(rows),
        "columns_present": len(headers),
        "required_columns_missing": [],
        "unique_facility_uids": len(seen_uid),
        "unique_osm_identities": len(seen_osm_identity),
        **critical_metrics,
        "missing_names": missing_names,
        "outside_approximate_bbox": outside_bbox,
        "missing_provenance_by_column": dict(missing_provenance),
        "rows_with_existing_review_flags": rows_with_flags,
        "review_flags_distribution": dict(flags_distribution),
        "warnings": warnings,
        "errors": errors,
    }
    report["categories"][domain] = result

    critical_errors.extend(
        f"{domain}: {error}" for error in errors
    )
    warning_count += len(warnings)

    print(
        f"{domain}: {status} | rows={len(rows)} | "
        f"missing_names={missing_names} | "
        f"invalid_coords={invalid_coordinates} | "
        f"duplicate_OSM_ids={duplicate_osm_identity_rows} | "
        f"outside_bbox={outside_bbox}"
    )

report["summary"] = {
    "categories_expected": len(FILES),
    "categories_checked": sum(
        1 for item in report["categories"].values()
        if item.get("status") in {"PASS", "WARN", "FAIL"}
    ),
    "total_records_read": total_records,
    "critical_error_count": len(critical_errors),
    "category_warning_count": warning_count,
    "overall_status": "FAIL" if critical_errors else "PASS",
    "critical_errors": critical_errors,
}

timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
output = REPORT_DIR / f"phase3_module4_validation_{timestamp}.json"
output.write_text(
    json.dumps(report, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print(f"\nTotal records read: {total_records}")
print(f"Critical errors: {len(critical_errors)}")
print(f"Report saved: {output}")
print(f"Overall result: {report['summary']['overall_status']}")

sys.exit(1 if critical_errors else 0)
