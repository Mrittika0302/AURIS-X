import json
import shutil
from pathlib import Path
from datetime import datetime, timezone

root = Path.cwd()
docs = root / "docs"
reports = root / "reports"
raw = root / "data" / "raw"
staging = root / "data" / "staging" / "category_ingestion"

register_path = docs / "DATA_REGISTER.md"
manifest_path = docs / "DATA_SOURCE_VERSION_MANIFEST.json"

for path in (register_path, manifest_path):
    if not path.exists():
        raise FileNotFoundError(f"Required file missing: {path}")

stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
for path in (register_path, manifest_path):
    backup = path.with_name(path.name + f".backup_{stamp}")
    shutil.copy2(path, backup)
    print(f"Backup: {backup}")

register = register_path.read_text(encoding="utf-8")
start_marker = "## 7. Additional infrastructure categories"
governance_marker = "## Data governance"

if start_marker not in register or governance_marker not in register:
    raise RuntimeError("Could not locate expected section headings; files left unchanged.")

new_section = """## 7. Additional infrastructure categories

All five categories now have raw OpenStreetMap downloads and staged CSV outputs. These are preliminary matched records, not verified counts of unique operating facilities. Collection used the approximate bounding box above, not an official administrative boundary.

### Transport facilities
- Source: OpenStreetMap via Overpass API
- Endpoint recorded in metadata: https://overpass-api.de/api/interpreter
- Raw file: `data/raw/transport_osm_20261015T152325Z.json`
- Metadata: `data/raw/transport_osm_20261015T152325Z_metadata.json`
- Raw elements: 432; staged matched records: 428
- Staged CSV: `data/staging/category_ingestion/transport_ingested_20261015T160811Z.csv`
- License: ODbL recorded in local metadata; attribution field repaired to `© OpenStreetMap contributors`
- Provenance limitation: exact retrieval timestamp and query are not preserved in metadata and remain unverified.
- Validation: 76 records missing names; 0 invalid coordinate pairs; 0 records outside the approximate box; 0 duplicate IDs within this category.

### Parks and open spaces
- Source: OpenStreetMap via Overpass API
- Endpoint: https://overpass-api.de/api/interpreter
- Raw file: `data/raw/parks_osm_20261015T161312Z.json`
- Metadata: `data/raw/parks_osm_20261015T161312Z_metadata.json`
- Retrieved: `2026-10-15T16:13:12.354029+00:00`
- Raw elements: 299; staged matched records: 299
- Staged CSV: `data/staging/category_ingestion/parks_ingested_20261015T162230Z.csv`
- License: Open Database License (ODbL); attribution: © OpenStreetMap contributors
- Validation: 162 records missing names; 0 invalid coordinate pairs; 0 records outside the approximate box; 0 duplicate IDs within this category.

### Water infrastructure
- Source: OpenStreetMap via Overpass API
- Endpoint: https://overpass-api.de/api/interpreter
- Raw file: `data/raw/water_osm_20261015T153117Z.json`
- Metadata: `data/raw/water_osm_20261015T153117Z_metadata.json`
- Retrieved: `2026-10-15T15:31:17.683395+00:00`
- Raw elements: 48; staged matched records: 40
- Staged CSV: `data/staging/category_ingestion/water_ingested_20261015T160811Z.csv`
- License: Open Database License (ODbL); attribution: © OpenStreetMap contributors
- Validation: 30 records missing names; 0 invalid coordinate pairs; 2 records outside the approximate box; 0 duplicate IDs within this category. The two out-of-box records are retained for review.

### Sanitation
- Source: OpenStreetMap via Overpass API
- Endpoint: https://overpass-api.de/api/interpreter
- Raw file: `data/raw/sanitation_osm_20261015T153228Z.json`
- Metadata: `data/raw/sanitation_osm_20261015T153228Z_metadata.json`
- Retrieved: `2026-10-15T15:32:28.342577+00:00`
- Raw elements: 37; staged matched records: 37
- Staged CSV: `data/staging/category_ingestion/sanitation_ingested_20261015T160812Z.csv`
- License: Open Database License (ODbL); attribution: © OpenStreetMap contributors
- Validation: 25 records missing names; 0 invalid coordinate pairs; 0 records outside the approximate box; 0 duplicate IDs within this category.

### Emergency services
- Source: OpenStreetMap via Overpass API
- Endpoint: https://overpass-api.de/api/interpreter
- Raw file: `data/raw/emergency_services_osm_20261015T153401Z.json`
- Metadata: `data/raw/emergency_services_osm_20261015T153401Z_metadata.json`
- Retrieved: `2026-10-15T15:34:01.017274+00:00`
- Raw elements: 87; staged matched records: 87
- Staged CSV: `data/staging/category_ingestion/emergency_services_ingested_20261015T160812Z.csv`
- License: Open Database License (ODbL); attribution: © OpenStreetMap contributors
- Validation: 32 records missing names; 0 invalid coordinate pairs; 0 records outside the approximate box; 0 duplicate IDs within this category.

### Shared limitations and validation status
- Total staged matched records across these five categories: 891.
- Missing names: 325; retain these records and apply a documented review policy rather than inventing names.
- Duplicate-ID check was performed within each category; cross-category and real-world entity deduplication has not been established.
- Coordinate checks verified numeric values and broad coordinate ranges; they do not verify facility existence, geometry completeness, or operational status.
- The bounding box is approximate and is not an official Coimbatore boundary.
- Raw JSON files were preserved; validation report: `reports/phase3_module4_validation.json`.
- Coordinate exception report: `reports/phase3_coordinate_validation.md`.
- Download summary: `reports/phase3_category_download_summary.json`.
- Transport query and exact retrieval time remain unverified. Education provenance and the 415-versus-401 reconciliation remain open.

"""

