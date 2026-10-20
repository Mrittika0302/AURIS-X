from pathlib import Path
import csv
import json
from datetime import datetime, timezone

root = Path(__file__).resolve().parents[1]
out_dir = root / "data" / "reference_cost_evidence"
out_dir.mkdir(parents=True, exist_ok=True)

records = [
    {
        "evidence_id": "CCMC_BUDGET_2025_26_BUILDINGS",
        "infrastructure_type": "building",
        "scope": "Coimbatore Corporation Buildings budget line",
        "amount_inr": 1123000000,
        "cost_type": "annual_budget_category",
        "period": "2025-26",
        "geography": "Coimbatore City Municipal Corporation",
        "source_organization": "Coimbatore City Municipal Corporation",
        "source_reference": "Coimbatore_Corporation_Budget_2025-26.pdf",
        "source_url": "https://ccmc.gov.in/img/upload/Coimbatore_Corporation_Budget_2025-26.pdf",
        "evidence_status": "official_published_budget",
        "usable_as_per_site_cost": False,
        "limitations": "Corporation-wide budget category; not a project-level or per-facility construction cost."
    },
    {
        "evidence_id": "CCMC_BUDGET_2025_26_HOSPITALS",
        "infrastructure_type": "healthcare",
        "scope": "Coimbatore Corporation Hospital budget line",
        "amount_inr": 89500000,
        "cost_type": "annual_budget_category",
        "period": "2025-26",
        "geography": "Coimbatore City Municipal Corporation",
        "source_organization": "Coimbatore City Municipal Corporation",
        "source_reference": "Coimbatore_Corporation_Budget_2025-26.pdf",
        "source_url": "https://ccmc.gov.in/img/upload/Coimbatore_Corporation_Budget_2025-26.pdf",
        "evidence_status": "official_published_budget",
        "usable_as_per_site_cost": False,
        "limitations": "Corporation-wide budget category; not a new-facility construction estimate."
    },
    {
        "evidence_id": "CCMC_UHSC_IMPROVEMENTS_WARD79_2026",
        "infrastructure_type": "healthcare",
        "scope": "Additional improvement works to Urban Health Sub Centre, Muthusamy Colony-2, Ward 79, South Zone",
        "amount_inr": 1000000,
        "cost_type": "tender_estimate",
        "period": "2026",
        "geography": "Coimbatore Corporation, South Zone",
        "source_organization": "Government of Tamil Nadu eProcurement / Coimbatore City Municipal Corporation",
        "source_reference": "Tender ID 2026_MAWS_680570_5; published June 2026",
        "source_url": "https://tntenders.gov.in/nicgep/app",
        "evidence_status": "official_tender_listing",
        "usable_as_per_site_cost": False,
        "limitations": "Improvement works at an existing facility; tender estimate is not the cost of a new facility. Search the official portal using the tender ID."
    },
    {
        "evidence_id": "CCMC_UPHC_STAFFING_SOUTH_2026",
        "infrastructure_type": "healthcare_operations",
        "scope": "Outsourced staffing services at seven Urban Primary Health Centres in the South Zone; tender describes a six-month service scope",
        "amount_inr": 3754000,
        "cost_type": "staffing_service_tender_estimate",
        "period": "2026",
        "geography": "Coimbatore Corporation, South Zone",
        "source_organization": "Government of Tamil Nadu eProcurement / Coimbatore City Municipal Corporation",
        "source_reference": "Tender reference E73/2026-Two cover; Tender ID 2026_MAWS_708658_11",
        "source_url": "https://tntenders.gov.in/nicgep/app",
        "evidence_status": "official_tender_listing",
        "usable_as_per_site_cost": False,
        "limitations": "Staffing/service contract, not construction cost. Verify award status, final contract value, service period, and applicable tender documents before financial use."
    },
]

stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
csv_path = out_dir / "phase4_cost_evidence_register.csv"
json_path = root / "reports" / f"phase4_cost_evidence_register_{stamp}.json"
json_path.parent.mkdir(parents=True, exist_ok=True)

fields = list(records[0].keys())
with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(records)

summary = {
    "status": "PASS",
    "created_utc": stamp,
    "record_count": len(records),
    "official_budget_records": sum(r["cost_type"] == "annual_budget_category" for r in records),
    "tender_records": sum("tender" in r["cost_type"] for r in records),
    "records_approved_as_per_site_cost": sum(bool(r["usable_as_per_site_cost"]) for r in records),
    "warning": "No record in this initial register is approved as a verified per-site construction cost.",
    "register_csv": str(csv_path.relative_to(root)),
    "records": records,
}
json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

print(json.dumps({
    "status": "PASS",
    "records_created": len(records),
    "approved_per_site_costs": 0,
    "csv": str(csv_path.relative_to(root)),
    "summary_json": str(json_path.relative_to(root)),
}, indent=2))
