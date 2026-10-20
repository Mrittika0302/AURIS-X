from pathlib import Path

p = Path("frontend/backend/main.py")
source = p.read_text(encoding="utf-8")

if '@app.get("/optimizer/cost-scenarios")' in source:
    print("Route already exists; no changes made.")
    raise SystemExit(0)

marker = '@app.get("/optimizer/candidates")'
if marker not in source:
    raise SystemExit("Could not find insertion point. No changes made.")

backup = p.with_name("main.py.pre_cost_scenarios.bak")
backup.write_text(source, encoding="utf-8")

route = '''

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
        })

    return {
        "status": "PASS",
        "currency": "INR assumed by current project convention; confirm before financial use",
        "candidate_count": candidate_count,
        "budget": budget,
        "scenarios": scenarios,
        "limitations": [
            "Per-site costs are supplied by the caller and are not verified estimates.",
            "The calculation is arithmetic affordability only; it does not select or validate sites.",
            "Land acquisition, surveys, permits, equipment, staffing, operations, maintenance, inflation, and lifecycle costs are excluded unless included in the supplied per-site assumption.",
            "Buildable land and population units remain unverified.",
            "Affordable site count does not establish that the sites are feasible or that their individual impacts add together.",
        ],
    }

'''

source = source.replace(marker, route + marker, 1)
p.write_text(source, encoding="utf-8")
print("Added /optimizer/cost-scenarios")
print(f"Backup: {backup}")