register = register[:register.index(start_marker)] + new_section + register[register.index(governance_marker):]
register_path.write_text(register, encoding="utf-8")
print(f"Updated: {register_path}")

manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
datasets = manifest.setdefault("datasets", [])

new_datasets = [
    {
        "dataset_id": "transport_facilities_osm_20261015",
        "category": "transport_facilities",
        "source": "OpenStreetMap",
        "source_url": "https://overpass-api.de/api/interpreter",
        "source_file": "data/raw/transport_osm_20261015T152325Z.json",
        "metadata_file": "data/raw/transport_osm_20261015T152325Z_metadata.json",
        "retrieved_at": None,
        "license": "ODbL (recorded in local metadata; attribution corrected)",
        "version": "local snapshot 2026-10-15",
        "status": "downloaded_and_staged; query_and_exact_retrieval_time_unverified",
        "file_exists": (raw / "transport_osm_20261015T152325Z.json").exists(),
        "metadata_file_exists": (raw / "transport_osm_20261015T152325Z_metadata.json").exists(),
        "feature_count": 432,
        "matched_records": 428,
        "staged_file": "data/staging/category_ingestion/transport_ingested_20261015T160811Z.csv",
        "missing_names": 76,
        "invalid_coordinates": 0,
        "outside_approximate_bbox": 0,
        "duplicate_id_rows_within_category": 0
    },
    {
        "dataset_id": "parks_osm_20261015T161312Z",
        "category": "parks",
        "source": "OpenStreetMap",
        "source_url": "https://overpass-api.de/api/interpreter",
        "source_file": "data/raw/parks_osm_20261015T161312Z.json",
        "metadata_file": "data/raw/parks_osm_20261015T161312Z_metadata.json",
        "retrieved_at": "2026-10-15T16:13:12.354029+00:00",
        "license": "ODbL",
        "version": "local snapshot 2026-10-15",
        "status": "downloaded_staged_basic_validation_complete",
        "file_exists": (raw / "parks_osm_20261015T161312Z.json").exists(),
        "metadata_file_exists": (raw / "parks_osm_20261015T161312Z_metadata.json").exists(),
        "feature_count": 299,
        "matched_records": 299,
        "staged_file": "data/staging/category_ingestion/parks_ingested_20261015T162230Z.csv",
        "missing_names": 162,
        "invalid_coordinates": 0,
        "outside_approximate_bbox": 0,
        "duplicate_id_rows_within_category": 0
    },
    {
        "dataset_id": "water_osm_20261015T153117Z",
        "category": "water",
        "source": "OpenStreetMap",
        "source_url": "https://overpass-api.de/api/interpreter",
        "source_file": "data/raw/water_osm_20261015T153117Z.json",
        "metadata_file": "data/raw/water_osm_20261015T153117Z_metadata.json",
        "retrieved_at": "2026-10-15T15:31:17.683395+00:00",
        "license": "ODbL",
        "version": "local snapshot 2026-10-15",
        "status": "downloaded_staged_basic_validation_complete_with_boundary_exceptions",
        "file_exists": (raw / "water_osm_20261015T153117Z.json").exists(),
        "metadata_file_exists": (raw / "water_osm_20261015T153117Z_metadata.json").exists(),
        "feature_count": 48,
        "matched_records": 40,
        "staged_file": "data/staging/category_ingestion/water_ingested_20261015T160811Z.csv",
        "missing_names": 30,
        "invalid_coordinates": 0,
        "outside_approximate_bbox": 2,
        "duplicate_id_rows_within_category": 0
    },
    {
        "dataset_id": "sanitation_osm_20261015T153228Z",
        "category": "sanitation",
        "source": "OpenStreetMap",
        "source_url": "https://overpass-api.de/api/interpreter",
        "source_file": "data/raw/sanitation_osm_20261015T153228Z.json",
        "metadata_file": "data/raw/sanitation_osm_20261015T153228Z_metadata.json",
        "retrieved_at": "2026-10-15T15:32:28.342577+00:00",
        "license": "ODbL",
        "version": "local snapshot 2026-10-15",
        "status": "downloaded_staged_basic_validation_complete",
        "file_exists": (raw / "sanitation_osm_20261015T153228Z.json").exists(),
        "metadata_file_exists": (raw / "sanitation_osm_20261015T153228Z_metadata.json").exists(),
        "feature_count": 37,
        "matched_records": 37,
        "staged_file": "data/staging/category_ingestion/sanitation_ingested_20261015T160812Z.csv",
        "missing_names": 25,
        "invalid_coordinates": 0,
        "outside_approximate_bbox": 0,
        "duplicate_id_rows_within_category": 0
    },
    {
        "dataset_id": "emergency_services_osm_20261015T153401Z",
        "category": "emergency_services",
        "source": "OpenStreetMap",
        "source_url": "https://overpass-api.de/api/interpreter",
        "source_file": "data/raw/emergency_services_osm_20261015T153401Z.json",
        "metadata_file": "data/raw/emergency_services_osm_20261015T153401Z_metadata.json",
        "retrieved_at": "2026-10-15T15:34:01.017274+00:00",
        "license": "ODbL",
        "version": "local snapshot 2026-10-15",
        "status": "downloaded_staged_basic_validation_complete",
        "file_exists": (raw / "emergency_services_osm_20261015T153401Z.json").exists(),
        "metadata_file_exists": (raw / "emergency_services_osm_20261015T153401Z_metadata.json").exists(),
        "feature_count": 87,
        "matched_records": 87,
        "staged_file": "data/staging/category_ingestion/emergency_services_ingested_20261015T160812Z.csv",
        "missing_names": 32,
        "invalid_coordinates": 0,
        "outside_approximate_bbox": 0,
        "duplicate_id_rows_within_category": 0
    }
]

new_ids = {item["dataset_id"] for item in new_datasets}
datasets[:] = [d for d in datasets if d.get("dataset_id") not in new_ids]
datasets.extend(new_datasets)

manifest["planned_categories_without_verified_raw_datasets"] = [
    "transport_facilities"
]
manifest["last_updated_at_utc"] = datetime.now(timezone.utc).isoformat()
manifest["update_note"] = (
    "Five additional infrastructure categories were downloaded and staged. "
    "Transport query/retrieval time and education provenance remain unverified. "
    "Basic checks do not establish real-world uniqueness or operational status."
)

manifest_path.write_text(
    json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8"
)
print(f"Updated: {manifest_path}")
print("Raw data and staged CSVs were not modified.")
