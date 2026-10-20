
import argparse
import json
from collections import Counter
from pathlib import Path


ALLOWED_CATEGORIES = {
    "healthcare",
    "education",
    "transport",
    "parks",
    "water",
    "sanitation",
    "emergency_services",
}


def validate_records(records, category):
    """Validate OSM-style records without modifying the source."""
    issues = []
    seen_ids = set()
    stats = Counter()

    for index, record in enumerate(records):
        identity = (record.get("type"), record.get("id"))
        tags = record.get("tags") or {}
        location = f"record[{index}] {identity}"

        if not record.get("type") or record.get("id") is None:
            issues.append({
                "record": location,
                "severity": "error",
                "code": "missing_identity",
                "message": "OSM element type or ID is missing.",
            })
        elif identity in seen_ids:
            issues.append({
                "record": location,
                "severity": "error",
                "code": "duplicate_identity",
                "message": "Duplicate OSM element identity.",
            })
        else:
            seen_ids.add(identity)

        lat = record.get("lat")
        lon = record.get("lon")

        # OSM ways and relations may have geometry instead of node coordinates.
        if record.get("type") == "node":
            try:
                lat = float(lat)
                lon = float(lon)
                valid_coordinates = (
                    -90 <= lat <= 90 and -180 <= lon <= 180
                )
            except (TypeError, ValueError):
                valid_coordinates = False

            if not valid_coordinates:
                issues.append({
                    "record": location,
                    "severity": "error",
                    "code": "invalid_coordinates",
                    "message": "Node coordinates are missing or invalid.",
                })
        elif lat is not None or lon is not None:
            try:
                lat = float(lat)
                lon = float(lon)
                valid_coordinates = (
                    -90 <= lat <= 90 and -180 <= lon <= 180
                )
            except (TypeError, ValueError):
                valid_coordinates = False

            if not valid_coordinates:
                issues.append({
                    "record": location,
                    "severity": "error",
                    "code": "invalid_coordinates",
                    "message": "Provided coordinates are invalid.",
                })

        if not isinstance(tags, dict):
            issues.append({
                "record": location,
                "severity": "error",
                "code": "invalid_tags",
                "message": "The tags field must be an object.",
            })
            tags = {}

        if not str(tags.get("name", "")).strip():
            issues.append({
                "record": location,
                "severity": "review",
                "code": "missing_name",
                "message": "Name is missing; inspect rather than automatically reject.",
            })

        category_tag = tags.get("amenity") or tags.get("leisure")
        if not category_tag:
            category_tag = tags.get("public_transport") or tags.get("shop")

        if not category_tag:
            issues.append({
                "record": location,
                "severity": "review",
                "code": "missing_category_tag",
                "message": "No recognized category tag was found.",
            })

        stats["records_checked"] += 1

    error_count = sum(
        issue["severity"] == "error" for issue in issues
    )
    review_count = sum(
        issue["severity"] == "review" for issue in issues
    )

    return {
        "category": category,
        "records_checked": len(records),
        "unique_identities": len(seen_ids),
        "error_count": error_count,
        "review_count": review_count,
        "issue_counts": dict(Counter(
            issue["code"] for issue in issues
        )),
        "issues": issues,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Read-only validator for OSM-style category data."
    )
    parser.add_argument("--input", required=True, help="Input OSM JSON file")
    parser.add_argument(
        "--category",
        required=True,
        choices=sorted(ALLOWED_CATEGORIES),
    )
    parser.add_argument(
        "--report",
        help="Optional report JSON path. Must not overwrite the input file.",
    )
    args = parser.parse_args()

    input_path = Path(args.input).resolve()

    try:
        with input_path.open("r", encoding="utf-8-sig") as handle:
            source = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(f"Cannot read valid JSON input: {exc}")

    if isinstance(source, dict):
        records = source.get("elements")
    else:
        records = None

    if not isinstance(records, list):
        parser.error("Expected an OSM JSON object containing an elements list.")

    report = validate_records(records, args.category)

    print(json.dumps({
        key: value
        for key, value in report.items()
        if key != "issues"
    }, indent=2))

    if args.report:
        report_path = Path(args.report).resolve()
        if report_path == input_path:
            parser.error("Report path cannot overwrite the input file.")

        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, ensure_ascii=False)
            handle.write("\n")

        print(f"Full report saved to: {report_path}")


if __name__ == "__main__":
    main()
