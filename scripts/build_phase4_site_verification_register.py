from pathlib import Path
import json
from datetime import datetime, timezone
import pandas as pd

root = Path(__file__).resolve().parents[1]
source = root / "data" / "gold" / "healthcare_candidate_sites.csv"
out_dir = root / "data" / "reference_site_evidence"
out_dir.mkdir(parents=True, exist_ok=True)

if not source.exists():
    raise SystemExit(f"Candidate source not found: {source}")

df = pd.read_csv(source)

def pick_column(options, required=True):
    for col in options:
        if col in df.columns:
            return col
    if required:
        raise SystemExit(f"Missing expected column. Tried {options}; found {list(df.columns)}")
    return None

id_col = pick_column(["candidate_zone_id"])
lat_col = pick_column(["centroid_latitude", "centroid_lat", "latitude", "lat"])
lon_col = pick_column(["centroid_longitude", "centroid_lon", "longitude", "lon", "lng"])
rank_col = pick_column(["rank"], required=False)
score_col = pick_column(["screening_score"], required=False)

rows = []
for _, item in df.iterrows():
    rows.append({
        "candidate_zone_id": str(item[id_col]),
        "model_rank": item[rank_col] if rank_col else None,
        "model_screening_score": item[score_col] if score_col else None,
        "model_centroid_latitude": item[lat_col],
        "model_centroid_longitude": item[lon_col],
        "coordinate_type": "model_generated_zone_centroid",
        "parcel_id": "",
        "survey_number": "",
        "land_owner_or_custodian": "",
        "land_ownership_verified": False,
        "parcel_boundary_verified": False,
        "field_visit_completed": False,
        "site_access_verified": False,
        "land_use_zone_verified": False,
        "healthcare_use_permitted_verified": False,
        "utilities_and_access_reviewed": False,
        "flood_and_environmental_constraints_reviewed": False,
        "buildable_land_verified": False,
        "verification_status": "NOT_VERIFIED",
        "reviewer": "",
        "review_date": "",
        "evidence_document_reference": "",
        "review_notes": "",
        "official_land_use_reference": "Coimbatore Master Plan 2041 maps and land-use schedule; verify applicable parcel",
        "official_gis_reference": "Tamil Nadu GIS (TNGIS); verify layer provenance and terms",
    })

register = pd.DataFrame(rows)
stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
csv_path = out_dir / "healthcare_candidate_site_verification_register.csv"
summary_path = root / "reports" / f"phase4_site_verification_register_{stamp}.json"
summary_path.parent.mkdir(parents=True, exist_ok=True)

register.to_csv(csv_path, index=False, encoding="utf-8-sig")

summary = {
    "status": "PASS",
    "created_utc": stamp,
    "candidate_count": len(register),
    "verified_parcels": int(register["buildable_land_verified"].sum()),
    "unverified_parcels": int((~register["buildable_land_verified"]).sum()),
    "register_csv": str(csv_path.relative_to(root)),
    "official_references": [
        {
            "name": "Coimbatore Master Plan 2041 downloads",
            "url": "https://coimbatorelpa.in/downloads/",
            "purpose": "Check official land-use maps and schedules against each actual parcel."
        },
        {
            "name": "Tamil Nadu GIS",
            "url": "https://tngis.tn.gov.in/apps.html",
            "purpose": "Find relevant spatial layers; verify data owner, currency, access conditions, and suitability."
        },
        {
            "name": "Coimbatore Corporation land-use regulation",
            "url": "https://ccmc.gov.in/index.php/createpage/regulation-of-land-use",
            "purpose": "Reference for applicable land-use and planning controls."
        }
    ],
    "important_note": "The script does not verify land. All verification flags start false and require documentary or field evidence.",
}
summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

print(json.dumps(summary, indent=2))
