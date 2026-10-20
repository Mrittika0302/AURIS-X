from pathlib import Path

p = Path("frontend/backend/main.py")
s = p.read_text(encoding="utf-8")

old = '    impact_path = latest_report("candidate_impact_top10_*.csv")'
new = '''    preferred_impact = REPORT_DIR / "candidate_impact_top10_20261012.csv"
    if preferred_impact.exists():
        impact_path = preferred_impact
    else:
        impact_files = sorted(
            (
                f for f in REPORT_DIR.glob("candidate_impact_top10_*.csv")
                if "audit" not in f.stem.casefold()
            ),
            key=lambda f: f.name,
            reverse=True,
        )
        impact_path = impact_files[0] if impact_files else None'''

if old not in s:
    raise SystemExit("Expected impact-path line not found; no changes made.")

backup = p.with_suffix(".py.before_impact_source_fix.bak")
backup.write_text(s, encoding="utf-8")
p.write_text(s.replace(old, new, 1), encoding="utf-8")
print(f"Updated impact source selection. Backup: {backup}")
