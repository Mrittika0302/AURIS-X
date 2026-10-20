
import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CATEGORY_RULES = {
    "healthcare": [
        ("amenity", {
            "hospital", "clinic", "doctors", "dentist",
            "pharmacy", "health_post"
        }),
    ],
    "education": [
        ("amenity", {
            "school", "college", "university", "kindergarten",
            "library"
        }),
    ],
    "transport": [
        ("public_transport", None),
        ("highway", {"bus_stop"}),
        ("amenity", {"bus_station"}),
        ("railway", {"station", "halt", "tram_stop", "subway_entrance"}),
        ("aeroway", {"terminal"}),
    ],
    "parks": [
        ("leisure", {"park", "playground", "garden", "nature_reserve", "recreation_ground", "pitch"}),
        ("landuse", {"recreation_ground", "village_green"}),
    ],
    "water": [
        ("amenity", {"drinking_water"}),
        ("man_made", {"water_tower", "reservoir_covered", "water_works", "water_well"}),
        ("water", {"reservoir"}),
        ("waterway", {"water_point"}),
    ],
    "sanitation": [
        ("amenity", {"toilets"}),
        ("man_made", {"wastewater_plant", "sewage_pumping_station"}),
        ("sewer", None),
    ],
    "emergency_services": [
        ("amenity", {"fire_station", "police", "ambulance_station"}),
        ("emergency", None),
    ],
}

FIELDS = [
    "facility_uid",
    "service_domain",
    "osm_type",
    "osm_id",
    "facility_name",
    "facility_category",
    "latitude",
    "longitude",
    "source",
    "source_url",
    "license",
    "source_file",
    "review_flags",
]


def matches_category(tags, category):
    for key, allowed_values in CATEGORY_RULES[category]:
        value = tags.get(key)
        if value and (allowed_values is None or value in allowed_values):
            return key, value
    return None, None


def normalize_record(record, category, source_path):
    tags = record.get("tags")
    if not isinstance(tags, dict):
        tags = {}

    tag_key, tag_value = matches_category(tags, category)
    if tag_key is None:
        return None

    osm_type = str(record.get("type", "")).strip()
    osm_id = str(record.get("id", "")).strip()
    flags = []

    if not osm_type or not osm_id:
        flags.append("missing_identity")

    try:
        location = record
        if not ("lat" in location and "lon" in location):
            location = record.get("center") or {}
        lat = float(location["lat"])
        lon = float(location["lon"])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("coordinates out of range")
    except (KeyError, TypeError, ValueError):
        lat = ""
        lon = ""
        flags.append("invalid_or_missing_coordinates")

    name = str(tags.get("name", "")).strip()
    if not name:
        flags.append("missing_name")

    if not osm_type or not osm_id:
        uid = ""
    else:
        uid = f"{category}:{osm_type}:{osm_id}"

    return {
        "facility_uid": uid,
        "service_domain": category,
        "osm_type": osm_type,
        "osm_id": osm_id,
        "facility_name": name,
        "facility_category": tag_value,
        "latitude": lat,
        "longitude": lon,
        "source": "OpenStreetMap",
        "source_url": (
            f"https://www.openstreetmap.org/{osm_type}/{osm_id}"
            if osm_type and osm_id else ""
        ),
        "license": "ODbL",
        "source_file": str(source_path.relative_to(ROOT)),
        "review_flags": ";".join(flags),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Normalize category-matched OSM JSON to a new CSV."
    )
    parser.add_argument("--input", required=True)
    parser.add_argument(
        "--category",
        required=True,
        choices=sorted(CATEGORY_RULES),
    )
    parser.add_argument("--output-dir", default="data/gold")
    args = parser.parse_args()

    source_path = Path(args.input).resolve()
    output_dir = Path(args.output_dir).resolve()

    try:
        source_path.relative_to(ROOT)
    except ValueError:
        parser.error("Input file must be inside the AURIS-X project.")

    if not source_path.is_file():
        parser.error(f"Input file not found: {source_path}")

    try:
        with source_path.open("r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(f"Could not read valid JSON: {exc}")

    records = payload.get("elements") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        parser.error("Expected an OSM JSON object containing elements.")

    rows = []
    seen = set()
    duplicate_count = 0

    for record in records:
        if not isinstance(record, dict):
            continue

        row = normalize_record(record, args.category, source_path)
        if row is None:
            continue

        identity = (row["osm_type"], row["osm_id"])
        if identity in seen:
            duplicate_count += 1
            existing_flags = row["review_flags"].split(";") if row["review_flags"] else []
            existing_flags.append("duplicate_identity")
            row["review_flags"] = ";".join(existing_flags)
        else:
            seen.add(identity)

        rows.append(row)

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"{args.category}_ingested_{timestamp}.csv"

    # Exclusive creation prevents accidental overwrite if a name already exists.
    with output_path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    flagged = sum(bool(row["review_flags"]) for row in rows)

    print(json.dumps({
        "category": args.category,
        "source_file": str(source_path.relative_to(ROOT)),
        "source_records": len(records),
        "matched_records": len(rows),
        "unique_osm_identities": len(seen),
        "duplicate_records": duplicate_count,
        "records_with_review_flags": flagged,
        "output_file": str(output_path),
        "source_modified": False,
    }, indent=2))


if __name__ == "__main__":
    main()
