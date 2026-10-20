from pathlib import Path

p = Path("frontend/backend/main.py")
source = p.read_text(encoding="utf-8")

if '@app.get("/optimizer/site-verification/summary")' in source:
    print("Verification summary route already exists; no changes made.")
    raise SystemExit(0)

marker = '@app.post("/optimizer/site-verification/update")'
if marker not in source:
    raise SystemExit("Could not find insertion point. No changes made.")

backup = p.with_name("main.py.pre_site_verification_summary.bak")
backup.write_text(source, encoding="utf-8")

route = '''

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

'''

source = source.replace(marker, route + marker, 1)
p.write_text(source, encoding="utf-8")
print("Added /optimizer/site-verification/summary")
print(f"Backup: {backup}")
