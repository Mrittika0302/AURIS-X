import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query

ROOT = Path(__file__).resolve().parents[2]
GOLD_DIR = ROOT / "data" / "gold"
CATEGORY_DIR = ROOT / "data" / "staging" / "category_ingestion"
REPORT_DIR = ROOT / "reports"

Domain = Literal[
    "healthcare", "education", "transport", "parks", "water",
    "sanitation", "emergency_services",
]
LEGACY_DOMAINS = {"healthcare", "education"}
CATEGORY_DOMAINS = {
    "transport", "parks", "water", "sanitation", "emergency_services"
}
ALL_DOMAINS = LEGACY_DOMAINS | CATEGORY_DOMAINS

app = FastAPI(
    title="AURIS-X API",
    description=(
        "Read-only API for infrastructure inventories and screening-level "
        "candidate-site evaluation."
    ),
    version="0.3.0",
)


def latest_inventory() -> Path | None:
    files = sorted(
        GOLD_DIR.glob("unified_facility_inventory_*.csv"),
        key=lambda path: path.name, reverse=True,
    )
    return files[0] if files else None


def latest_category_file(domain: str) -> Path | None:
    files = sorted(
        CATEGORY_DIR.glob(f"{domain}_ingested_*.csv"),
        key=lambda path: path.name, reverse=True,
    )
    return files[0] if files else None


def latest_report(pattern: str) -> Path | None:
    files = sorted(REPORT_DIR.glob(pattern), key=lambda p: p.name, reverse=True)
    return files[0] if files else None


def read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    except (OSError, csv.Error) as exc:
        raise HTTPException(
            status_code=503, detail=f"Could not read {path.name}: {exc}"
        ) from exc


def load_inventory() -> tuple[list[dict[str, str]], Path]:
    path = latest_inventory()
    if path is None:
        raise HTTPException(
            status_code=503, detail="No unified facility inventory is available."
        )
    return read_csv(path), path


def load_category_rows(
    domains: set[str] | None = None,
) -> tuple[list[dict[str, str]], dict[str, str]]:
    selected = domains if domains is not None else CATEGORY_DOMAINS
    rows: list[dict[str, str]] = []
    files: dict[str, str] = {}
    for domain in sorted(selected):
        path = latest_category_file(domain)
        if path is not None:
            rows.extend(read_csv(path))
            files[domain] = path.name
    return rows, files


def inside_bounding_box(
    row: dict[str, str], min_lat: float, max_lat: float,
    min_lon: float, max_lon: float,
) -> bool:
    try:
        lat = float(row.get("latitude", ""))
        lon = float(row.get("longitude", ""))
    except (TypeError, ValueError):
        return False
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return False
    return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon


def split_flags(row: dict[str, str]) -> list[str]:
    return [flag.strip() for flag in row.get("review_flags", "").split(";") if flag.strip()]


def count_domains(rows: list[dict[str, str]]) -> dict[str, int]:
    return dict(sorted(Counter(row.get("service_domain", "") for row in rows).items()))


def number(row: dict[str, str], *keys: str) -> float | None:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            try:
                result = float(value)
                if result == result and abs(result) != float("inf"):
                    return result
            except (TypeError, ValueError):
                pass
    return None


def load_candidate_comparison() -> tuple[list[dict[str, str]], Path]:
    path = latest_report("phase4_candidate_comparison_*.csv")
    if path is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "No Phase 4 comparison CSV found. Run "
                "scripts/evaluate_phase4_portfolios.py first."
            ),
        )
    return read_csv(path), path


@app.get("/")
def root():
    return {
        "project": "AURIS-X",
        "api_version": app.version,
        "docs": "/docs",
        "endpoints": [
            "/health", "/summary", "/facilities",
            "/optimizer/candidates", "/optimizer/portfolio",
        ],
        "supported_domains": sorted(ALL_DOMAINS),
        "default_scope": "healthcare and education for backward compatibility",
    }


@app.get("/health")
def health():
    path = latest_inventory()
    category_files = {
        domain: category_path.name
        for domain in sorted(CATEGORY_DOMAINS)
        if (category_path := latest_category_file(domain)) is not None
    }
    comparison = latest_report("phase4_candidate_comparison_*.csv")
    return {
        "status": "ok",
        "inventory_available": path is not None,
        "inventory_file": path.name if path else None,
        "category_files": category_files,
        "available_category_count": len(category_files),
        "candidate_comparison_available": comparison is not None,
        "candidate_comparison_file": comparison.name if comparison else None,
    }


@app.get("/summary")
def summary():
    rows, path = load_inventory()
    domain_counts = Counter(row.get("service_domain", "") for row in rows)
    flagged_rows = [row for row in rows if split_flags(row)]
    flag_counts = Counter(
        (row.get("service_domain", ""), flag)
        for row in rows for flag in split_flags(row)
    )
    category_rows, category_files = load_category_rows()
    combined_rows = rows + category_rows
    return {
        "inventory_file": path.name,
        "total_records": len(rows),
        "records_by_domain": dict(sorted(domain_counts.items())),
        "records_with_review_flags": len(flagged_rows),
        "records_without_names": sum(not row.get("facility_name", "").strip() for row in rows),
        "review_flags_by_domain": [
            {"service_domain": domain, "flag": flag, "count": count}
            for (domain, flag), count in sorted(flag_counts.items())
        ],
        "combined_total_records": len(combined_rows),
        "combined_records_by_domain": count_domains(combined_rows),
        "category_files": category_files,
        "category_records_without_names": sum(
            not row.get("facility_name", "").strip() for row in category_rows
        ),
        "limitations": [
            "The original summary fields describe healthcare and education only.",
            "Combined statistics include the latest available staged category CSVs.",
            "Missing category files are omitted from the combined statistics.",
            "Review flags indicate records requiring inspection; they do not prove invalidity.",
            "Network snap distance is not travel time.",
            "Facility capacity, buildable land, and construction cost are not inferred.",
            "Candidate evaluation uses saved screening outputs and does not recalculate network accessibility.",
            "Some OSM ways and relations are represented by a point or center; native geometry is not preserved in these CSVs.",
        ],
    }


