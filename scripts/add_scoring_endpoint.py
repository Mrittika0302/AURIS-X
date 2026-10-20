from pathlib import Path

p = Path("frontend/backend/main.py")
source = p.read_text(encoding="utf-8")

if '@app.get("/optimizer/scoring")' in source:
    print("Route already exists; no changes made.")
    raise SystemExit(0)

marker = '@app.get("/optimizer/candidates")'
if marker not in source:
    raise SystemExit("Could not find insertion point. No changes made.")

backup = p.with_name("main.py.pre_scoring_endpoint.bak")
backup.write_text(source, encoding="utf-8")

route = '''

@app.get("/optimizer/scoring")
def optimizer_scoring(limit: int = 20, offset: int = 0):
    """Return the latest saved transparent candidate scoring breakdown."""
    import json
    from pathlib import Path
    import pandas as pd
    from fastapi import HTTPException

    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 100.")
    if offset < 0:
        raise HTTPException(status_code=422, detail="offset must be zero or greater.")

    root = Path(__file__).resolve().parents[2]
    reports = root / "reports"
    files = sorted(
        reports.glob("phase4_transparent_scoring_*.csv"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise HTTPException(
            status_code=404,
            detail="No transparent scoring report found. Run scripts/generate_phase4_transparent_scoring.py first.",
        )

    csv_path = files[0]
    json_path = csv_path.with_suffix(".json")
    try:
        df = pd.read_csv(csv_path)
        metadata = json.loads(json_path.read_text(encoding="utf-8")) if json_path.exists() else {}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read scoring report: {exc}")

    total = len(df)
    page = df.iloc[offset:offset + limit].copy()
    page = page.astype(object).where(pd.notna(page), None)

    return {
        "status": "PASS",
        "source_file": csv_path.name,
        "metadata": metadata,
        "total_candidates": total,
        "limit": limit,
        "offset": offset,
        "candidates": page.to_dict(orient="records"),
        "interpretation": [
            "Scores are relative heuristic screening scores, not validated probabilities or incremental public benefit.",
            "Component contributions explain the saved score; they do not prove causal effects.",
            "Missing saved impact evidence is not equivalent to zero impact.",
            "Population units and buildable land remain unverified unless independently established.",
        ],
    }

'''

source = source.replace(marker, route + marker, 1)
p.write_text(source, encoding="utf-8")
print("Added /optimizer/scoring")
print(f"Backup: {backup}")
