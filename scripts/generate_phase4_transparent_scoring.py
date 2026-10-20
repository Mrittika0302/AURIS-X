from pathlib import Path
from datetime import datetime, timezone
import json

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "data/gold/healthcare_candidate_sites.csv"
IMPACTS = ROOT / "reports/candidate_impact_top10_20261012.csv"
OUT_DIR = ROOT / "reports"

WEIGHTS = {
    "gap_score": 0.40,
    "unreachable_score": 0.20,
    "distance_score": 0.25,
    "demand_proxy_score": 0.10,
    "snap_review_score": 0.05,
}

def main():
    if not CANDIDATES.exists():
        raise FileNotFoundError(f"Missing candidate file: {CANDIDATES}")

    df = pd.read_csv(CANDIDATES)
    required = ["rank", "candidate_zone_id", "screening_score", *WEIGHTS.keys()]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Candidate file missing required columns: {missing}")

    if df["candidate_zone_id"].duplicated().any():
        raise ValueError("Duplicate candidate_zone_id values; refusing ambiguous report.")

    for col in required:
        if col != "candidate_zone_id":
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Preserve the original rank and score; independently reconstruct the
    # documented weighted score to expose discrepancies rather than hide them.
    for component, weight in WEIGHTS.items():
        df[f"{component}_weight"] = weight
        df[f"{component}_contribution"] = df[component] * weight

    contribution_cols = [f"{c}_contribution" for c in WEIGHTS]
    df["reconstructed_score"] = df[contribution_cols].sum(axis=1, min_count=len(contribution_cols))
    df["score_difference"] = df["screening_score"] - df["reconstructed_score"]
    df["score_reconstruction_matches"] = df["score_difference"].abs() <= 0.02

    if "assumed_site_cost" in df.columns:
        df["assumed_site_cost"] = pd.to_numeric(df["assumed_site_cost"], errors="coerce")

    # Attach existing single-candidate impact evidence when a matching ID exists.
    # These are not portfolio impacts and are not used to alter the score.
    impact_count = 0
    if IMPACTS.exists():
        impacts = pd.read_csv(IMPACTS)
        if "candidate_zone_id" in impacts.columns:
            impacts = impacts.drop_duplicates("candidate_zone_id", keep="first")
            impact_cols = [
                "candidate_zone_id",
                "driving_cells_improved_over_1m",
                "walking_cells_improved_over_1m",
                "driving_cells_moved_to_5km_or_less",
                "walking_cells_moved_to_5km_or_less",
                "driving_mean_reduction_among_baseline_reachable_m",
                "walking_mean_reduction_among_baseline_reachable_m",
            ]
            available = [c for c in impact_cols if c in impacts.columns]
            impact_count = len(available) - 1
            if len(available) > 1:
                df = df.merge(impacts[available], on="candidate_zone_id", how="left")
    df["has_saved_single_site_impact_evidence"] = (
        df.get("driving_cells_improved_over_1m", pd.Series(index=df.index, dtype=float)).notna()
        if "driving_cells_improved_over_1m" in df.columns
        else False
    )

    def flags(row):
        result = []
        if "buildable_land_verified" in row.index and str(row["buildable_land_verified"]).casefold() not in ("true", "1"):
            result.append("Buildable land not verified")
        if "population_units_verified" in row.index and str(row["population_units_verified"]).casefold() not in ("true", "1"):
            result.append("Population units not verified")
        if not bool(row["has_saved_single_site_impact_evidence"]):
            result.append("No matched saved single-site impact evidence")
        result.append("Score is a relative heuristic, not incremental benefit")
        result.append("Single-site impacts must not be added to estimate portfolio impact")
        return "; ".join(result)

    df["interpretation_and_review_flags"] = df.apply(flags, axis=1)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / f"phase4_transparent_scoring_{stamp}.csv"
    json_path = OUT_DIR / f"phase4_transparent_scoring_{stamp}.json"

    df = df.sort_values("rank", kind="stable")
    df.to_csv(csv_path, index=False)

    report = {
        "status": "PASS",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate_count": int(len(df)),
        "weights": WEIGHTS,
        "score_formula": "sum(component_score * component_weight)",
        "score_reconstruction_matches": int(df["score_reconstruction_matches"].sum()),
        "score_reconstruction_mismatches": int((~df["score_reconstruction_matches"]).sum()),
        "candidates_with_matched_saved_single_site_impact": int(
            df["has_saved_single_site_impact_evidence"].sum()
        ),
        "impact_fields_attached": int(impact_count),
        "source_candidate_file": str(CANDIDATES.relative_to(ROOT)),
        "source_impact_file": str(IMPACTS.relative_to(ROOT)) if IMPACTS.exists() else None,
        "output_csv": str(csv_path.relative_to(ROOT)),
        "interpretation": [
            "Screening score is relative and heuristic, not incremental benefit or a validated probability.",
            "Component contributions explain the existing score; they do not establish causal effects.",
            "Saved impact values are single-site simulations and are not summed into portfolio impact.",
            "A missing impact match means evidence is unavailable in the selected source, not that impact is zero.",
            "Population units and buildable land remain unverified unless source evidence establishes otherwise.",
        ],
    }
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    print("\nTOP 10 — TRANSPARENT SCORE BREAKDOWN")
    cols = [
        "rank", "candidate_zone_id", "screening_score",
        *[f"{c}_contribution" for c in WEIGHTS],
        "reconstructed_score", "score_reconstruction_matches",
        "has_saved_single_site_impact_evidence",
    ]
    print(df[[c for c in cols if c in df.columns]].head(10).to_string(index=False))
    print(f"\nCSV: {csv_path}")
    print(f"JSON: {json_path}")

if __name__ == "__main__":
    main()
