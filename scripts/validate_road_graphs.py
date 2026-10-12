
import json
import statistics
from pathlib import Path

import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)

GRAPHS = {
    "driving": ROOT / "data/raw/roads_osm_20261011_115925.graphml",
    "walking": ROOT / "data/raw/roads_walking_osm_20261011_122708.graphml",
}


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def inspect_graph(name, path):
    graph = nx.read_graphml(path)
    nodes = list(graph.nodes(data=True))
    edges = list(graph.edges(data=True))

    xs, ys = [], []
    missing_coords = 0

    for _, attrs in nodes:
        x = number(attrs.get("x"))
        y = number(attrs.get("y"))
        if x is None or y is None:
            missing_coords += 1
        else:
            xs.append(x)
            ys.append(y)

    lengths = []
    missing_lengths = 0
    nonpositive_lengths = 0

    for _, _, attrs in edges:
        length = number(attrs.get("length"))
        if length is None:
            missing_lengths += 1
        else:
            lengths.append(length)
            if length <= 0:
                nonpositive_lengths += 1

    if graph.is_directed():
        weak_components = nx.number_weakly_connected_components(graph)
        strong_components = nx.number_strongly_connected_components(graph)
        largest_weak = max(
            (len(c) for c in nx.weakly_connected_components(graph)),
            default=0,
        )
    else:
        weak_components = nx.number_connected_components(graph)
        strong_components = None
        largest_weak = max(
            (len(c) for c in nx.connected_components(graph)),
            default=0,
        )

    return {
        "graph": name,
        "file": str(path.relative_to(ROOT)),
        "directed": graph.is_directed(),
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "nodes_missing_coordinates": missing_coords,
        "longitude_min": min(xs) if xs else None,
        "longitude_max": max(xs) if xs else None,
        "latitude_min": min(ys) if ys else None,
        "latitude_max": max(ys) if ys else None,
        "edges_missing_length": missing_lengths,
        "edges_nonpositive_length": nonpositive_lengths,
        "length_min_m": min(lengths) if lengths else None,
        "length_median_m": statistics.median(lengths) if lengths else None,
        "length_max_m": max(lengths) if lengths else None,
        "weak_or_connected_components": weak_components,
        "strongly_connected_components": strong_components,
        "largest_weak_component_nodes": largest_weak,
        "largest_component_node_share": (
            largest_weak / graph.number_of_nodes()
            if graph.number_of_nodes() else None
        ),
        "notes": (
            "Structural checks only. Component counts alone do not establish "
            "real-world road completeness, legal access, or travel times."
        ),
    }


def main():
    results = []

    for name, path in GRAPHS.items():
        if not path.exists():
            raise FileNotFoundError(f"Missing graph: {path}")
        results.append(inspect_graph(name, path))

    output = REPORTS / "road_graph_validation.json"
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")

    for result in results:
        print(f"\n=== {result['graph'].upper()} GRAPH ===")
        for key, value in result.items():
            if key not in ("graph", "notes"):
                print(f"{key}: {value}")
        print(result["notes"])

    print(f"\nSaved report: {output}")


if __name__ == "__main__":
    main()
