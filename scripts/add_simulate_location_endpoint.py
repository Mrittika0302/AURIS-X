from pathlib import Path

p = Path("frontend/backend/main.py")
source = p.read_text(encoding="utf-8")

if '@app.get("/optimizer/simulate-location")' in source:
    print("Route already exists; no changes needed.")
    raise SystemExit(0)

marker = '@app.get("/optimizer/candidates")'
if marker not in source:
    raise SystemExit("Could not find insertion point. No changes made.")

backup = p.with_name("main.py.pre_simulate_location.bak")
backup.write_text(source, encoding="utf-8")

route = '''

@app.get("/optimizer/simulate-location")
def simulate_location(latitude: float, longitude: float):
    """Run a fresh healthcare driving/walking network-distance simulation."""
    import json
    import subprocess
    import sys
    from pathlib import Path

    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise HTTPException(status_code=422, detail="Invalid latitude or longitude.")

    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "evaluate_proposed_healthcare_location.py"
    if not script.exists():
        raise HTTPException(status_code=500, detail="Simulation script not found.")

    try:
        result = subprocess.run(
            [
                sys.executable, str(script),
                "--latitude", str(latitude),
                "--longitude", str(longitude),
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Simulation exceeded the 10-minute API timeout.")

    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Fresh accessibility simulation failed.",
                "stderr": result.stderr[-4000:],
                "stdout": result.stdout[-2000:],
            },
        )

    try:
        start = result.stdout.find("{")
        if start < 0:
            raise ValueError("No JSON report found in simulation output.")
        report, _ = json.JSONDecoder().raw_decode(result.stdout[start:])
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=f"Could not parse simulation report: {exc}")

    return report

'''

source = source.replace(marker, route + marker, 1)
p.write_text(source, encoding="utf-8")
print("Added /optimizer/simulate-location")
print(f"Backup saved to {backup}")
