from pathlib import Path

p = Path("frontend/backend/main.py")
source = p.read_text(encoding="utf-8")
marker = '@app.get("/optimizer/candidates")'

if '@app.get("/optimizer/scenario")' in source:
    print("Route /optimizer/scenario already exists; no changes made.")
    raise SystemExit(0)

if marker not in source:
    raise SystemExit("Could not find insertion point; no changes made.")

route = r'''

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

'''

backup = p.with_name("main.py.pre_counterfactual_scenario.bak")
backup.write_text(source, encoding="utf-8")
source = source.replace(marker, route + "\n\n" + marker, 1)
p.write_text(source, encoding="utf-8")
print("Added /optimizer/scenario")
print(f"Backup: {backup}")
