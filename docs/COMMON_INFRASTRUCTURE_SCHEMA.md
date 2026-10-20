# AURIS-X Common Infrastructure Schema
Version: 1.0
Study area: Coimbatore, Tamil Nadu, India (working designation)

## Purpose
Define a common record contract for healthcare, education, transport,
parks, water, sanitation, and emergency services.

## Common facility fields

| Field | Meaning | Rule |
|---|---|---|
| facility_uid | Stable category-qualified record identifier | Required; unique within the unified inventory |
| service_domain | Canonical service category | Required; use a controlled category value |
| osm_type | OpenStreetMap element type | Required when sourced from OSM |
| osm_id | OpenStreetMap element identifier | Required when sourced from OSM |
| facility_name | Display name | Nullable; do not invent missing names |
| facility_category | Category-specific facility type | Nullable only when source cannot classify it |
| latitude | WGS84 latitude in decimal degrees | Nullable only with an explicit quality flag |
| longitude | WGS84 longitude in decimal degrees | Nullable only with an explicit quality flag |
| source | Source dataset/provider | Required |
| source_url | Source record or dataset reference | Nullable if unavailable; document why |
| license | Source license or documented licensing status | Required provenance field |
| source_file | Original source filename or dataset identifier | Required |
| review_flags | Machine-readable quality/review flags | Empty when no review is required |

## Canonical service domains
- healthcare
- education
- transport
- parks
- water
- sanitation
- emergency_services

## Validation rules
1. Each facility_uid must be non-empty and unique in the combined inventory.
2. service_domain must be one of the canonical domains above.
3. Coordinates must be numeric and within latitude [-90, 90] and longitude [-180, 180].
4. Missing names must be flagged, not fabricated.
5. Missing coordinates must be flagged; such records must not be used in spatial analysis.
6. Preserve source identifiers and provenance.
7. Duplicate source identities must be reported for review before deduplication.
8. Do not infer capacity, service coverage, costs, land availability, or operating status without evidence.
9. Keep raw downloads immutable and write normalized outputs to separate locations.
10. Keep frozen healthcare and education analytical outputs unchanged.

## Geometry and network fields
Point coordinates are the common minimum for point facilities. Lines and polygons
must be preserved in an appropriate geometry-capable dataset when the source
contains them; do not reduce park boundaries or transport networks to points
without an explicit derived representation. Network matches and snap distances
are optional, mode-specific attributes and must not be confused with facility
coordinates.

## Geographic and population compatibility
Record the study-area boundary/version, coordinate reference system, source date,
population dataset/year, spatial resolution, and any coverage differences.
Do not assume categories are comparable until those definitions are verified.

## Source registry and version manifest
For every dataset, record: dataset ID, category, provider, source URL, license,
retrieval date, source year/version, geographic coverage, original filename,
record count, processing script/version, output path, and validation status.
Unknown metadata must be marked unknown, not guessed.

## Compatibility policy
Category-specific fields may be added without changing the meaning of common
fields. Schema changes must be versioned and tested against all integrated
categories before release.
