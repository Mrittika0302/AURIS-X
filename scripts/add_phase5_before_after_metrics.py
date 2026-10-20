from pathlib import Path

p = Path("scripts/evaluate_healthcare_portfolio.py")
source = p.read_text(encoding="utf-8")

old = '''            "mean_distance_reduction_m_among_baseline_reachable": (
                round(float(delta[baseline_reachable].mean()), 3)
                if baseline_reachable.any() else None
            ),
            "mean_distance_reduction_m_all_comparable_cells": (
                round(float(delta[valid].mean()), 3) if valid.any() else None
            ),'''

new = '''            "mean_baseline_distance_m_among_baseline_reachable": (
                round(float(base[baseline_reachable].mean()), 3)
                if baseline_reachable.any() else None
            ),
            "mean_portfolio_distance_m_among_baseline_reachable": (
                round(float(new[baseline_reachable].mean()), 3)
                if baseline_reachable.any() else None
            ),
            "mean_distance_reduction_m_among_baseline_reachable": (
                round(float(delta[baseline_reachable].mean()), 3)
                if baseline_reachable.any() else None
            ),
            "mean_baseline_distance_m_all_comparable_cells": (
                round(float(base[valid].mean()), 3) if valid.any() else None
            ),
            "mean_portfolio_distance_m_all_comparable_cells": (
                round(float(new[valid].mean()), 3) if valid.any() else None
            ),
            "mean_distance_reduction_m_all_comparable_cells": (
                round(float(delta[valid].mean()), 3) if valid.any() else None
            ),'''

if old not in source:
    raise SystemExit("Expected metrics block not found. No changes made.")

backup = p.with_name("evaluate_healthcare_portfolio.py.pre_phase5_before_after.bak")
backup.write_text(source, encoding="utf-8")
p.write_text(source.replace(old, new, 1), encoding="utf-8")
print("Added baseline and portfolio mean-distance metrics.")
print(f"Backup: {backup}")
