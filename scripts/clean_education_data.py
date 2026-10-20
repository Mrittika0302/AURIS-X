
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
SILVER_DIR = ROOT / "data" / "silver"
REPORT_DIR = ROOT / "reports"

VALID_AMENITIES = {
    "school",
    "college",
    "university",
    "kindergarten",
}

EDUCATION_OFFICE = "educational_institution"


def clean_text(value):
    if value is None:
        return None

    value = re.sub(r"\s+", " ", str(value)).strip()
    return value or None


def get_coordinates(element):
    if element.get("type") == "node":
        lat = element.get("lat")
        lon = element.get("lon")
    else:
        center = element.get("center") or {}
        lat = center.get("lat")
        lon = center.get("lon")

    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return None, None

    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None, None

    return lat, lon


def classify_facility(tags):
    amenity = clean_text(tags.get("amenity"))
    office = clean_text(tags.get("office"))
    education = clean_text(tags.get("education"))

    if amenity in VALID_AMENITIES:
        return amenity

    if office == EDUCATION_OFFICE:
        return "educational_institution"

    if education:
        return "education_tagged_other"

    return "other_or_unclassified"


def main():
    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    raw_files = sorted(
        RAW_DIR.glob("education_osm_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not raw_files:
        raise FileNotFoundError(
            "No data/raw/education_osm_*.json file found."
        )

    raw_path = raw_files[0]
    print(f"Reading raw file: {raw_path}")

    with raw_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    elements = payload.get("elements", [])
    rows = []
    rejected = []
    seen_ids = set()

    for element in elements:
        element_type = element.get("type")
        osm_id = element.get("id")
        tags = element.get("tags") or {}

        if not isinstance(tags, dict):
            tags = {}

        if element_type not in {"node", "way", "relation"} or osm_id is None:
            rejected.append({
                "element_type": element_type,
                "osm_id": osm_id,
                "reason": "missing_or_invalid_osm_identifier",
            })
            continue

        unique_key = f"{element_type}/{osm_id}"

        if unique_key in seen_ids:
            rejected.append({
                "element_type": element_type,
                "osm_id": osm_id,
                "reason": "duplicate_element_id",
            })
            continue

        seen_ids.add(unique_key)

        amenity = clean_text(tags.get("amenity"))
        office = clean_text(tags.get("office"))
        education = clean_text(tags.get("education"))

        # Keep relevant educational facilities and other explicitly
        # education-tagged records. Do not treat driving/dancing schools
        # as academic schools merely because of their amenity tag.
        relevant = (
            amenity in VALID_AMENITIES
            or office == EDUCATION_OFFICE
            or education is not None
        )

        if not relevant:
            continue

        lat, lon = get_coordinates(element)

        name = clean_text(tags.get("name"))
        name_en = clean_text(tags.get("name:en"))
        operator = clean_text(tags.get("operator"))

        rows.append({
            "osm_type": element_type,
            "osm_id": int(osm_id),
            "osm_key": unique_key,
            "name": name,
            "name_en": name_en,
            "facility_type": classify_facility(tags),
            "amenity": amenity,
            "office": office,
            "education_tag": education,
            "operator": operator,
            "latitude": lat,
            "longitude": lon,
            "has_name": bool(name or name_en),
            "has_coordinates": lat is not None and lon is not None,
            "source_raw_file": raw_path.name,
        })

    columns = [
        "osm_type",
        "osm_id",
        "osm_key",
        "name",
        "name_en",
        "facility_type",
        "amenity",
        "office",
        "education_tag",
        "operator",
        "latitude",
        "longitude",
        "has_name",
        "has_coordinates",
        "source_raw_file",
    ]

    df = pd.DataFrame(rows, columns=columns)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    silver_path = SILVER_DIR / f"education_clean_{timestamp}.csv"
    report_path = REPORT_DIR / f"education_cleaning_report_{timestamp}.json"
    rejected_path = REPORT_DIR / f"education_rejected_records_{timestamp}.csv"

    df.to_csv(silver_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(rejected, columns=[
        "element_type", "osm_id", "reason"
    ]).to_csv(rejected_path, index=False, encoding="utf-8-sig")

    facility_counts = (
        df["facility_type"].value_counts(dropna=False).to_dict()
        if not df.empty else {}
    )

    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_raw_file": str(raw_path.relative_to(ROOT)),
        "raw_element_count": len(elements),
        "clean_record_count": len(df),
        "rejected_record_count": len(rejected),
        "duplicate_or_invalid_records_rejected": len(rejected),
        "missing_name_count": int((~df["has_name"]).sum()) if not df.empty else 0,
        "missing_coordinate_count": int((~df["has_coordinates"]).sum()) if not df.empty else 0,
        "facility_type_counts": facility_counts,
        "silver_file": str(silver_path.relative_to(ROOT)),
        "rejected_file": str(rejected_path.relative_to(ROOT)),
        "limitations": [
            "OSM records are not verified against official education registers.",
            "Different OSM element types may describe overlapping real-world facilities.",
            "Records without names are retained when otherwise relevant.",
            "Coordinates for ways and relations use the OSM-provided center.",
            "The study area is an approximate bounding box.",
            "Academic level, enrolment, capacity, accreditation, and operating status are not verified.",
        ],
    }

    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\nEDUCATION CLEANING COMPLETE")
    print(f"Raw elements: {len(elements)}")
    print(f"Clean records: {len(df)}")
    print(f"Rejected invalid/duplicate records: {len(rejected)}")
    print(f"Missing names: {report['missing_name_count']}")
    print(f"Missing coordinates: {report['missing_coordinate_count']}")
    print("\nFacility type counts:")
    for key, count in sorted(facility_counts.items()):
        print(f"  {key}: {count}")

    print(f"\nSilver CSV: {silver_path}")
    print(f"Cleaning report: {report_path}")
    print(f"Rejected-record CSV: {rejected_path}")


if __name__ == "__main__":
    main()
