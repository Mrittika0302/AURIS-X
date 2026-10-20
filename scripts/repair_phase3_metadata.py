import json
from pathlib import Path
from datetime import datetime, timezone

raw = Path("data/raw")

# Repair only fields supported by the existing transport metadata and log.
transport_path = raw / "transport_osm_20261015T152325Z_metadata.json"
if transport_path.exists():
    meta = json.loads(transport_path.read_text(encoding="utf-8"))
    meta["category"] = "transport"
    meta["source"] = "OpenStreetMap"
    meta["endpoint"] = "https://overpass-api.de/api/interpreter"
    meta["attribution"] = "© OpenStreetMap contributors"
    meta["copyright_url"] = "https://www.openstreetmap.org/copyright"
    meta["retrieved_utc"] = None
    meta["retrieval_time_note"] = (
        "Exact retrieval timestamp not recorded in metadata; "
        "filename contains 20261015T152325Z."
    )
    meta["query"] = None
    meta["query_note"] = (
        "Exact query was not recorded in this metadata file; "
        "do not treat it as verified until recovered from the script or logs."
    )
    transport_path.write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("Transport metadata repaired; unknown fields explicitly marked.")

# Create a transparent placeholder for education; do not invent provenance.
education_path = raw / "education_osm_20261013T085408Z.json"
education_meta_path = raw / "education_osm_20261013T085408Z_metadata.json"

if education_path.exists() and not education_meta_path.exists():
    placeholder = {
        "category": "education",
        "source": None,
        "endpoint": None,
        "retrieved_utc": None,
        "element_count": None,
        "license": None,
        "attribution": None,
        "copyright_url": None,
        "status": "provenance incomplete; verification required",
        "note": (
            "Metadata sidecar was absent. The filename alone is not proof "
            "of the exact source, query, retrieval time, or license. "
            "Recover these details from existing logs or source records."
        ),
    }
    education_meta_path.write_text(
        json.dumps(placeholder, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("Education metadata placeholder created; provenance remains unverified.")
elif education_meta_path.exists():
    print("Education metadata already exists; left unchanged.")
else:
    print("Education raw file not found; no placeholder created.")

print("Raw JSON datasets were not modified.")
