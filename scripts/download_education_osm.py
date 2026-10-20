
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
REPORT_DIR = ROOT / "reports"

SOUTH, WEST, NORTH, EAST = 10.85, 76.85, 11.15, 77.15

# Try alternative public Overpass servers if one times out.
OVERPASS_SERVERS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

QUERY = f"""
[out:json][timeout:120];
(
  nwr["amenity"~"^(school|college|university|kindergarten)$"]
    ({SOUTH},{WEST},{NORTH},{EAST});
  nwr["office"="educational_institution"]
    ({SOUTH},{WEST},{NORTH},{EAST});
  nwr["education"]
    ({SOUTH},{WEST},{NORTH},{EAST});
);
out center tags;
"""


def download_data():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "AURIS-X educational research prototype"
    })

    for server in OVERPASS_SERVERS:
        print(f"\nTrying server: {server}")

        try:
            response = session.post(
                server,
                data={"data": QUERY},
                timeout=(20, 180),
            )
            response.raise_for_status()
            payload = response.json()

            if not isinstance(payload.get("elements"), list):
                print("Unexpected response format; trying next server.")
                continue

            print("Download successful.")
            return payload, server

        except (requests.RequestException, ValueError) as exc:
            print(f"Server failed: {exc}")
            time.sleep(2)

    return None, None


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 55)
    print("AURIS-X EDUCATION OSM DOWNLOAD")
    print("=" * 55)
    print(f"Bounding box: {SOUTH}, {WEST}, {NORTH}, {EAST}")

    payload, successful_server = download_data()

    if payload is None:
        print("\nAll servers failed. No new data file was saved.")
        print("Wait a while before trying again.")
        return

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    elements = payload["elements"]

    raw_path = RAW_DIR / f"education_osm_{timestamp}.json"
    report_path = REPORT_DIR / f"education_download_report_{timestamp}.json"

    with raw_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    amenity_counts = {}
    element_type_counts = {}
    other_tag_counts = {}

    for element in elements:
        tags = element.get("tags", {})

        amenity = tags.get("amenity", "not_specified")
        kind = element.get("type", "unknown")

        amenity_counts[amenity] = amenity_counts.get(amenity, 0) + 1
        element_type_counts[kind] = element_type_counts.get(kind, 0) + 1

        for key in ("office", "education"):
            if key in tags:
                label = f"{key}={tags[key]}"
                other_tag_counts[label] = other_tag_counts.get(label, 0) + 1

    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source": "OpenStreetMap Overpass API",
        "successful_server": successful_server,
        "study_area_bbox": {
            "south": SOUTH,
            "west": WEST,
            "north": NORTH,
            "east": EAST,
        },
        "feature_count": len(elements),
        "element_type_counts": element_type_counts,
        "amenity_tag_counts": amenity_counts,
        "other_education_tag_counts": other_tag_counts,
        "raw_file": str(raw_path.relative_to(ROOT)),
        "limitations": [
            "The bounding box is approximate, not an official city boundary.",
            "OSM completeness and operating status are unverified.",
            "Nodes, ways, and relations may describe overlapping facilities.",
            "Accreditation, enrolment, capacity, and school quality are unknown.",
        ],
    }

    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\nDOWNLOAD COMPLETE")
    print(f"Features retrieved: {len(elements)}")
    print(f"Raw data saved: {raw_path}")
    print(f"Report saved: {report_path}")
    print("\nAmenity counts:")
    for key, count in sorted(amenity_counts.items()):
        print(f"  {key}: {count}")
    print("\nElement types:")
    for key, count in sorted(element_type_counts.items()):
        print(f"  {key}: {count}")


if __name__ == "__main__":
    main()
