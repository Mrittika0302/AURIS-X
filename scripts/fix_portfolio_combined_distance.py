from pathlib import Path

p = Path("scripts/evaluate_healthcare_portfolio.py")
s = p.read_text(encoding="utf-8")

old = '''    cells["portfolio_driving_distance_m"] = cells[drive_node_col].map(
        lambda x: drive_to_site.get(node_key(x), math.nan)
    )
    cells["portfolio_walking_distance_m"] = cells[walk_node_col].map(
        lambda x: walk_to_site.get(node_key(x), math.nan)
    )'''

new = '''    # Keep proposed-site-only distances for auditability.
    cells["proposed_sites_driving_distance_m"] = cells[drive_node_col].map(
        lambda x: drive_to_site.get(node_key(x), math.nan)
    )
    cells["proposed_sites_walking_distance_m"] = cells[walk_node_col].map(
        lambda x: walk_to_site.get(node_key(x), math.nan)
    )

    # Adding sites cannot remove access to existing facilities.
    # Combined distance is the better of baseline access and proposed-site access.
    cells["portfolio_driving_distance_m"] = pd.concat(
        [
            cells["baseline_driving_distance_m"],
            cells["proposed_sites_driving_distance_m"],
        ],
        axis=1,
    ).min(axis=1, skipna=True)
    cells["portfolio_walking_distance_m"] = pd.concat(
        [
            cells["baseline_walking_distance_m"],
            cells["proposed_sites_walking_distance_m"],
        ],
        axis=1,
    ).min(axis=1, skipna=True)'''

if old not in s:
    raise SystemExit(
        "Expected distance-assignment block not found. No changes made; inspect the script before retrying."
    )

backup = p.with_name("evaluate_healthcare_portfolio.py.pre_combined_distance.bak")
if not backup.exists():
    backup.write_text(s, encoding="utf-8")

s = s.replace(old, new, 1)

# Include proposed-site-only distances in the detail output.
old_keep = '''        "baseline_driving_distance_m", "portfolio_driving_distance_m",
        "baseline_walking_distance_m", "portfolio_walking_distance_m",'''
new_keep = '''        "baseline_driving_distance_m", "proposed_sites_driving_distance_m",
        "portfolio_driving_distance_m",
        "baseline_walking_distance_m", "proposed_sites_walking_distance_m",
        "portfolio_walking_distance_m",'''
if old_keep not in s:
    raise SystemExit(
        "Distance assignment patched in memory, but output-column block was not found. No changes written."
    )
s = s.replace(old_keep, new_keep, 1)

p.write_text(s, encoding="utf-8")
print("Patched combined existing-plus-proposed distance calculation.")
print(f"Backup: {backup}")