@app.get("/facilities")
def facilities(
    domain: Domain | None = None,
    domains: list[Domain] | None = Query(default=None),
    q: str | None = Query(default=None, max_length=120),
    review_only: bool = False,
    min_lat: float | None = Query(default=None, ge=-90, le=90),
    max_lat: float | None = Query(default=None, ge=-90, le=90),
    min_lon: float | None = Query(default=None, ge=-180, le=180),
    max_lon: float | None = Query(default=None, ge=-180, le=180),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    if domain is not None and domains is not None:
        raise HTTPException(status_code=400, detail="Use either 'domain' or 'domains', not both.")
    if domain is None and domains is None:
        selected_domains = LEGACY_DOMAINS
    elif domain is not None:
        selected_domains = {domain}
    else:
        selected_domains = set(domains or [])

    rows: list[dict[str, str]] = []
    inventory_path: Path | None = None
    category_files: dict[str, str] = {}
    selected_legacy = selected_domains & LEGACY_DOMAINS
    selected_categories = selected_domains & CATEGORY_DOMAINS

    if selected_legacy:
        legacy_rows, inventory_path = load_inventory()
        rows.extend(row for row in legacy_rows if row.get("service_domain") in selected_legacy)
    if selected_categories:
        category_rows, category_files = load_category_rows(selected_categories)
        rows.extend(category_rows)

    if q:
        term = q.casefold()
        searchable_fields = ("facility_name", "facility_category", "osm_id", "facility_uid")
        rows = [
            row for row in rows
            if any(term in row.get(field, "").casefold() for field in searchable_fields)
        ]
    if review_only:
        rows = [row for row in rows if split_flags(row)]

    coordinates = (min_lat, max_lat, min_lon, max_lon)
    if any(value is not None for value in coordinates):
        if any(value is None for value in coordinates):
            raise HTTPException(
                status_code=400,
                detail="Provide all four parameters: min_lat, max_lat, min_lon, max_lon.",
            )
        if min_lat > max_lat or min_lon > max_lon:
            raise HTTPException(
                status_code=400,
                detail="Minimum coordinates must not exceed maximum coordinates.",
            )
        rows = [
            row for row in rows
            if inside_bounding_box(row, min_lat, max_lat, min_lon, max_lon)
        ]

    total = len(rows)
    return {
        "inventory_file": inventory_path.name if inventory_path else None,
        "category_files": category_files,
        "selected_domains": sorted(selected_domains),
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": rows[offset:offset + limit],
    }




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
            lat = float(row.get("centroid_latitude") or row.get("latitude") or "")
            lon = float(row.get("centroid_longitude") or row.get("longitude") or "")
        except (TypeError, ValueError):
            continue
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            valid.append((haversine_m(latitude, longitude, lat, lon), row))

    if not valid:
        raise HTTPException(status_code=503, detail="No candidates have valid coordinates.")

    distance_m, candidate = min(valid, key=lambda item: item[0])
    zone_id = candidate.get("candidate_zone_id", "")

    preferred_impact = REPORT_DIR / "candidate_impact_top10_20261012.csv"
    if preferred_impact.exists():
        impact_path = preferred_impact
    else:
        impact_files = sorted(
            (
                f for f in REPORT_DIR.glob("candidate_impact_top10_*.csv")
                if "audit" not in f.stem.casefold()
            ),
            key=lambda f: f.name,
            reverse=True,
        )
        impact_path = impact_files[0] if impact_files else None
    impact = None
    if impact_path:
        impact_rows = read_csv(impact_path)
        impact = next(
            (row for row in impact_rows if row.get("candidate_zone_id") == zone_id),
            None,
        )
    if impact is None:
        # The comparison CSV already contains saved single-site impact evidence.
        impact = candidate

    score = number(candidate, "screening_score", "priority_score")
    cost = number(candidate, "assumed_site_cost", "assumed_cost", "cost")

    impact_fields = [
        "driving_cells_improved_over_1m",
        "walking_cells_improved_over_1m",
        "driving_cells_moved_to_5km_or_less",
        "walking_cells_moved_to_5km_or_less",
        "driving_mean_reduction_among_baseline_reachable_m",
        "walking_mean_reduction_among_baseline_reachable_m",
        "driving_mean_distance_reduction_m",
        "walking_mean_distance_reduction_m",
        "drive_snap_m",
        "walk_snap_m",
        "snap_review",
        "pros",
        "cons",
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
            "latitude": float(candidate.get("centroid_latitude") or candidate.get("latitude")),
            "longitude": float(candidate.get("centroid_longitude") or candidate.get("longitude")),
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




@app.get("/optimizer/simulate-location")
def simulate_location(latitude: float, longitude: float):
    """Run a fresh healthcare driving/walking network-distance simulation."""
    import json
    import subprocess
    import sys
    from pathlib import Path

    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise HTTPException(status_code=422, detail="Invalid latitude or longitude.")

    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "evaluate_proposed_healthcare_location.py"
    if not script.exists():
        raise HTTPException(status_code=500, detail="Simulation script not found.")

    try:
        result = subprocess.run(
            [
                sys.executable, str(script),
                "--latitude", str(latitude),
                "--longitude", str(longitude),
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Simulation exceeded the 10-minute API timeout.")

    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Fresh accessibility simulation failed.",
                "stderr": result.stderr[-4000:],
                "stdout": result.stdout[-2000:],
            },
        )

    try:
        start = result.stdout.find("{")
        if start < 0:
            raise ValueError("No JSON report found in simulation output.")
        report, _ = json.JSONDecoder().raw_decode(result.stdout[start:])
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=f"Could not parse simulation report: {exc}")

    return report



@app.get("/optimizer/scoring")
def optimizer_scoring(limit: int = 20, offset: int = 0):
    """Return the latest saved transparent candidate scoring breakdown."""
    import json
    from pathlib import Path
    import pandas as pd
    from fastapi import HTTPException

    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 100.")
    if offset < 0:
        raise HTTPException(status_code=422, detail="offset must be zero or greater.")

    root = Path(__file__).resolve().parents[2]
    reports = root / "reports"
    files = sorted(
        reports.glob("phase4_transparent_scoring_*.csv"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise HTTPException(
            status_code=404,
            detail="No transparent scoring report found. Run scripts/generate_phase4_transparent_scoring.py first.",
        )

    csv_path = files[0]
    json_path = csv_path.with_suffix(".json")
    try:
        df = pd.read_csv(csv_path)
        metadata = json.loads(json_path.read_text(encoding="utf-8")) if json_path.exists() else {}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read scoring report: {exc}")

    total = len(df)
    page = df.iloc[offset:offset + limit].copy()
    page = page.astype(object).where(pd.notna(page), None)

    return {
        "status": "PASS",
        "source_file": csv_path.name,
        "metadata": metadata,
        "total_candidates": total,
        "limit": limit,
        "offset": offset,
        "candidates": page.to_dict(orient="records"),
        "interpretation": [
            "Scores are relative heuristic screening scores, not validated probabilities or incremental public benefit.",
            "Component contributions explain the saved score; they do not prove causal effects.",
            "Missing saved impact evidence is not equivalent to zero impact.",
            "Population units and buildable land remain unverified unless independently established.",
        ],
    }



@app.get("/optimizer/cost-scenarios")
def optimizer_cost_scenarios(
    budget: float,
    cost_per_site: list[float] = Query(...),
):
    """Compare caller-supplied per-site cost assumptions with a budget."""
    import math
    from pathlib import Path
    import pandas as pd
    from fastapi import HTTPException

    if not math.isfinite(budget) or budget < 0:
        raise HTTPException(status_code=422, detail="budget must be a finite non-negative number.")
    if not cost_per_site:
        raise HTTPException(status_code=422, detail="Supply at least one cost_per_site value.")
    if any(not math.isfinite(cost) or cost <= 0 for cost in cost_per_site):
        raise HTTPException(status_code=422, detail="Each cost_per_site must be finite and greater than zero.")

    root = Path(__file__).resolve().parents[2]
    candidate_file = root / "data" / "gold" / "healthcare_candidate_sites.csv"
    if not candidate_file.exists():
        raise HTTPException(status_code=404, detail="Healthcare candidate file not found.")

    try:
        candidates = pd.read_csv(candidate_file)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read candidates: {exc}")

    candidate_count = len(candidates)
    scenarios = []
    for cost in cost_per_site:
        affordable = int(math.floor((budget + 1e-9) / cost))
        scenarios.append({
            "assumed_cost_per_site": cost,
            "budget": budget,
            "theoretical_affordable_site_count": affordable,
            "candidate_limited_site_count": min(affordable, candidate_count),
            "assumed_cost_for_candidate_limited_count": round(min(affordable, candidate_count) * cost, 2),
            "remaining_budget_after_that_count": round(budget - min(affordable, candidate_count) * cost, 2),
            "cost_is_verified": False,
            "cost_source": "caller_supplied_assumption",
            "evidence_used_for_per_site_cost": False,
            "construction_cost_verified": False,
            "operating_cost_included": False,
            "lifecycle_cost_included": False,
        })

    return {
        "status": "PASS",
        "currency": "INR assumed by current project convention; confirm before financial use",
        "candidate_count": candidate_count,
        "budget": budget,
        "scenario_cost_semantics": {
            "costs_are_user_supplied_assumptions": True,
            "official_evidence_register_used_as_site_cost": False,
            "verified_per_site_cost_available": False,
            "note": "Official budget and tender records are reference evidence only. None is approved as a comparable per-site construction cost.",
        },
        "scenarios": scenarios,
        "limitations": [
            "Per-site costs are supplied by the caller and are not verified estimates.",
            "The calculation is arithmetic affordability only; it does not select or validate sites.",
            "Land acquisition, surveys, permits, equipment, staffing, operations, maintenance, inflation, and lifecycle costs are excluded unless included in the supplied per-site assumption.",
            "Buildable land and population units remain unverified.",
            "Affordable site count does not establish that the sites are feasible or that their individual impacts add together.",
        ],
    }



@app.get("/optimizer/simulate-portfolio")
def optimizer_simulate_portfolio(site_ids: str):
    """Run joint accessibility simulation for selected healthcare candidate sites."""
    import json
    import subprocess
    import sys
    from pathlib import Path
    from fastapi import HTTPException

    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "evaluate_healthcare_portfolio.py"
    if not script.exists():
        raise HTTPException(status_code=404, detail="Portfolio simulation script not found.")

    ids = [item.strip() for item in site_ids.split(",") if item.strip()]
    if not ids:
        raise HTTPException(status_code=422, detail="Supply comma-separated site_ids.")
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=422, detail="Duplicate site IDs are not allowed.")
    if len(ids) > 100:
        raise HTTPException(status_code=422, detail="At most 100 site IDs may be simulated.")

    try:
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--site-ids",
                ",".join(ids),
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Portfolio simulation exceeded 600 seconds.")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not launch simulation: {exc}")

    if result.returncode != 0:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Portfolio simulation failed.",
                "stderr": result.stderr[-5000:],
                "stdout": result.stdout[-2000:],
            },
        )

    try:
        payload = json.loads(result.stdout)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Simulation did not return valid JSON.",
                "stdout": result.stdout[-3000:],
                "stderr": result.stderr[-3000:],
            },
        )

    if payload.get("status") != "PASS":
        raise HTTPException(status_code=500, detail="Simulation did not report PASS.")
    return payload



