# AURIS-X — Infrastructure Category Interface Contract

Version: 1.1
Phase: 3 — Unified Infrastructure Platform
Status: Defined; implementation and dataset validation tracked separately

## 1. Contract shared by all categories

Every normalized facility record must map to the common schema in
`docs/COMMON_INFRASTRUCTURE_SCHEMA.md`.

Required common fields:
- facility_uid: stable, category-qualified identifier
- service_domain: canonical category value
- facility_category: source-supported subtype, or explicitly unknown
- facility_name: nullable; never fabricate
- source: provider or dataset
- license: source licence or explicitly documented unknown/pending status
- source_file: original source dataset identifier or filename
- review_flags: machine-readable quality flags

For OSM records, preserve osm_type and osm_id. For non-OSM sources,
preserve the original source identifier in an additional source-specific
field or provenance table. Do not manufacture OSM identifiers.

Coordinates:
- Point features use latitude and longitude in WGS84 decimal degrees.
- Validate latitude in [-90, 90] and longitude in [-180, 180].
- Missing or invalid coordinates require a review flag and exclusion from
  coordinate-based analysis.
- Preserve source geometry for lines and polygons in a geometry-capable
  output. Do not silently convert them to points.
- Any representative point or centroid must be identified as derived geometry.

Provenance for every imported dataset:
- dataset ID and category
- provider and source URL
- licence and attribution requirements
- retrieval timestamp and source data version/year, when available
- geographic coverage and CRS
- original filename and record count
- ingestion script/version and normalized output path
- validation result and known limitations

Unknown metadata must be recorded as unknown or pending verification.

## 2. Category interfaces

### 2.1 Transport

Canonical domain: `transport`

Supported feature types:
- Public transport stops and stations
- Bus terminals and interchanges
- Railway and metro stations where mapped
- Airports and other mapped transport terminals
- Road and transport-network features, stored as line/network geometry
  rather than forced into the point-facility table

Source attributes to preserve when available:
- source identifier and original tags
- transport mode
- stop/station/terminal subtype
- route or network identifiers
- operator and service status
- geometry type and access restrictions

Validation:
- A stop or station must have valid point geometry or a documented
  source-derived representative point.
- Route identifiers and modes must retain source provenance.
- Road segments must retain line geometry and must not be counted as
  individual facilities.
- Do not infer service frequency, operating status, or connectivity.

### 2.2 Parks and open spaces

Canonical domain: `parks`

Supported feature types:
- Parks and public gardens
- Playgrounds and recreation grounds
- Public green spaces and mapped nature reserves
- Sports and recreational areas, classified separately where possible

Source attributes to preserve when available:
- source identifier and original tags
- park/open-space subtype
- geometry type
- source-reported area and units
- access/public-use designation
- operator and operating status

Validation:
- Preserve polygon or multipolygon boundaries where supplied.
- Preserve point geometry for point-only source features.
- Validate polygon geometry and area units before using area measurements.
- Do not assume every green space is publicly accessible.
- Do not replace a polygon with its centroid without recording that
  transformation.

### 2.3 Water infrastructure

Canonical domain: `water`

Supported feature types:
- Public drinking-water points
- Water towers and reservoirs
- Water-treatment and water-supply works
- Mapped water-distribution infrastructure, stored using its native
  line or polygon geometry where available

Source attributes to preserve when available:
- source identifier and original tags
- water facility subtype
- water source or system identifier
- operator
- access and operational status
- geometry type and source-reported capacity, with units

Validation:
- Distinguish drinking-water access points from supply infrastructure.
- Preserve line and polygon geometry for networks and sites.
- Capacity and water quality must remain unknown unless supported by data.
- Do not infer that a mapped feature is functional or supplies a
  particular population.

### 2.4 Sanitation

Canonical domain: `sanitation`

Supported feature types:
- Public toilets
- Wastewater-treatment plants
- Sewage pumping stations
- Mapped sewer and wastewater-network infrastructure

Source attributes to preserve when available:
- source identifier and original tags
- sanitation subtype
- public access and accessibility attributes
- operator and operating status
- network/site geometry
- source-reported capacity and units

Validation:
- Distinguish public toilets from wastewater and sewer infrastructure.
- Preserve network and site geometry.
- Do not infer accessibility, working condition, treatment capacity,
  or population served without supporting evidence.
- Missing operational or access status must remain unknown.

### 2.5 Emergency services

Canonical domain: `emergency_services`

Supported feature types:
- Fire stations
- Ambulance stations or verified ambulance facilities
- Police stations and other explicitly mapped emergency-response facilities

Source attributes to preserve when available:
- source identifier and original tags
- emergency-service subtype
- operator
- verified contact details
- operational status and service hours
- geometry and access information

Validation:
- Distinguish emergency-response facilities from unrelated offices
  or general healthcare facilities.
- Do not treat an ordinary clinic as an ambulance station without evidence.
- Contacts and operating status require a source and verification date.
- Do not infer response times, staffing, readiness, or service coverage.

## 3. Shared adapter interface

Each category adapter must:
1. Accept a source file and an explicit category.
2. Preserve the raw input unchanged.
3. retain original identifiers and source attributes needed for audit.
4. Map common fields and category-specific attributes.
5. validate identifiers, coordinate ranges, geometry and required provenance.
6. Detect duplicate source identities and flag them before deduplication.
7. Flag missing names, invalid coordinates, unknown subtypes and
   unsupported geometry.
8. Write normalized data and a machine-readable validation report to
   versioned output locations.
9. Record input/output counts, exclusions, duplicates and review counts.
10. Never overwrite frozen healthcare or education outputs.

## 4. Shared selection and filtering contract

The future API must support:
- One or more canonical service domains
- Optional category subtype filters
- Text search when a searchable field exists
- Geographic bounding-box filters
- Review-only selection
- Bounded pagination with total matching count
- Consistent common-schema response fields
- Explicit validation errors for invalid domains, bounds and parameters

Bounding boxes must be validated for legal coordinate ranges and
min/max ordering. They remain rectangular filters, not official
administrative boundaries.

## 5. Cross-category compatibility

Before comparing categories, record:
- study-area boundary source and version
- geographic coverage and CRS
- source retrieval date and source data year
- population dataset, reference year, units and resolution
- category-specific exclusions and known coverage gaps

Do not equate facility count with service capacity, access, quality,
population coverage or need. Report differences in coverage explicitly.

## 6. Module 3 acceptance criteria

- [x] Five category interfaces defined.
- [x] Common fields and category-specific extensions specified.
- [x] Point, line and polygon handling specified.
- [x] Provenance and licensing requirements specified.
- [x] Category-specific validation requirements specified.
- [ ] Interface implementation verified by ingestion tests.
- [ ] Each category has a real source dataset and validation report.
- [ ] Shared API supports all integrated categories.

The unchecked criteria belong to implementation and data collection;
this document alone does not certify those tasks as complete.
