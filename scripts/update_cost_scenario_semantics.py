from pathlib import Path

p = Path("frontend/backend/main.py")
source = p.read_text(encoding="utf-8")

start = source.find('@app.get("/optimizer/cost-scenarios")')
if start < 0:
    raise SystemExit("Cost-scenarios route not found. No changes made.")

end = source.find("\n@app.get(", start + 1)
if end < 0:
    end = len(source)

route = source[start:end]
if '"cost_source": "caller_supplied_assumption"' in route:
    print("Cost scenario labels already present; no changes made.")
    raise SystemExit(0)

old_cost = '''            "cost_is_verified": False,
        })'''
new_cost = '''            "cost_is_verified": False,
            "cost_source": "caller_supplied_assumption",
            "evidence_used_for_per_site_cost": False,
            "construction_cost_verified": False,
            "operating_cost_included": False,
            "lifecycle_cost_included": False,
        })'''

if old_cost not in route:
    raise SystemExit("Expected scenario block not found. No changes made.")

route = route.replace(old_cost, new_cost, 1)

old_response = '''        "budget": budget,
        "scenarios": scenarios,'''
new_response = '''        "budget": budget,
        "scenario_cost_semantics": {
            "costs_are_user_supplied_assumptions": True,
            "official_evidence_register_used_as_site_cost": False,
            "verified_per_site_cost_available": False,
            "note": "Official budget and tender records are reference evidence only. None is approved as a comparable per-site construction cost.",
        },
        "scenarios": scenarios,'''

if old_response not in route:
    raise SystemExit("Expected response block not found. No changes made.")

route = route.replace(old_response, new_response, 1)

backup = p.with_name("main.py.pre_cost_scenario_semantics.bak")
if not backup.exists():
    backup.write_text(source, encoding="utf-8")

source = source[:start] + route + source[end:]
p.write_text(source, encoding="utf-8")

print("Updated cost scenario transparency.")
print(f"Backup: {backup}")
