from pathlib import Path

p = Path("scripts/evaluate_healthcare_portfolio.py")
s = p.read_text(encoding="utf-8")

if "def haversine_m(" not in s:
    marker = "\ndef main():"
    helper = '''

def haversine_m(lat1, lon1, lat2, lon2):
    """Approximate straight-line distance in metres between two coordinates."""
    radius_m = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius_m * math.asin(min(1.0, math.sqrt(a)))
'''
    if marker not in s:
        raise SystemExit("Could not find main() insertion point; no changes made.")
    s = s.replace(marker, helper + marker, 1)

old_drive = '''        drive_snap_m = float(
            ox.distance.euclidean_dist_vec(
                lat, lon,
                drive_graph.nodes[drive_node]["y"],
                drive_graph.nodes[drive_node]["x"],
            )
        ) * 111000.0
        walk_snap_m = float(
            ox.distance.euclidean_dist_vec(
                lat, lon,
                walk_graph.nodes[walk_node]["y"],
                walk_graph.nodes[walk_node]["x"],
            )
        ) * 111000.0'''

new_drive = '''        drive_snap_m = haversine_m(
            lat, lon,
            float(drive_graph.nodes[drive_node]["y"]),
            float(drive_graph.nodes[drive_node]["x"]),
        )
        walk_snap_m = haversine_m(
            lat, lon,
            float(walk_graph.nodes[walk_node]["y"]),
            float(walk_graph.nodes[walk_node]["x"]),
        )'''

if old_drive in s:
    s = s.replace(old_drive, new_drive, 1)
elif "ox.distance.euclidean_dist_vec" in s:
    raise SystemExit("Found an unexpected distance-code layout; no changes written.")
else:
    print("Legacy OSMnx distance calls not found; checking whether patch was already applied.")

p.write_text(s, encoding="utf-8")
print("Updated approximate snap-distance calculation.")
