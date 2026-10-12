
import json
from pathlib import Path

import networkx as nx
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MATCHES = ROOT / "data/silver/healthcare_network_matches_20261011_122708.csv"
OUT = ROOT / "reports/disconnected_healthcare_facilities.csv"

df = pd.read_csv(MATCHES, dtype=str).fillna("")
results = []

graphs = {
    "driving": (
        ROOT / "data/raw/roads_osm_20261011_115925.graphml",
        "drive_nearest_node_id",
        "drive_snap_distance_m",
    ),
    "walking": (
        ROOT / "data/raw/roads_walking_osm_20261011_122708.graphml",
        "walk_nearest_node_id",
        "walk_snap_distance_m",
    ),
}


def norm_id(value):
    try:
        number = float(str(value).strip())
        if number.is_integer():
            return str(int(number))
    except (ValueError, TypeError, OverflowError):
        pass
    return str(value).strip()


for mode, (path, node_col, snap_col) in graphs.items():
    graph = nx.read_graphml(path)
    components = list(nx.weakly_connected_components(graph))
    largest = max(components, key=len)
    component_by_node = {
        node: index
        for index, component in enumerate(components)
        for node in component
    }
    largest_nodes = set(largest)
    lookup = {norm_id(node): node for node in graph.nodes}

    for _, row in df.iterrows():
        node = lookup.get(norm_id(row[node_col]))
        if node is None or node in largest_nodes:
            continue

        results.append({
            "network": mode,
            "name": row.get("name", ""),
            "category": row.get("category", ""),
            "osm_id": row.get("osm_id", ""),
            "latitude": row.get("latitude", ""),
            "longitude": row.get("longitude", ""),
            "matched_node_id": row[node_col],
            "snap_distance_m": row[snap_col],
            "component_id": component_by_node.get(node),
        })

OUT.parent.mkdir(exist_ok=True)
pd.DataFrame(results).to_csv(OUT, index=False)

print("Disconnected facility records:", len(results))
print("Unique facilities affected:", len({
    (r["network"], r["osm_id"]) for r in results
}))
print("Saved:", OUT)

if results:
    print(pd.DataFrame(results).to_string(index=False))
else:
    print("No facilities outside the largest component.")
