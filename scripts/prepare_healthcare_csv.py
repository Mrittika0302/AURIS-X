
from pathlib import Path
from datetime import datetime
import csv
import json

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUTPUT_DIR = ROOT / "data" / "silver"
REPORT_DIR = ROOT / "reports"


def get_coordinates(element):
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
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    files = [
        path for path in RAW_DIR.glob("healthcare_osm_*.json")
        if not path.name.endswith("_metadata.json")
    ]

    if not files:
        raise FileNotFoundError(
            "No raw healthcare dataset found in data/raw."
        )

    source = max(files, key=lambda path: path.stat().st_mtime)
    data = json.loads(source.read_text(encoding="utf-8"))
    elements = data.get("elements", [])

    rows = []
    seen_ids = set()
    rejected = 0
    duplicate_ids = 0

    for element in elements:
        element_type = element.get("type", "")
        osm_id = element.get("id")

        if not isinstance(osm_id, int):
            rejected += 1
            continue

        unique_key = (element_type, osm_id)
        if unique_key in seen_ids:
            duplicate_ids += 1
            continue
        seen_ids.add(unique_key)

        coordinates = get_coordinates(element)
        if coordinates is None:
            rejected += 1
            continue

        lat, lon = coordinates
        tags = element.get("tags", {})

        category = (
            tags.get("amenity")
            or tags.get("healthcare")
            or "unclassified"
        )

        rows.append({
            "osm_type": element_type,
            "osm_id": osm_id,
            "name": tags.get("name", ""),
            "category": category,
            "latitude": lat,
            "longitude": lon,
            "street": tags.get("addr:street", ""),
            "city": tags.get("addr:city", ""),
            "postcode": tags.get("addr:postcode", ""),
            "source": "OpenStreetMap",
            "source_url": "https://www.openstreetmap.org/",
            "license": "ODbL",
        })

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = OUTPUT_DIR / f"healthcare_clean_{timestamp}.csv"

    fieldnames = [
        "osm_type", "osm_id", "name", "category",
        "latitude", "longitude", "street", "city",
        "postcode", "source", "source_url", "license",
    ]

    with output_file.open(
        "w", newline="", encoding="utf-8-sig"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    report = {
        "source_file": str(source.relative_to(ROOT)),
        "output_file": str(output_file.relative_to(ROOT)),
        "input_records": len(elements),
        "output_records": len(rows),
        "rejected_records": rejected,
        "duplicate_ids_skipped": duplicate_ids,
        "records_without_names": sum(
            1 for row in rows if not row["name"].strip()
        ),
        "generated_at": datetime.now().astimezone().isoformat(),
        "note": (
            "Normalization only; not proof of facility existence, "
            "operational status, completeness, or service capacity."
        ),
    }

    report_file = REPORT_DIR / "healthcare_cleaning_report.json"
    report_file.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print("=" * 55)
    print("AURIS-X | CLEAN HEALTHCARE DATA")
    print("=" * 55)
    print(f"Input records: {len(elements)}")
    print(f"Clean records: {len(rows)}")
    print(f"Rejected records: {rejected}")
    print(f"Duplicate IDs skipped: {duplicate_ids}")
    print(f"Records without names: {report['records_without_names']}")
    print(f"\nCSV saved to: {output_file}")
    print(f"Report saved to: {report_file}")
    print("=" * 55)


if __name__ == "__main__":
    main()
