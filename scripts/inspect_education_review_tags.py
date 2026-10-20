
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
REPORT_DIR = ROOT / "reports"
REVIEW_FILE = REPORT_DIR / "education_network_review_20261013T090018Z.csv"


def main():
    if not REVIEW_FILE.exists():
        raise FileNotFoundError(f"Review file not found: {REVIEW_FILE}")

    raw_files = sorted(
        RAW_DIR.glob("education_osm_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not raw_files:
        raise FileNotFoundError("No raw Education OSM JSON file found.")

    raw_path = raw_files[0]
    review = pd.read_csv(REVIEW_FILE, dtype={"osm_id": str})

    with raw_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    wanted = {
        (str(row["osm_type"]), str(row["osm_id"]))
        for _, row in review.iterrows()
    }

    found = {}
    for element in payload.get("elements", []):
        key = (str(element.get("type")), str(element.get("id")))
        if key in wanted:
            found[key] = element

    rows = []
    for _, row in review.iterrows():
        key = (str(row["osm_type"]), str(row["osm_id"]))
        element = found.get(key)

        rows.append({
            "osm_key": row["osm_key"],
            "review_name": row.get("name"),
            "facility_type": row.get("facility_type"),
            "driving_snap_m": row.get("driving_snap_distance_m"),
            "walking_snap_m": row.get("walking_snap_distance_m"),
            "raw_element_found": element is not None,
            "raw_tags_json": json.dumps(
                element.get("tags", {}) if element else {},
                ensure_ascii=False,
                sort_keys=True,
            ),
            "raw_lat": element.get("lat") if element else None,
            "raw_lon": element.get("lon") if element else None,
            "raw_center_lat": (
                element.get("center", {}).get("lat") if element else None
            ),
            "raw_center_lon": (
                element.get("center", {}).get("lon") if element else None
            ),
        })

    result = pd.DataFrame(rows)
    output = REPORT_DIR / "education_review_original_osm_tags.csv"
    result.to_csv(output, index=False, encoding="utf-8-sig")

    print("=" * 65)
    print("EDUCATION REVIEW: ORIGINAL OSM TAGS")
    print("=" * 65)
    print(f"Raw source: {raw_path}")
    print(f"Flagged records: {len(review)}")
    print(f"Matched to raw elements: {sum(r['raw_element_found'] for r in rows)}")
    print(f"Output: {output}\n")

    for record in rows:
        print(f"\n{record['osm_key']} | {record['review_name']}")
        print(f"  Type: {record['facility_type']}")
        print(f"  Driving snap: {record['driving_snap_m']} m")
        print(f"  Walking snap: {record['walking_snap_m']} m")
        print(f"  Raw tags: {record['raw_tags_json']}")

    print("\nNo input files or coordinates were modified.")


if __name__ == "__main__":
    main()
