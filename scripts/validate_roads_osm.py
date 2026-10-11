
import json
from pathlib import Path

import networkx as nx
import osmnx as ox

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
REPORT_DIR = PROJECT_ROOT / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

files = sorted(RAW_DIR.glob("roads_osm_*.graphml"))

if not files:
    raise FileNotFoundError("No roads_osm_*.graphml file found in data/raw")

graph_path = files[-1]
print(f"Validating: {graph_path.name}")

graph = ox.load_graphml(graph_path)

nodes = list(graph.nodes(data=True))
edges = list(graph.edges(data=True))

node_ids = {node_id for node_id, _ in nodes}
missing_coordinates = 0
invalid_coordinates = 0

for node_id, attrs in nodes:
    try:
        x = float(attrs["x"])
        y = float(attrs["y"])
        if not (-180 <= x <= 180 and -90 <= y <= 90):
            invalid_coordinates += 1
    except (KeyError, TypeError, ValueError):
        missing_coordinates += 1

missing_lengths = 0
invalid_lengths = 0

for u, v, attrs in edges:
    if u not in node_ids or v not in node_ids:
        invalid_lengths += 1
        continue

    try:
        length = float(attrs["length"])
        if length <= 0:
            invalid_lengths += 1
    except (KeyError, TypeError, ValueError):
        missing_lengths += 1

weak_components = nx.number_weakly_connected_components(graph)
strong_components = nx.number_strongly_connected_components(graph)

report = {
    "dataset": graph_path.name,
    "node_count": len(nodes),
    "directed_edge_count": len(edges),
    "nodes_missing_coordinates": missing_coordinates,
    "nodes_with_invalid_coordinates": invalid_coordinates,
    "edges_missing_length": missing_lengths,
    "edges_with_invalid_length_or_endpoints": invalid_lengths,
    "weakly_connected_components": weak_components,
    "strongly_connected_components": strong_components,
    "checks": {
        "has_nodes": len(nodes) > 0,
        "has_edges": len(edges) > 0,
        "all_nodes_have_coordinates": missing_coordinates == 0,
        "all_coordinates_in_valid_ranges": invalid_coordinates == 0,
        "all_edges_have_positive_lengths": (
            missing_lengths == 0 and invalid_lengths == 0
        ),
    },
    "limitations": [
        "Structural checks do not prove real-world road completeness.",
        "Connected components may reflect one-way streets, access rules, or data gaps.",
        "Edge lengths are not validated travel times.",
        "Study boundary is an approximate bounding box, not an official boundary.",
    ],
}

report_path = REPORT_DIR / "roads_validation_report.json"
report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

print("\nVALIDATION RESULTS")
print(f"Nodes: {len(nodes)}")
print(f"Directed edges: {len(edges)}")
print(f"Missing coordinates: {missing_coordinates}")
print(f"Invalid coordinates: {invalid_coordinates}")
print(f"Edges missing length: {missing_lengths}")
print(f"Edges with invalid length/endpoints: {invalid_lengths}")
print(f"Weakly connected components: {weak_components}")
print(f"Strongly connected components: {strong_components}")
print(f"Report: {report_path}")
print("\nChecks:")
for name, passed in report["checks"].items():
    print(f"  {name}: {'PASS' if passed else 'FAIL'}")
