from pathlib import Path

p = Path("frontend/backend/main.py")
s = p.read_text(encoding="utf-8")

replacements = [
(
'''            lat = float(row.get("centroid_latitude", ""))
            lon = float(row.get("centroid_longitude", ""))''',
'''            lat = float(row.get("centroid_latitude") or row.get("latitude") or "")
            lon = float(row.get("centroid_longitude") or row.get("longitude") or "")'''
),
(
'''            "latitude": float(candidate["centroid_latitude"]),
            "longitude": float(candidate["centroid_longitude"]),''',
'''            "latitude": float(candidate.get("centroid_latitude") or candidate.get("latitude")),
            "longitude": float(candidate.get("centroid_longitude") or candidate.get("longitude")),'''
),
(
'''    cost = number(candidate, "assumed_site_cost", "assumed_cost")''',
'''    cost = number(candidate, "assumed_site_cost", "assumed_cost", "cost")'''
),
(
'''        "driving_mean_reduction_among_baseline_reachable_m",
        "walking_mean_reduction_among_baseline_reachable_m",''',
'''        "driving_mean_reduction_among_baseline_reachable_m",
        "walking_mean_reduction_among_baseline_reachable_m",
        "driving_mean_distance_reduction_m",
        "walking_mean_distance_reduction_m",
        "drive_snap_m",
        "walk_snap_m",
        "snap_review",
        "pros",
        "cons",'''
),
(
'''            None,
        )

    score = number(candidate, "screening_score", "priority_score")''',
'''            None,
        )
    if impact is None:
        # The comparison CSV already contains saved single-site impact evidence.
        impact = candidate

    score = number(candidate, "screening_score", "priority_score")'''
)
]

for old, new in replacements:
    if old not in s:
        raise SystemExit("Expected code block not found; no file changes written.")
    s = s.replace(old, new, 1)

backup = p.with_suffix(".py.before_location_schema_fix.bak")
backup.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
p.write_text(s, encoding="utf-8")
print(f"Updated {p}; backup saved to {backup}")
