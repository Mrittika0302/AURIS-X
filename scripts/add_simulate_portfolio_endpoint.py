from pathlib import Path

p = Path("frontend/backend/main.py")
source = p.read_text(encoding="utf-8")

if '@app.get("/optimizer/simulate-portfolio")' in source:
    print("Route already exists; no changes made.")
    raise SystemExit(0)

marker = '@app.get("/optimizer/candidates")'
if marker not in source:
    raise SystemExit("Could not find insertion point. No changes made.")

backup = p.with_name("main.py.pre_simulate_portfolio.bak")
backup.write_text(source, encoding="utf-8")

route = '''

@app.get("/optimizer/simulate-portfolio")
def optimizer_simulate_portfolio(site_ids: str):
    """Run joint accessibility simulation for selected healthcare candidate sites."""
    import json
    import subprocess
    import sys
    from pathlib import Path
    from fastapi import HTTPException

    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "evaluate_healthcare_portfolio.py"
    if not script.exists():
        raise HTTPException(status_code=404, detail="Portfolio simulation script not found.")

    ids = [item.strip() for item in site_ids.split(",") if item.strip()]
    if not ids:
        raise HTTPException(status_code=422, detail="Supply comma-separated site_ids.")
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=422, detail="Duplicate site IDs are not allowed.")
    if len(ids) > 100:
        raise HTTPException(status_code=422, detail="At most 100 site IDs may be simulated.")

    try:
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--site-ids",
                ",".join(ids),
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Portfolio simulation exceeded 600 seconds.")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not launch simulation: {exc}")

    if result.returncode != 0:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Portfolio simulation failed.",
                "stderr": result.stderr[-5000:],
                "stdout": result.stdout[-2000:],
            },
        )

    try:
        payload = json.loads(result.stdout)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Simulation did not return valid JSON.",
                "stdout": result.stdout[-3000:],
                "stderr": result.stderr[-3000:],
            },
        )

    if payload.get("status") != "PASS":
        raise HTTPException(status_code=500, detail="Simulation did not report PASS.")
    return payload

'''

source = source.replace(marker, route + marker, 1)
p.write_text(source, encoding="utf-8")
print("Added /optimizer/simulate-portfolio")
print(f"Backup: {backup}")
