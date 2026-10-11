
from pathlib import Path
from collections import Counter
from datetime import datetime
import json

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
REPORT_DIR = ROOT / "reports"

# Same approximate bounding box used in the download.
SOUTH, WEST, NORTH, EAST = 10.85, 76.85, 11.15, 77.15


def get_coordinates(element):
    """Extract coordinates from an OSM node or way/relation center."""
    if element.get("type") == "node":
        lat = element.get("lat")
        lon = element.get("lon")
    else:
        center = element.get("center", {})
        lat = center.get("lat")
        lon = center.get("lon")

    if not isinstance(lat, (int, float)):
        return None
    if not isinstance(lon, (int, float)):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None

    return lat, lon


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    files = sorted(
        RAW_DIR.glob("healthcare_osm_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    # Exclude metadata files.
    files = [
        path for path in files
        if not path.name.endswith("_metadata.json")
    ]

    if not files:
        raise FileNotFoundError(
            "No healthcare JSON download found in data/raw."
        )

    source_file = files[0]
    print("=" * 60)
    print("AURIS-X | HEALTHCARE DATA VALIDATION")
    print("=" * 60)
    print(f"Input: {source_file.name}")

    data = json.loads(source_file.read_text(encoding="utf-8"))
    elements = data.get("elements", [])

    category_counts = Counter()
    missing_coordinates = []
    outside_bbox = []
    invalid_ids = []
    duplicate_ids = []
    seen_ids = set()
    coordinate_keys = set()
    duplicate_coordinates = []

    valid_coordinate_count = 0
    inside_bbox_count = 0

    for element in elements:
        element_type = element.get("type", "unknown")
        osm_id = element.get("id")

        if not isinstance(osm_id, int):
            invalid_ids.append(element_type)
        else:
            key = (element_type, osm_id)
            if key in seen_ids:
                duplicate_ids.append({
                    "type": element_type,
                    "id": osm_id,
                })
            seen_ids.add(key)

        tags = element.get("tags", {})
        category = (
            tags.get("amenity")
            or tags.get("healthcare")
            or "unclassified"
        )
        category_counts[category] += 1

        coordinates = get_coordinates(element)

        if coordinates is None:
            missing_coordinates.append({
                "type": element_type,
                "id": osm_id,
            })
            continue

        valid_coordinate_count += 1
        lat, lon = coordinates

        if SOUTH <= lat <= NORTH and WEST <= lon <= EAST:
            inside_bbox_count += 1
        else:
            outside_bbox.append({
                "type": element_type,
                "id": osm_id,
                "lat": lat,
                "lon": lon,
            })

        # This flags shared point coordinates for review.
        # Different facilities can legitimately share coordinates.
        coord_key = (round(lat, 6), round(lon, 6))
        if coord_key in coordinate_keys:
            duplicate_coordinates.append({
                "type": element_type,
                "id": osm_id,
                "lat": lat,
                "lon": lon,
            })
        coordinate_keys.add(coord_key)

    report = {
        "project": "AURIS-X",
        "validated_at": datetime.now().astimezone().isoformat(),
        "source_file": str(source_file.relative_to(ROOT)),
        "bounding_box": {
            "south": SOUTH,
            "west": WEST,
            "north": NORTH,
            "east": EAST,
        },
        "total_records": len(elements),
        "valid_coordinate_records": valid_coordinate_count,
        "missing_or_invalid_coordinates": len(missing_coordinates),
        "records_inside_bbox": inside_bbox_count,
        "records_outside_bbox": len(outside_bbox),
        "records_missing_numeric_ids": len(invalid_ids),
        "duplicate_osm_ids": len(duplicate_ids),
        "repeated_coordinate_records": len(duplicate_coordinates),
        "category_counts": dict(category_counts),
        "issues": {
            "missing_coordinates": missing_coordinates,
            "outside_bbox": outside_bbox,
            "missing_numeric_ids": invalid_ids,
            "duplicate_osm_ids": duplicate_ids,
            "repeated_coordinates": duplicate_coordinates,
        },
        "limitations": [
            "Bounding box is approximate, not an official city boundary.",
            "Repeated coordinates do not necessarily mean duplicate facilities.",
            "Valid coordinates do not prove a facility exists or is operational.",
            "OSM coverage may be incomplete.",
        ],
    }

    report_file = REPORT_DIR / "healthcare_validation_report.json"
    report_file.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print(f"\nTotal records: {len(elements)}")
    print(f"Records with valid coordinates: {valid_coordinate_count}")
    print(f"Missing/invalid coordinates: {len(missing_coordinates)}")
    print(f"Records inside bounding box: {inside_bbox_count}")
    print(f"Records outside bounding box: {len(outside_bbox)}")
    print(f"Duplicate OSM IDs: {len(duplicate_ids)}")
    print(f"Repeated coordinate records: {len(duplicate_coordinates)}")

    print("\nCategories:")
    for category, count in sorted(category_counts.items()):
        print(f"  {category}: {count}")

    print(f"\nFull report saved to: {report_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
