from pathlib import Path

p = Path("frontend/backend/main.py")
source = p.read_text(encoding="utf-8")

if '@app.get("/optimizer/cost-evidence")' in source:
    print("Route already exists; no changes made.")
    raise SystemExit(0)

marker = '@app.get("/optimizer/candidates")'
if marker not in source:
    raise SystemExit("Could not find insertion point. No changes made.")

backup = p.with_name("main.py.pre_cost_evidence.bak")
backup.write_text(source, encoding="utf-8")

route = '''

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

'''

source = source.replace(marker, route + marker, 1)
p.write_text(source, encoding="utf-8")
print("Added /optimizer/cost-evidence")
print(f"Backup: {backup}")