@app.get("/optimizer/cost-evidence")
def optimizer_cost_evidence(
    infrastructure_type: str | None = None,
    cost_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """Return sourced cost evidence with explicit scope and verification status."""
    import csv
    from pathlib import Path
    from fastapi import HTTPException

    if limit < 1 or limit > 500:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 500.")
    if offset < 0:
        raise HTTPException(status_code=422, detail="offset must be non-negative.")

    root = Path(__file__).resolve().parents[2]
    register = root / "data" / "reference_cost_evidence" / "phase4_cost_evidence_register.csv"
    if not register.exists():
        raise HTTPException(
            status_code=404,
            detail="Evidence register not found. Run scripts/build_phase4_evidence_register.py first.",
        )

    try:
        with register.open("r", encoding="utf-8-sig", newline="") as f:
            records = list(csv.DictReader(f))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read evidence register: {exc}")

    if infrastructure_type:
        records = [
            r for r in records
            if r.get("infrastructure_type", "").casefold() == infrastructure_type.casefold()
        ]
    if cost_type:
        records = [
            r for r in records
            if r.get("cost_type", "").casefold() == cost_type.casefold()
        ]

    for record in records:
        raw_amount = record.get("amount_inr", "")
        try:
            record["amount_inr"] = float(raw_amount) if raw_amount else None
        except (TypeError, ValueError):
            record["amount_inr"] = None
        record["usable_as_per_site_cost"] = (
            str(record.get("usable_as_per_site_cost", "")).casefold() == "true"
        )

    total = len(records)
    return {
        "status": "PASS",
        "total_matching_records": total,
        "limit": limit,
        "offset": offset,
        "records": records[offset:offset + limit],
        "interpretation": {
            "annual_budget_category": "Official budget allocation/category; not a per-site cost.",
            "tender_estimate": "Tender-level estimate for the stated project scope; not necessarily awarded or final expenditure.",
            "staffing_service_tender_estimate": "Operating/service scope; do not treat as construction cost.",
            "usable_as_per_site_cost": "Only true when explicitly approved after comparability and provenance review.",
        },
        "limitations": [
            "An official source does not make a figure comparable to every proposed facility.",
            "Tender estimates may differ from awarded contract values and final expenditure.",
            "Operating and construction costs must remain separate.",
            "The initial register contains no approved verified per-site construction costs.",
        ],
    }



@app.get("/optimizer/site-evidence")
def optimizer_site_evidence(candidate_zone_id: str):
    """Combine a candidate's score, saved impact evidence, costs, and verification flags."""
    import csv
    import math
    from pathlib import Path
    import pandas as pd
    from fastapi import HTTPException

    candidate_zone_id = candidate_zone_id.strip()
    if not candidate_zone_id:
        raise HTTPException(status_code=422, detail="candidate_zone_id must not be empty.")

    root = Path(__file__).resolve().parents[2]
    candidates_path = root / "data" / "gold" / "healthcare_candidate_sites.csv"
    evidence_path = root / "data" / "reference_cost_evidence" / "phase4_cost_evidence_register.csv"
    scoring_files = sorted(
        (root / "reports").glob("phase4_transparent_scoring_*.csv"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )

    if not candidates_path.exists():
        raise HTTPException(status_code=404, detail="Healthcare candidate file not found.")

    try:
        candidates = pd.read_csv(candidates_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read candidates: {exc}")

    if "candidate_zone_id" not in candidates.columns:
        raise HTTPException(status_code=500, detail="Candidate ID column is missing.")

    matched = candidates[
        candidates["candidate_zone_id"].astype(str) == candidate_zone_id
    ]
    if matched.empty:
        raise HTTPException(status_code=404, detail=f"Unknown candidate_zone_id: {candidate_zone_id}")

    def clean(value):
        if value is None:
            return None
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass
        if hasattr(value, "item"):
            try:
                value = value.item()
            except Exception:
                pass
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value

    candidate = {key: clean(value) for key, value in matched.iloc[0].to_dict().items()}

    score = None
    score_source = None
    if scoring_files:
        try:
            scored = pd.read_csv(scoring_files[0])
            if "candidate_zone_id" in scored.columns:
                rows = scored[
                    scored["candidate_zone_id"].astype(str) == candidate_zone_id
                ]
                if not rows.empty:
                    score = {key: clean(value) for key, value in rows.iloc[0].to_dict().items()}
                    score_source = str(scoring_files[0].relative_to(root))
        except Exception:
            score = None

    cost_evidence = []
    if evidence_path.exists():
        try:
            with evidence_path.open("r", encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    if row.get("infrastructure_type", "").casefold() in {
                        "healthcare", "healthcare_operations"
                    }:
                        try:
                            row["amount_inr"] = float(row["amount_inr"])
                        except (ValueError, TypeError):
                            row["amount_inr"] = None
                        row["usable_as_per_site_cost"] = (
                            row.get("usable_as_per_site_cost", "").casefold() == "true"
                        )
                        cost_evidence.append(row)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Could not read cost evidence: {exc}")

    flags = {
        "candidate_is_verified_buildable_parcel": False,
        "population_units_verified": False,
        "site_cost_verified": False,
        "authoritative_study_boundary_verified": False,
        "score_is_heuristic_not_validated_outcome_probability": True,
        "impact_metrics_are_candidate_specific_when_present": True,
    }

    impact = {}
    if score:
        for key, value in score.items():
            if any(token in key.casefold() for token in (
                "driving_cells", "walking_cells", "mean_reduction",
                "simulation_scope", "population_units", "candidate_is_buildable"
            )):
                impact[key] = value

    return {
        "status": "PASS",
        "candidate_zone_id": candidate_zone_id,
        "infrastructure_type": "healthcare",
        "candidate": candidate,
        "transparent_score": score,
        "score_source": score_source,
        "saved_impact_evidence": impact or None,
        "cost_evidence": cost_evidence,
        "cost_evidence_note": (
            "These are relevant reference records, not verified costs for this candidate. "
            "Do not use corporation-wide budgets or existing-facility improvements as a new-site cost."
        ),
        "verification_flags": flags,
        "limitations": [
            "Candidate coordinates are generated zone centroids, not verified parcels.",
            "The score is a relative screening heuristic, not a probability of success or proven benefit.",
            "Saved single-site impacts, when present, describe that candidate's simulation and must not be added across sites.",
            "Population raster units remain unverified; grid cells must not be described as people.",
            "Cost references have different scopes and are not approved per-site construction estimates.",
            "Land ownership, zoning, buildability, facility capacity, travel time, and operating lifecycle costs are not verified by this endpoint.",
            "A PASS status means the evidence response was assembled successfully, not that the site is approved or feasible.",
        ],
    }



@app.get("/optimizer/site-verification")
def optimizer_site_verification(
    candidate_zone_id: str | None = None,
    verification_status: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """Read candidate parcel verification records."""
    from pathlib import Path
    import pandas as pd
    from fastapi import HTTPException

    if limit < 1 or limit > 500:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 500.")
    if offset < 0:
        raise HTTPException(status_code=422, detail="offset must be non-negative.")

    root = Path(__file__).resolve().parents[2]
    path = root / "data" / "reference_site_evidence" / "healthcare_candidate_site_verification_register.csv"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Verification register not found.")

    try:
        df = pd.read_csv(path, keep_default_na=False)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read verification register: {exc}")

    if candidate_zone_id:
        df = df[df["candidate_zone_id"].astype(str) == candidate_zone_id.strip()]
    if verification_status:
        df = df[df["verification_status"].astype(str).str.casefold() == verification_status.casefold()]

    total = len(df)
    records = df.iloc[offset:offset + limit].to_dict(orient="records")
    return {
        "status": "PASS",
        "total_matching_records": total,
        "limit": limit,
        "offset": offset,
        "records": records,
        "note": "A model-generated centroid is not proof of a parcel or buildable land.",
    }




@app.get("/optimizer/site-verification/summary")
def optimizer_site_verification_summary():
    """Summarize parcel verification progress and missing checks."""
    from pathlib import Path
    import pandas as pd
    from fastapi import HTTPException

    root = Path(__file__).resolve().parents[2]
    path = root / "data" / "reference_site_evidence" / "healthcare_candidate_site_verification_register.csv"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Verification register not found.")

    try:
        df = pd.read_csv(path, keep_default_na=False)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read verification register: {exc}")

    status_counts = {
        str(k): int(v)
        for k, v in df["verification_status"].value_counts().items()
    }
    checks = [
        "land_ownership_verified",
        "parcel_boundary_verified",
        "field_visit_completed",
        "site_access_verified",
        "land_use_zone_verified",
        "healthcare_use_permitted_verified",
        "utilities_and_access_reviewed",
        "flood_and_environmental_constraints_reviewed",
    ]

    def is_true(value):
        return str(value).strip().casefold() == "true"

    missing_checks = {}
    for col in checks:
        missing_checks[col] = int((~df[col].map(is_true)).sum())

    return {
        "status": "PASS",
        "candidate_count": int(len(df)),
        "verification_status_counts": status_counts,
        "buildable_land_verified_count": int(df["buildable_land_verified"].map(is_true).sum()),
        "missing_or_incomplete_checks": missing_checks,
        "candidates_missing_parcel_identifier": int(
            (
                df["parcel_id"].astype(str).str.strip().eq("")
                & df["survey_number"].astype(str).str.strip().eq("")
            ).sum()
        ),
        "candidates_missing_evidence_reference": int(
            df["evidence_document_reference"].astype(str).str.strip().eq("").sum()
        ),
        "note": "API smoke-test notes are not real-world evidence. VERIFIED status requires documented parcel and review checks.",
    }

@app.post("/optimizer/site-verification/update")
def optimizer_update_site_verification(payload: dict):
    """Record review evidence; never infer verification from candidate coordinates."""
    from pathlib import Path
    import pandas as pd
    from fastapi import HTTPException
    from datetime import date

    root = Path(__file__).resolve().parents[2]
    path = root / "data" / "reference_site_evidence" / "healthcare_candidate_site_verification_register.csv"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Verification register not found.")

    candidate_id = str(payload.get("candidate_zone_id", "")).strip()
    if not candidate_id:
        raise HTTPException(status_code=422, detail="candidate_zone_id is required.")

    allowed_flags = {
        "land_ownership_verified",
        "parcel_boundary_verified",
        "field_visit_completed",
        "site_access_verified",
        "land_use_zone_verified",
        "healthcare_use_permitted_verified",
        "utilities_and_access_reviewed",
        "flood_and_environmental_constraints_reviewed",
    }
    text_fields = {
        "parcel_id", "survey_number", "land_owner_or_custodian",
        "reviewer", "review_date", "evidence_document_reference", "review_notes",
    }
    unexpected = set(payload) - ({"candidate_zone_id"} | allowed_flags | text_fields)
    if unexpected:
        raise HTTPException(
            status_code=422,
            detail={"message": "Unsupported fields supplied.", "fields": sorted(unexpected)},
        )

    for key in allowed_flags:
        if key in payload and not isinstance(payload[key], bool):
            raise HTTPException(status_code=422, detail=f"{key} must be true or false.")

    try:
        df = pd.read_csv(path, keep_default_na=False)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read verification register: {exc}")

    matches = df.index[df["candidate_zone_id"].astype(str) == candidate_id].tolist()
    if len(matches) != 1:
        raise HTTPException(status_code=404, detail="Candidate not found or candidate ID is ambiguous.")

    idx = matches[0]
    for key in allowed_flags | text_fields:
        if key in payload:
            df.at[idx, key] = payload[key]

    if not str(df.at[idx, "review_date"]).strip() and str(df.at[idx, "reviewer"]).strip():
        df.at[idx, "review_date"] = date.today().isoformat()

    required_checks = [
        "land_ownership_verified",
        "parcel_boundary_verified",
        "field_visit_completed",
        "site_access_verified",
        "land_use_zone_verified",
        "healthcare_use_permitted_verified",
        "utilities_and_access_reviewed",
        "flood_and_environmental_constraints_reviewed",
    ]
    all_checks = all(
        str(df.at[idx, key]).strip().casefold() == "true"
        for key in required_checks
    )
    evidence_present = bool(str(df.at[idx, "evidence_document_reference"]).strip())
    parcel_identified = bool(
        str(df.at[idx, "parcel_id"]).strip()
        or str(df.at[idx, "survey_number"]).strip()
    )
    reviewer_present = bool(str(df.at[idx, "reviewer"]).strip())
    review_date_present = bool(str(df.at[idx, "review_date"]).strip())

    verified = (
        all_checks and evidence_present and parcel_identified
        and reviewer_present and review_date_present
    )
    df.at[idx, "buildable_land_verified"] = bool(verified)
    df.at[idx, "verification_status"] = "VERIFIED" if verified else "IN_REVIEW"

    try:
        df.to_csv(path, index=False, encoding="utf-8-sig")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not save verification register: {exc}")

    return {
        "status": "PASS",
        "candidate_zone_id": candidate_id,
        "verification_status": str(df.at[idx, "verification_status"]),
        "buildable_land_verified": bool(verified),
        "required_checks_complete": all_checks,
        "evidence_reference_present": evidence_present,
        "parcel_identifier_present": parcel_identified,
        "reviewer_and_date_present": reviewer_present and review_date_present,
        "message": (
            "Verification requirements recorded as complete."
            if verified else
            "Review saved, but the candidate remains unverified until all required checks and evidence are present."
        ),
    }


@app.get("/optimizer/cost-model")
def optimizer_cost_model(
    budget: float = 10000000,
    capital_cost_per_site: float = 2500000,
    annual_operating_cost_per_site: float = 0,
    operating_years: int = 10,
    contingency_percent: float = 10,
):
    """Scenario calculator; inputs are assumptions, not verified quotes."""
    from fastapi import HTTPException

    if budget < 0 or capital_cost_per_site < 0 or annual_operating_cost_per_site < 0:
        raise HTTPException(status_code=400, detail="Budget and costs must be non-negative.")
    if operating_years < 1 or operating_years > 100:
        raise HTTPException(status_code=400, detail="operating_years must be between 1 and 100.")
    if contingency_percent < 0 or contingency_percent > 100:
        raise HTTPException(status_code=400, detail="contingency_percent must be between 0 and 100.")

    contingency = capital_cost_per_site * contingency_percent / 100
    capital_with_contingency = capital_cost_per_site + contingency
    lifecycle_per_site = capital_with_contingency + annual_operating_cost_per_site * operating_years
    affordable_by_capital = int(budget // capital_with_contingency) if capital_with_contingency else None
    affordable_by_lifecycle = int(budget // lifecycle_per_site) if lifecycle_per_site else None

    return {
        "status": "PASS",
        "currency": "INR assumed; confirm before financial use",
        "budget": budget,
        "scenario_inputs": {
            "capital_cost_per_site": capital_cost_per_site,
            "annual_operating_cost_per_site": annual_operating_cost_per_site,
            "operating_years": operating_years,
            "contingency_percent": contingency_percent,
        },
        "per_site": {
            "assumed_capital_cost": capital_cost_per_site,
            "assumed_contingency": contingency,
            "assumed_capital_with_contingency": capital_with_contingency,
            "assumed_annual_operating_cost": annual_operating_cost_per_site,
            "assumed_operating_cost_over_period": annual_operating_cost_per_site * operating_years,
            "assumed_lifecycle_total": lifecycle_per_site,
        },
        "affordability": {
            "sites_affordable_by_capital_only": affordable_by_capital,
            "sites_affordable_by_lifecycle_total": affordable_by_lifecycle,
        },
        "cost_status": {
            "construction_cost_verified": False,
            "operating_cost_verified": False,
            "contingency_verified": False,
            "lifecycle_cost_verified": False,
            "official_evidence_used_as_per_site_cost": False,
        },
        "exclusions": [
            "Land acquisition, surveys, approvals, equipment, staffing and maintenance are excluded unless represented in supplied assumptions.",
            "No inflation, discounting, financing cost or salvage value is modelled.",
            "Official budget lines and tender references are not treated as comparable new-facility costs.",
        ],
        "interpretation": "Scenario analysis only; not a quotation, sanctioned estimate, or verified funding recommendation.",
    }


@app.get("/optimizer/feasible-portfolio")
def optimizer_feasible_portfolio(
    budget: float = 10000000,
    cost_per_site: float = 2500000,
    limit: int = 100,
):
    """Only return candidates passing documented parcel-verification gates."""
    from pathlib import Path
    import pandas as pd
    from fastapi import HTTPException

    if budget < 0 or cost_per_site < 0:
        raise HTTPException(status_code=400, detail="Budget and cost_per_site must be non-negative.")
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 1000.")

    root = Path(__file__).resolve().parents[2]
    register = root / "data" / "reference_site_evidence" / "healthcare_candidate_site_verification_register.csv"
    candidates_path = root / "data" / "gold" / "healthcare_candidate_sites.csv"

    if not register.exists():
        raise HTTPException(status_code=404, detail="Site verification register not found.")

    df = pd.read_csv(register, keep_default_na=False)
    required_checks = [
        "land_ownership_verified",
        "parcel_boundary_verified",
        "field_visit_completed",
        "site_access_verified",
        "land_use_zone_verified",
        "healthcare_use_permitted_verified",
        "utilities_and_access_reviewed",
        "flood_and_environmental_constraints_reviewed",
    ]

    def truth(value):
        return str(value).strip().casefold() == "true"

    missing = [c for c in required_checks + [
        "buildable_land_verified", "verification_status", "parcel_id",
        "survey_number", "evidence_document_reference", "reviewer", "review_date"
    ] if c not in df.columns]
    if missing:
        raise HTTPException(status_code=500, detail=f"Verification register missing columns: {missing}")

    eligible = df[
        df["verification_status"].astype(str).str.upper().eq("VERIFIED")
        & df["buildable_land_verified"].map(truth)
        & df[required_checks].apply(lambda row: all(truth(v) for v in row), axis=1)
        & df["evidence_document_reference"].astype(str).str.strip().ne("")
        & (df["parcel_id"].astype(str).str.strip().ne("") | df["survey_number"].astype(str).str.strip().ne(""))
        & df["reviewer"].astype(str).str.strip().ne("")
        & df["review_date"].astype(str).str.strip().ne("")
    ].copy()

    if not eligible.empty and candidates_path.exists():
        candidates = pd.read_csv(candidates_path)
        if "candidate_zone_id" in candidates.columns:
            eligible = eligible.merge(candidates, on="candidate_zone_id", how="left", suffixes=("", "_candidate"))

    affordable_count = int(budget // cost_per_site) if cost_per_site else len(eligible)
    eligible = eligible.head(min(limit, affordable_count))

    sites = []
    for _, row in eligible.iterrows():
        item = {
            "candidate_zone_id": str(row["candidate_zone_id"]),
            "verification_status": str(row["verification_status"]),
            "buildable_land_verified": truth(row["buildable_land_verified"]),
            "parcel_id": str(row["parcel_id"]),
            "survey_number": str(row["survey_number"]),
            "evidence_document_reference": str(row["evidence_document_reference"]),
            "assumed_cost": cost_per_site,
            "cost_is_verified": False,
        }
        for col in ["rank", "screening_score", "model_rank", "model_screening_score"]:
            if col in row.index and pd.notna(row[col]):
                item[col] = row[col].item() if hasattr(row[col], "item") else row[col]
        sites.append(item)

    return {
        "status": "PASS",
        "decision": "PROVISIONAL_SCREENING_ONLY" if sites else "NO_VERIFIED_FEASIBLE_SITES",
        "budget": budget,
        "assumed_cost_per_site": cost_per_site,
        "cost_is_verified": False,
        "eligible_verified_site_count_before_budget": int(len(eligible)),
        "selected_site_count": len(sites),
        "assumed_portfolio_cost": len(sites) * cost_per_site,
        "remaining_budget": budget - len(sites) * cost_per_site,
        "selected_sites": sites,
        "feasibility_gate": {
            "requires_all_eight_checks": True,
            "requires_parcel_or_survey_identifier": True,
            "requires_evidence_reference": True,
            "requires_reviewer_and_date": True,
            "requires_buildable_land_verified": True,
        },
        "note": "A high screening score or affordable assumed cost does not establish feasibility. Only documented verified candidates can pass this gate.",
    }




@app.get("/optimizer/scenario")
def optimizer_counterfactual_scenario(
    scenario_type: str,
    latitude: float = None,
    longitude: float = None,
    site_ids: str = "",
    budget: float = 10000000,
    capital_cost_per_site: float = 2500000,
    annual_operating_cost_per_site: float = 0,
    operating_years: int = 10,
    contingency_percent: float = 10,
):
    """Run a fresh counterfactual simulation and export normalized JSON/CSV results."""
    import csv
    import json
    import subprocess
    import sys
    from datetime import datetime, timezone
    from pathlib import Path
    from fastapi import HTTPException

    kind = scenario_type.strip().lower()
    if kind not in {"location", "portfolio"}:
        raise HTTPException(status_code=422, detail="scenario_type must be location or portfolio.")
    if budget < 0 or capital_cost_per_site < 0 or annual_operating_cost_per_site < 0:
        raise HTTPException(status_code=422, detail="Budget and cost assumptions must be non-negative.")
    if not 1 <= operating_years <= 100:
        raise HTTPException(status_code=422, detail="operating_years must be between 1 and 100.")
    if not 0 <= contingency_percent <= 100:
        raise HTTPException(status_code=422, detail="contingency_percent must be between 0 and 100.")

    root = Path(__file__).resolve().parents[2]
    if kind == "location":
        if latitude is None or longitude is None or not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise HTTPException(status_code=422, detail="Location scenarios require valid latitude and longitude.")
        script = root / "scripts" / "evaluate_proposed_healthcare_location.py"
        args = [sys.executable, str(script), "--latitude", str(latitude), "--longitude", str(longitude)]
        selected_ids = []
        if not script.exists():
            raise HTTPException(status_code=404, detail="Location simulation script not found.")
    else:
        selected_ids = [x.strip() for x in site_ids.split(",") if x.strip()]
        if not selected_ids:
            raise HTTPException(status_code=422, detail="Portfolio scenarios require comma-separated site_ids.")
        if len(selected_ids) != len(set(selected_ids)):
            raise HTTPException(status_code=422, detail="Duplicate site_ids are not allowed.")
        if len(selected_ids) > 100:
            raise HTTPException(status_code=422, detail="At most 100 site IDs may be simulated.")
        script = root / "scripts" / "evaluate_healthcare_portfolio.py"
        args = [sys.executable, str(script), "--site-ids", ",".join(selected_ids)]
        if not script.exists():
            raise HTTPException(status_code=404, detail="Portfolio simulation script not found.")

    try:
        result = subprocess.run(
            args, cwd=str(root), capture_output=True, text=True,
            timeout=600, check=False
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Scenario simulation exceeded 600 seconds.")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not launch scenario simulation: {exc}")

    if result.returncode != 0:
        raise HTTPException(status_code=500, detail={
            "message": "Scenario simulation failed.",
            "stderr": result.stderr[-4000:],
            "stdout": result.stdout[-2000:],
        })

    try:
        if kind == "location":
            start = result.stdout.find("{")
            if start < 0:
                raise ValueError("No JSON object in location simulation output.")
            simulation, _ = json.JSONDecoder().raw_decode(result.stdout[start:])
        else:
            simulation = json.loads(result.stdout)
        if simulation.get("status") != "PASS":
            raise ValueError("Underlying simulation did not report PASS.")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not parse successful simulation report: {exc}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    json_path = reports / f"counterfactual_scenario_{stamp}.json"
    csv_path = reports / f"counterfactual_scenario_{stamp}.csv"

    capital = capital_cost_per_site
    contingency = capital * contingency_percent / 100
    capital_with_contingency = capital + contingency
    lifecycle_per_site = capital_with_contingency + annual_operating_cost_per_site * operating_years
    site_count = 1 if kind == "location" else len(selected_ids)

    if kind == "location":
        proposed = simulation.get("proposed_location", {})
        mode_metrics = {}
        for mode in ("driving", "walking"):
            m = simulation.get(mode, {})
            mode_metrics[mode] = {
                "grid_cells_evaluated": m.get("grid_cells_evaluated"),
                "baseline_reachable_cells": m.get("baseline_reachable_cells"),
                "after_reachable_cells": m.get("after_reachable_cells"),
                "mean_distance_before_m": m.get("mean_distance_before_m"),
                "mean_distance_after_m": m.get("mean_distance_after_m"),
                "mean_reduction_m": m.get("mean_reduction_among_baseline_reachable_m"),
                "cells_improved_over_1m": m.get("cells_improved_over_1m"),
                "cells_over_5km_before": m.get("cells_over_5km_before"),
                "cells_over_5km_after": m.get("cells_over_5km_after"),
                "cells_moved_to_5km_or_less": m.get("cells_moved_to_5km_or_less"),
                "potentially_affected_cells": m.get("cells_improved_over_1m"),
                "population_units_verified": m.get("population_units_verified", False),
            }
        location = proposed
        simulation_kind = "fresh_single_location_network_distance"
    else:
        location = None
        simulation_kind = "fresh_joint_portfolio_network_distance"
        raw_metrics = simulation.get("metrics", {})
        mode_metrics = {}
        for mode in ("driving", "walking"):
            m = raw_metrics.get(mode, {})
            mode_metrics[mode] = {
                "grid_cells_evaluated": simulation.get("input_grid_cell_count"),
                "comparable_cells": m.get("grid_cells_with_baseline_and_portfolio_routes"),
                "cells_improved_over_1m": m.get("grid_cells_improved_over_threshold"),
                "cells_moved_to_5km_or_less": m.get("grid_cells_moved_to_within_reachability_threshold"),
                "cells_within_5km_after": m.get("grid_cells_within_threshold_after_portfolio"),
                "mean_reduction_m_all_comparable_cells": m.get("mean_distance_reduction_m_all_comparable_cells"),
                "mean_reduction_m_among_baseline_reachable": m.get("mean_distance_reduction_m_among_baseline_reachable"),
                "unrouted_or_missing_cells": m.get("unrouted_or_missing_cells"),
                "potentially_affected_cells": m.get("grid_cells_improved_over_threshold"),
                "population_units_verified": False,
            }

    cost = {
        "currency": "INR assumed; confirm before financial use",
        "site_count_assumed": site_count,
        "assumed_capital_cost_per_site": capital,
        "assumed_contingency_percent": contingency_percent,
        "assumed_contingency_per_site": contingency,
        "assumed_capital_with_contingency_per_site": capital_with_contingency,
        "assumed_annual_operating_cost_per_site": annual_operating_cost_per_site,
        "assumed_operating_cost_per_site_over_period": annual_operating_cost_per_site * operating_years,
        "assumed_lifecycle_total_per_site": lifecycle_per_site,
        "assumed_portfolio_capital_with_contingency": capital_with_contingency * site_count,
        "assumed_portfolio_operating_cost_over_period": annual_operating_cost_per_site * operating_years * site_count,
        "assumed_portfolio_lifecycle_total": lifecycle_per_site * site_count,
        "budget": budget,
        "budget_covers_assumed_lifecycle_total": lifecycle_per_site * site_count <= budget,
        "verified_per_site_cost_available": False,
        "official_evidence_used_as_per_site_cost": False,
    }

    limitations = [
        "Grid-cell counts are not verified counts of people; population raster units remain unverified.",
        "Distance metrics are not travel-time estimates.",
        "Candidate centroids and network snaps do not establish parcel feasibility.",
        "Costs are user-supplied assumptions, not verified estimates or approved funding.",
        "Operating costs, capacity, service eligibility, land acquisition, permits, and lifecycle risks are not empirically validated unless explicitly supplied.",
    ]
    if kind == "portfolio":
        limitations.extend(simulation.get("limitations", []))
    else:
        limitations.extend(simulation.get("limitations", []))

    payload = {
        "status": "PASS",
        "scenario_id": f"CF_{stamp}",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scenario_type": kind,
        "simulation_method": simulation_kind,
        "baseline": {
            "definition": "Existing healthcare accessibility in the supplied baseline dataset and road graphs.",
            "metrics_by_mode": {
                mode: {
                    "reachable_cells_before": m.get("baseline_reachable_cells"),
                    "mean_distance_before_m": m.get("mean_distance_before_m"),
                    "cells_over_5km_before": m.get("cells_over_5km_before"),
                }
                for mode, m in mode_metrics.items()
            } if kind == "location" else {
                "note": "Portfolio report contains joint-comparison metrics; inspect the underlying report for exact baseline values."
            },
        },
        "intervention": {
            "proposed_location": location,
            "selected_site_ids": selected_ids if kind == "portfolio" else [],
            "assumed_facility_count": site_count,
        },
        "metrics_by_mode": mode_metrics,
        "cost_assumptions": cost,
        "underserved_area_proxy": {
            "definition": "Grid cells over the 5 km network-distance threshold before and after, where available.",
            "population_units_verified": False,
            "limitation": "This is a spatial accessibility proxy, not a confirmed count of underserved residents.",
        },
        "assumptions": {
            "reachability_threshold_m": 5000,
            "improvement_threshold_m": 1,
            "population_units_verified": False,
            "costs_are_assumptions": True,
        },
        "limitations": list(dict.fromkeys(limitations)),
        "underlying_simulation_report": simulation,
        "exports": {
            "json": str(json_path.relative_to(root)),
            "csv": str(csv_path.relative_to(root)),
        },
    }

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        fields = [
            "scenario_id", "scenario_type", "mode", "grid_cells_evaluated",
            "baseline_reachable_cells", "after_reachable_cells",
            "mean_distance_before_m", "mean_distance_after_m", "mean_reduction_m",
            "cells_improved_over_1m", "cells_over_5km_before", "cells_over_5km_after",
            "cells_moved_to_5km_or_less", "potentially_affected_cells",
            "population_units_verified", "assumed_capital_cost_per_site",
            "assumed_annual_operating_cost_per_site", "assumed_lifecycle_total_per_site",
            "assumed_portfolio_lifecycle_total", "budget",
        ]
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for mode, metrics in mode_metrics.items():
            row = {
                "scenario_id": payload["scenario_id"],
                "scenario_type": kind,
                "mode": mode,
                **metrics,
                "assumed_capital_cost_per_site": capital,
                "assumed_annual_operating_cost_per_site": annual_operating_cost_per_site,
                "assumed_lifecycle_total_per_site": lifecycle_per_site,
                "assumed_portfolio_lifecycle_total": lifecycle_per_site * site_count,
                "budget": budget,
            }
            writer.writerow(row)

    return payload



@app.get("/optimizer/candidates")
def optimizer_candidates(
    infrastructure_type: str = Query(default="healthcare", min_length=1, max_length=60),
):
    """Return saved candidate comparison rows; no new impact simulation is run."""
    allowed = {"healthcare"}
    if infrastructure_type.casefold() not in allowed:
        raise HTTPException(
            status_code=400,
            detail=(
                "Saved Phase 4 candidate-impact data currently supports healthcare only. "
                "Other infrastructure types require their own impact datasets."
            ),
        )
    rows, path = load_candidate_comparison()
    return {
        "infrastructure_type": infrastructure_type.casefold(),
        "source_file": path.name,
        "total": len(rows),
        "items": rows,
        "limitations": [
            "This endpoint serves saved screening results; it does not rerun accessibility analysis.",
            "Population raster values are not verified headcounts; do not describe cells as people.",
            "Candidate coordinates are screening centroids, not verified buildable parcels.",
            "Travel distance is not travel time; facility capacity is not modeled.",
        ],
    }


@app.get("/optimizer/portfolio")
def optimizer_portfolio(
    budget: float = Query(..., gt=0, le=1_000_000_000_000),
    infrastructure_type: str = Query(default="healthcare", min_length=1, max_length=60),
    cost_per_site: float | None = Query(default=None, gt=0, le=1_000_000_000_000),
):
    """Return a transparent greedy portfolio based on saved comparison scores."""
    if infrastructure_type.casefold() != "healthcare":
        raise HTTPException(
            status_code=400,
            detail="Portfolio evaluation is currently available for healthcare candidates only.",
        )
    rows, path = load_candidate_comparison()
    if not rows:
        raise HTTPException(status_code=503, detail="Candidate comparison report is empty.")

    # Prefer the existing score and cost columns produced by the evaluator.
    normalized: list[dict] = []
    for row in rows:
        site_id = (
            row.get("candidate_zone_id") or row.get("site_id")
            or row.get("candidate_id") or row.get("candidate")
        )
        if not site_id:
            continue
        score = number(row, "priority_score", "composite_score", "screening_score", "suitability_score")
        if score is None:
            # Fallback is explicitly a ranking proxy, not an impact estimate.
            parts = [
                number(row, "driving_cells_moved_to_5km_or_less"),
                number(row, "walking_cells_moved_to_5km_or_less"),
                number(row, "driving_mean_reduction_among_baseline_reachable_m",
                       "driving_mean_distance_reduction_among_baseline_reachable_m"),
                number(row, "walking_mean_reduction_among_baseline_reachable_m",
                       "walking_mean_distance_reduction_among_baseline_reachable_m"),
            ]
            score = sum(v for v in parts if v is not None)
        cost = cost_per_site or number(row, "assumed_site_cost", "estimated_site_cost", "site_cost")
        if cost is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "No site-cost column found. Supply cost_per_site explicitly; "
                    "costs are assumptions, not verified estimates."
                ),
            )
        if cost <= 0:
            continue
        normalized.append({
            "candidate_zone_id": site_id,
            "score": float(score),
            "assumed_cost": float(cost),
            "source_row": row,
        })
    if not normalized:
        raise HTTPException(
            status_code=422,
            detail="No usable candidate IDs found in the comparison report.",
        )

    # Greedy score-per-cost selection, with deterministic tie-breaking.
    ranked = sorted(
        normalized,
        key=lambda item: (
            -(item["score"] / item["assumed_cost"]),
            -item["score"],
            item["candidate_zone_id"],
        ),
    )
    selected = []
    spent = 0.0
    for item in ranked:
        if spent + item["assumed_cost"] <= budget + 1e-9:
            selected.append(item)
            spent += item["assumed_cost"]

    return {
        "status": "PASS" if selected else "NO_SITES_WITHIN_BUDGET",
        "infrastructure_type": infrastructure_type.casefold(),
        "source_file": path.name,
        "budget": budget,
        "cost_basis": "caller-supplied cost_per_site" if cost_per_site else "cost column in comparison CSV",
        "candidate_count": len(normalized),
        "selected_sites": [
            {
                "candidate_zone_id": item["candidate_zone_id"],
                "priority_score": item["score"],
                "assumed_cost": item["assumed_cost"],
                "pros": [
                    "Included in the saved candidate comparison.",
                    "Ranked using the available screening score or fallback proxy.",
                ],
                "cons": [
                    "Buildable land and site permissions are not verified.",
                    "Facility capacity and operating costs are not modeled unless supplied in source data.",
                    "Single-site impacts are not additive; portfolio-wide accessibility has not been simulated.",
                ],
            }
            for item in selected
        ],
        "selected_site_count": len(selected),
        "assumed_portfolio_cost": round(spent, 2),
        "remaining_budget": round(budget - spent, 2),
        "selection_method": "Greedy descending score-per-assumed-cost; not a globally optimal solution.",
        "evidence_and_assumptions": [
            f"Candidate comparison source: {path.name}.",
            "Saved screening results are used; this endpoint does not rerun routing or accessibility.",
            "Raster cells are not verified people counts.",
            "Coordinates identify candidate zones/centroids, not surveyed parcels.",
            "Costs are assumptions and exclude unmodeled operating, land, and lifecycle costs.",
            "Selected sites' individual simulated effects must not be summed as a portfolio effect.",
        ],
    }
