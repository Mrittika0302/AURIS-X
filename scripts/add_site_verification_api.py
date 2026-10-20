from pathlib import Path

p = Path("frontend/backend/main.py")
source = p.read_text(encoding="utf-8")

if '@app.get("/optimizer/site-verification")' in source:
    print("Site-verification routes already exist; no changes made.")
    raise SystemExit(0)

marker = '@app.get("/optimizer/candidates")'
if marker not in source:
    raise SystemExit("Could not find insertion point. No changes made.")

backup = p.with_name("main.py.pre_site_verification_api.bak")
backup.write_text(source, encoding="utf-8")

routes = '''

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

'''

source = source.replace(marker, routes + marker, 1)
p.write_text(source, encoding="utf-8")
print("Added site-verification read and update endpoints.")
print(f"Backup: {backup}")
