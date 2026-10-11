# AURIS-X — Dataset Register

**Study area:** Coimbatore, Tamil Nadu, India  
**Purpose:** Track data sources and verify suitability before analysis.

## 1. Healthcare facilities

- Candidate source: OpenStreetMap (OSM)
- Website: https://www.openstreetmap.org/
- Required fields: facility name, facility type, latitude, longitude, source identifier
- Validation: coordinate validity, duplicates, missing names/types, study-area coverage
- Status: Not yet downloaded or validated

## 2. Population

- Candidate source: WorldPop data portal
- Website: https://hub.worldpop.org/geodata/
- Required fields: population values, geographic coordinates or raster grid, year, spatial resolution
- Validation: geographic coverage, year, resolution, licensing, missing or invalid values
- Status: Not yet downloaded or validated

## 3. Road network

- Candidate source: OpenStreetMap
- Website: https://www.openstreetmap.org/
- Possible processing tool: OSMnx — https://osmnx.readthedocs.io/en/stable/
- Required fields: connected road network, road geometry, road type
- Validation: study-area coverage, connectivity, disconnected components, data date
- Status: Not yet downloaded or validated

## 4. Administrative boundary

- Candidate source: Coimbatore Local Planning Authority
- Website: https://coimbatorelpa.in/downloads/
- Alternative source to investigate: official government boundary datasets
- Required fields: boundary geometry, name, source, geographic scope
- Validation: confirm whether the boundary represents the city corporation, urban agglomeration, or planning area
- Status: Not yet downloaded or validated

## Data governance rules

1. Preserve original downloads without editing them.
2. Record the download date, source URL, license, data year and processing steps.
3. Do not invent missing facility capacity, land availability, travel speeds or costs.
4. Label assumptions and modeled estimates separately from observed facts.
5. Do not treat a candidate source as validated until its actual data has been inspected.