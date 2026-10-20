from pathlib import Path

p = Path("frontend/backend/main.py")
source = p.read_text(encoding="utf-8")

marker = '@app.get("/optimizer/candidates")'
if marker not in source:
    raise SystemExit("Could not find insertion point; no changes made.")

routes = []

if '@app.get("/optimizer/cost-model")' not in source:
    routes.append('''
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
''')

if '@app.get("/optimizer/feasible-portfolio")' not in source:
    routes.append('''
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
''')

if not routes:
    print("Both routes already exist; no changes made.")
    raise SystemExit(0)

backup = p.with_name("main.py.pre_phase4_cost_feasibility.bak")
backup.write_text(source, encoding="utf-8")
source = source.replace(marker, "\n".join(routes) + "\n\n" + marker, 1)
p.write_text(source, encoding="utf-8")
print("Added routes:", ", ".join(
    name for name in ["cost-model", "feasible-portfolio"]
    if f'/optimizer/{name}' in source
))
print(f"Backup: {backup}")
