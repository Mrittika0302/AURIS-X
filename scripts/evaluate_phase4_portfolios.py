#!/usr/bin/env python3
"""AURIS-X Phase 4 candidate comparison and budget-constrained portfolio screening.

Reads existing candidate and single-site impact CSVs. Does not modify source files.
All scores are screening metrics; raster weights are not verified headcounts.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES_DEFAULT = ROOT / "data/gold/healthcare_candidate_sites.csv"
IMPACT_DEFAULT = ROOT / "reports/candidate_impact_top10_20261012.csv"
REPORTS = ROOT / "reports"


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Required input not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def number(row: dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        value = float(row.get(key, ""))
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def truth(row: dict[str, str], key: str) -> bool:
    return str(row.get(key, "")).strip().lower() in {"true", "1", "yes"}


def minmax(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if math.isclose(lo, hi):
        return [50.0 if math.isfinite(v) else 0.0 for v in values]
    return [max(0.0, min(100.0, (v - lo) * 100.0 / (hi - lo))) for v in values]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget", type=float, required=True,
                        help="Maximum budget in the same currency units as assumed_site_cost (currently INR).")
    parser.add_argument("--candidate-file", type=Path, default=CANDIDATES_DEFAULT)
    parser.add_argument("--impact-file", type=Path, default=IMPACT_DEFAULT)
    parser.add_argument("--cost-per-site", type=float, default=None,
                        help="Override per-site cost for scenario testing; explicitly an assumption.")
    parser.add_argument("--max-sites", type=int, default=10)
    args = parser.parse_args()

    if args.budget < 0:
        parser.error("--budget must be >= 0")
    if args.max_sites < 1:
        parser.error("--max-sites must be >= 1")
    if args.cost_per_site is not None and args.cost_per_site < 0:
        parser.error("--cost-per-site must be >= 0")

    candidates = read_csv(args.candidate_file)
    impacts = read_csv(args.impact_file)
    if not candidates or not impacts:
        raise ValueError("Candidate and impact files must both contain rows.")
    for key in ("candidate_zone_id", "screening_score", "centroid_latitude", "centroid_longitude"):
        if key not in candidates[0]:
            raise ValueError(
                f"Candidate CSV missing required column: {key}. "
                f"Available columns: {', '.join(candidates[0].keys())}"
            )

    # Normalize historical column-name variants BEFORE checking required columns.
    # The source impact CSV is read into memory and is never modified on disk.
    aliases = {
        "driving_mean_distance_reduction_among_baseline_reachable_m": (
            "driving_mean_distance_reduction_among_baseline_reachable_m",
            "driving_mean_reduction_among_baseline_reachable_m",
        ),
        "walking_mean_distance_reduction_among_baseline_reachable_m": (
            "walking_mean_distance_reduction_among_baseline_reachable_m",
            "walking_mean_reduction_among_baseline_reachable_m",
        ),
    }
    impact_headers = set(impacts[0].keys())
    for canonical_name, choices in aliases.items():
        actual_name = next((name for name in choices if name in impact_headers), None)
        if actual_name is not None and actual_name != canonical_name:
            for row in impacts:
                row[canonical_name] = row.get(actual_name, "")

    required_impact_columns = (
        "candidate_zone_id",
        "driving_cells_moved_to_5km_or_less",
        "walking_cells_moved_to_5km_or_less",
        "driving_mean_distance_reduction_among_baseline_reachable_m",
        "walking_mean_distance_reduction_among_baseline_reachable_m",
    )
    for key in required_impact_columns:
        if key not in impacts[0]:
            raise ValueError(
                f"Impact CSV missing required column: {key}. "
                f"Available columns: {', '.join(impacts[0].keys())}"
            )
    impact_by_id = {r["candidate_zone_id"]: r for r in impacts}
    joined = []
    for c in candidates:
        cid = c["candidate_zone_id"]
        impact = impact_by_id.get(cid)
        if not impact:
            continue
        cost = args.cost_per_site if args.cost_per_site is not None else number(c, "assumed_site_cost", 0.0)
        if cost < 0:
            continue
        drive_moved = number(impact, "driving_cells_moved_to_5km_or_less")
        walk_moved = number(impact, "walking_cells_moved_to_5km_or_less")
        drive_reduction = number(impact, "driving_mean_distance_reduction_among_baseline_reachable_m")
        walk_reduction = number(impact, "walking_mean_distance_reduction_among_baseline_reachable_m")
        screening = number(c, "screening_score")
        # These are relative ranking components, not people counts or probabilities.
        joined.append({
            "candidate_zone_id": cid,
            "latitude": number(c, "centroid_latitude"),
            "longitude": number(c, "centroid_longitude"),
            "screening_score": screening,
            "driving_cells_moved_to_5km_or_less": drive_moved,
            "walking_cells_moved_to_5km_or_less": walk_moved,
            "driving_mean_distance_reduction_m": drive_reduction,
            "walking_mean_distance_reduction_m": walk_reduction,
            "drive_snap_m": number(impact, "drive_candidate_snap_m", math.nan),
            "walk_snap_m": number(impact, "walk_candidate_snap_m", math.nan),
            "snap_review": truth(impact, "drive_snap_review") or truth(impact, "walk_snap_review"),
            "cost": cost,
            "cost_is_assumption": args.cost_per_site is not None or not truth(c, "buildable_land_verified"),
            "population_units_verified": truth(impact, "population_raster_units_verified"),
            "buildable_parcel_verified": truth(impact, "candidate_is_buildable_parcel"),
            "travel_time_modelled": truth(impact, "travel_time_modelled"),
            "facility_capacity_modelled": truth(impact, "facility_capacity_modelled"),
            "review_flags": c.get("review_flags", ""),
        })

    if not joined:
        raise ValueError("No candidate IDs overlap between candidate and impact CSVs.")

    # Candidate impact only exists for the 10 simulated candidates. Normalize across this matched set.
    metric_specs = [
        ("driving_cells_moved_to_5km_or_less", 0.30),
        ("walking_cells_moved_to_5km_or_less", 0.30),
        ("driving_mean_distance_reduction_m", 0.15),
        ("walking_mean_distance_reduction_m", 0.15),
        ("screening_score", 0.10),
    ]
    for field, weight in metric_specs:
        normalized = minmax([r[field] for r in joined])
        for r, score in zip(joined, normalized):
            r[field + "_normalized"] = score
            r["priority_score"] = r.get("priority_score", 0.0) + score * weight

    # Show explicit evidence flags and do not imply the relative score is validated.
    for r in joined:
        r["priority_score"] = round(r["priority_score"], 2)
        pros, cons = [], []
        if r["driving_cells_moved_to_5km_or_less"] > 0:
            pros.append("Improves modeled driving coverage at the 5 km threshold")
        if r["walking_cells_moved_to_5km_or_less"] > 0:
            pros.append("Improves modeled walking coverage at the 5 km threshold")
        if r["screening_score"] >= 60:
            pros.append("High relative underserved-gap screening score")
        if r["snap_review"]:
            cons.append("Candidate-to-network snap needs review")
        if not r["population_units_verified"]:
            cons.append("Population raster units are unverified; grid-cell metrics are not headcounts")
        if not r["buildable_parcel_verified"]:
            cons.append("Candidate centroid is not a verified buildable parcel")
        if not r["travel_time_modelled"]:
            cons.append("Travel time is not modelled; metrics are network distance")
        if not r["facility_capacity_modelled"]:
            cons.append("Facility capacity and service mix are not modelled")
        if r["cost_is_assumption"]:
            cons.append("Cost is an assumed scenario value, not a site-specific estimate")
        r["pros"] = "; ".join(pros) or "No positive impact signal in available metrics"
        r["cons"] = "; ".join(cons) or "Review site feasibility before investment"

    ranked = sorted(joined, key=lambda r: (-r["priority_score"], r["candidate_zone_id"]))
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
        r["affordable_alone"] = r["cost"] <= args.budget

    # Greedy portfolio: prioritize impact score per cost, subject to budget and max sites.
    # This is a transparent heuristic, not a globally optimal solution.
    portfolio_pool = sorted(
        [r for r in ranked if r["cost"] <= args.budget],
        key=lambda r: (-(r["priority_score"] / r["cost"] if r["cost"] > 0 else float("inf")),
                       -r["priority_score"], r["candidate_zone_id"])
    )
    selected, spent = [], 0.0
    for r in portfolio_pool:
        if len(selected) >= args.max_sites:
            break
        if spent + r["cost"] <= args.budget:
            selected.append(r)
            spent += r["cost"]
    selected_ids = {r["candidate_zone_id"] for r in selected}
    for r in ranked:
        r["selected_in_budget_portfolio"] = r["candidate_zone_id"] in selected_ids

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    csv_path = REPORTS / f"phase4_candidate_comparison_{timestamp}.csv"
    json_path = REPORTS / f"phase4_portfolio_summary_{timestamp}.json"
    REPORTS.mkdir(parents=True, exist_ok=True)

    fields = [
        "rank", "candidate_zone_id", "latitude", "longitude", "priority_score",
        "screening_score", "driving_cells_moved_to_5km_or_less",
        "walking_cells_moved_to_5km_or_less", "driving_mean_distance_reduction_m",
        "walking_mean_distance_reduction_m", "drive_snap_m", "walk_snap_m",
        "snap_review", "cost", "cost_is_assumption", "affordable_alone",
        "selected_in_budget_portfolio", "pros", "cons", "review_flags",
        "population_units_verified", "buildable_parcel_verified",
        "travel_time_modelled", "facility_capacity_modelled"
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(ranked)

    summary = {
        "title": "AURIS-X Phase 4 candidate comparison and budget screening",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "budget": args.budget,
        "currency": "INR (assumed from project cost context; confirm before procurement use)",
        "cost_source": "candidate assumed_site_cost unless overridden by --cost-per-site",
        "candidate_file": str(args.candidate_file),
        "impact_file": str(args.impact_file),
        "matched_candidates": len(ranked),
        "selected_site_count": len(selected),
        "portfolio_candidate_ids": [r["candidate_zone_id"] for r in selected],
        "portfolio_assumed_cost": round(spent, 2),
        "remaining_budget": round(args.budget - spent, 2),
        "portfolio_selection_method": "Greedy priority-score-per-cost heuristic; not a guaranteed global optimum.",
        "priority_score_method": {
            "driving cells moved to <=5 km": 0.30,
            "walking cells moved to <=5 km": 0.30,
            "driving mean-distance reduction": 0.15,
            "walking mean-distance reduction": 0.15,
            "existing screening score": 0.10,
            "normalization": "Min-max 0-100 across candidates with available impact simulations only."
        },
        "limitations": [
            "Impact simulations are available only for matched candidates, currently expected to be the precomputed top 10.",
            "Each candidate was simulated individually; combined portfolio impact is not simulated and benefits may overlap.",
            "Raster units are unverified; cell counts are not verified population headcounts.",
            "Candidate centroids are not verified buildable parcels.",
            "Distances are network metres, not travel times.",
            "Facility capacity and service mix are not modelled.",
            "Cost is an assumed planning input, not a verified construction or operating estimate.",
            "This is decision support, not an investment approval or land feasibility determination."
        ],
        "top_candidates": [
            {
                "rank": r["rank"],
                "candidate_zone_id": r["candidate_zone_id"],
                "priority_score": r["priority_score"],
                "assumed_cost": r["cost"],
                "selected_in_portfolio": r["selected_in_budget_portfolio"],
                "pros": r["pros"],
                "cons": r["cons"]
            } for r in ranked[:10]
        ],
        "outputs": {"comparison_csv": str(csv_path), "summary_json": str(json_path)}
    }
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": "PASS",
        "matched_candidates": len(ranked),
        "budget": args.budget,
        "selected_sites": [r["candidate_zone_id"] for r in selected],
        "assumed_portfolio_cost": round(spent, 2),
        "remaining_budget": round(args.budget - spent, 2),
        "comparison_csv": str(csv_path),
        "summary_json": str(json_path),
        "warning": "Screening heuristic only; single-site impacts are not additive."
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
