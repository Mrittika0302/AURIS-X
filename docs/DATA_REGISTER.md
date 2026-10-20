# AURIS-X — Dataset Register

**Working study area:** Coimbatore, Tamil Nadu, India
**Current spatial extent:** Approximate bounding box: south 10.85, west 76.85, north 11.15, east 77.15. This is not an official administrative boundary.

## 1. Healthcare facilities

- Source: OpenStreetMap via Overpass API
- Endpoint: https://overpass-api.de/api/interpreter
- Raw file: `data/raw/healthcare_osm_20261011_112504.json`
- Metadata file: `data/raw/healthcare_osm_20261011_112504_metadata.json`
- Retrieved: 2026-10-11 11:25:06 +05:30
- Raw element count: 396
- Queried tags: `amenity=hospital`, `amenity=clinic`, `amenity=doctors`
- License: Open Database License (ODbL); attribution to © OpenStreetMap contributors
- Status: Downloaded; raw metadata available; earlier healthcare analysis outputs are frozen.
- Limitations: Approximate bounding box; OSM may be incomplete or contain duplicates; query covers only the listed amenity values.

## 2. Education facilities

- Source: OpenStreetMap; exact query and retrieval metadata: pending verification.
- Raw file: `data/raw/education_osm_20261013T085408Z.json`
- Raw element count: 415, as reported by the ingestion/validation run.
- License and attribution: Verify against the original retrieval metadata and source workflow.
- Status: Downloaded and processed; existing education analysis is frozen.
- Reconciliation required: generic ingestion matched 401 records, whereas the existing raw/validation workflow reports 415. Do not replace frozen outputs until the discrepancy is explained.

## 3. Driving road network

- Source: OpenStreetMap via OSMnx
- Source URL: https://www.openstreetmap.org/
- Raw file: `data/raw/roads_osm_20261011_115925.graphml`
- Metadata file: `data/raw/roads_osm_20261011_115925_metadata.json`
- Retrieved: 2026-10-11 06:30:38 UTC
- Network type: Drive
- Nodes: 84,306
- Edges: 211,237
- License: ODbL; verify attribution requirements
- Status: Downloaded; topology, connectivity, and travel-time assumptions require validation.
- Limitations: Approximate bounding box; drive network does not represent walking access.

## 4. Walking road network

- Raw files reported:
  - `data/raw/roads_walking_osm_20261011_120504.graphml`
  - `data/raw/roads_walking_osm_20261011_122708.graphml`
- Status: Files present; retrieval metadata, relationship between versions, and validation status require verification.

## 5. Population

- File: `data/population/coimbatore_population_2026_approx.tif`
- Status: File present; source provider, population reference year, CRS, pixel resolution, NoData handling, and licensing are not yet verified.
- Candidate source previously recorded: WorldPop, https://hub.worldpop.org/geodata/
- Important: The candidate source is not proof that this raster came from WorldPop. Do not assert provenance until verified.

## 6. Administrative boundary

- Candidate source: Coimbatore Local Planning Authority, https://coimbatorelpa.in/downloads/
- Alternative: official government boundary datasets.
- Status: Official study-area boundary not yet verified. Determine whether the intended geography is the city corporation, urban agglomeration, or planning area before cross-category comparisons.

## 7. Additional infrastructure categories

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

## Data governance

1. Preserve original downloads without editing them.
2. Record source, retrieval date, license, data year, geographic coverage, and processing steps.
3. Do not invent facility capacity, land availability, travel speeds, or costs.
4. Distinguish observed facts from assumptions and modeled estimates.
5. Do not mark a source validated until the actual data has been inspected.
6. Preserve frozen healthcare and education analytical outputs.
7. Version derived outputs and retain validation reports.
