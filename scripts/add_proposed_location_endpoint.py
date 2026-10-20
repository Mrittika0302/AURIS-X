from pathlib import Path

p = Path("frontend/backend/main.py")
source = p.read_text(encoding="utf-8")

if "/optimizer/evaluate-location" in source:
    raise SystemExit("Endpoint already exists; no changes made.")

if "import math\n" not in source:
    source = source.replace("import json\n", "import json\nimport math\n", 1)

marker = '@app.get("/optimizer/candidates")'
if marker not in source:
    raise SystemExit("Could not find optimizer candidates route; no changes made.")

endpoint = '''

@app.get("/optimizer/evaluate-location")
def optimizer_evaluate_location(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    infrastructure_type: str = Query("healthcare"),
):
    """Match a proposed coordinate to saved healthcare screening evidence."""
    if infrastructure_type != "healthcare":
        raise HTTPException(
            status_code=501,
            detail="Proposed-location evidence is currently available only for healthcare.",
        )

    candidates, comparison_path = load_candidate_comparison()
    if not candidates:
        raise HTTPException(status_code=503, detail="No candidate comparison rows available.")

    def haversine_m(lat1, lon1, lat2, lon2):
        radius_m = 6371000.0
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)
        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 2 * radius_m * math.asin(min(1.0, math.sqrt(a)))

    valid = []
    for row in candidates:
        try:
            lat = float(row.get("centroid_latitude", ""))
            lon = float(row.get("centroid_longitude", ""))
        except (TypeError, ValueError):
            continue
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            valid.append((haversine_m(latitude, longitude, lat, lon), row))

    if not valid:
        raise HTTPException(status_code=503, detail="No candidates have valid coordinates.")

    distance_m, candidate = min(valid, key=lambda item: item[0])
    zone_id = candidate.get("candidate_zone_id", "")

    impact_path = latest_report("candidate_impact_top10_*.csv")
    impact = None
    if impact_path:
        impact_rows = read_csv(impact_path)
        impact = next(
            (row for row in impact_rows if row.get("candidate_zone_id") == zone_id),
            None,
        )

    score = number(candidate, "screening_score", "priority_score")
    cost = number(candidate, "assumed_site_cost", "assumed_cost")

    impact_fields = [
        "driving_cells_improved_over_1m",
        "walking_cells_improved_over_1m",
        "driving_cells_moved_to_5km_or_less",
        "walking_cells_moved_to_5km_or_less",
        "driving_mean_reduction_among_baseline_reachable_m",
        "walking_mean_reduction_among_baseline_reachable_m",
        "drive_candidate_snap_m",
        "walk_candidate_snap_m",
        "simulation_scope",
        "population_raster_units_verified",
        "candidate_is_buildable_parcel",
        "travel_time_modelled",
        "facility_capacity_modelled",
    ]

    return {
        "status": "PASS",
        "infrastructure_type": infrastructure_type,
        "proposed_location": {
            "latitude": latitude,
            "longitude": longitude,
        },
        "matching_method": "Nearest candidate-zone centroid by straight-line haversine distance",
        "nearest_candidate": {
            "candidate_zone_id": zone_id,
            "latitude": float(candidate["centroid_latitude"]),
            "longitude": float(candidate["centroid_longitude"]),
            "distance_from_proposed_location_m": round(distance_m, 1),
            "screening_score": score,
            "score_type": candidate.get("score_type", "Screening score; interpretation depends on source data"),
            "assumed_site_cost": cost,
            "buildable_land_verified": candidate.get("buildable_land_verified"),
            "population_units_verified": candidate.get("population_units_verified"),
            "review_flags": candidate.get("review_flags", ""),
        },
        "saved_impact_evidence": (
            {key: impact.get(key) for key in impact_fields if key in impact}
            if impact else None
        ),
        "sources": {
            "candidate_comparison": comparison_path.name,
            "impact_report": impact_path.name if impact_path else None,
        },
        "limitations": [
            "This matches the coordinate to an existing candidate; it does not create a new site or rerun routing.",
            "Impact metrics describe the matched candidate's saved single-site simulation, not the exact proposed coordinate.",
            "Straight-line distance is not road-network travel distance.",
            "Raster cells are not verified people counts.",
            "Candidate centroids are not surveyed parcels; land availability and permissions are unverified.",
            "Individual candidate effects cannot be added to estimate a combined portfolio effect.",
        ],
    }

'''

backup = p.with_suffix(".py.before_location_endpoint.bak")
backup.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
p.write_text(source.replace(marker, endpoint + "\n" + marker, 1), encoding="utf-8")
print(f"Updated {p}; backup saved to {backup}")
