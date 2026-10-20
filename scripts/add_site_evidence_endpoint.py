from pathlib import Path

p = Path("frontend/backend/main.py")
source = p.read_text(encoding="utf-8")

if '@app.get("/optimizer/site-evidence")' in source:
    print("Route already exists; no changes made.")
    raise SystemExit(0)

marker = '@app.get("/optimizer/candidates")'
if marker not in source:
    raise SystemExit("Could not find insertion point. No changes made.")

backup = p.with_name("main.py.pre_site_evidence.bak")
backup.write_text(source, encoding="utf-8")

route = '''

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

'''

source = source.replace(marker, route + marker, 1)
p.write_text(source, encoding="utf-8")
print("Added /optimizer/site-evidence")
print(f"Backup: {backup}")
