
import json
from pathlib import Path

import networkx as nx
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MATCHES = ROOT / "data/silver/healthcare_network_matches_20261011_122708.csv"
OUT = ROOT / "reports/disconnected_component_details.json"

GRAPHS = {
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


def main():
    df = pd.read_csv(MATCHES, dtype=str).fillna("")
    report = {}

    for mode, (path, node_col, snap_col) in GRAPHS.items():
        graph = nx.read_graphml(path)
        components = list(nx.weakly_connected_components(graph))
        largest = max(components, key=len)
        component_by_node = {
            node: component
            for component in components
            for node in component
        }
        lookup = {norm_id(n): n for n in graph.nodes}
        rows = []

        for _, row in df.iterrows():
            node = lookup.get(norm_id(row[node_col]))
            if node is None or node in largest:
                continue

            component = component_by_node[node]
            component_nodes = list(component)
            xs = [
                float(graph.nodes[n]["x"])
                for n in component_nodes
                if "x" in graph.nodes[n]
            ]
            ys = [
                float(graph.nodes[n]["y"])
                for n in component_nodes
                if "y" in graph.nodes[n]
            ]

            rows.append({
                "name": row.get("name", ""),
                "category": row.get("category", ""),
                "osm_id": row.get("osm_id", ""),
                "matched_node_id": str(node),
                "snap_distance_m": row.get(snap_col, ""),
                "component_nodes": len(component),
                "component_edges": graph.subgraph(component).number_of_edges(),
                "component_lon_min": min(xs) if xs else None,
                "component_lon_max": max(xs) if xs else None,
                "component_lat_min": min(ys) if ys else None,
                "component_lat_max": max(ys) if ys else None,
            })

        report[mode] = rows

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    for mode, rows in report.items():
        print(f"\n=== {mode.upper()} ===")
        for row in rows:
            print(
                f"{row['name'] or '(unnamed)'} | "
                f"component nodes={row['component_nodes']} | "
                f"edges={row['component_edges']} | "
                f"snap={row['snap_distance_m']} m"
            )

    print(f"\nSaved report: {OUT}")


if __name__ == "__main__":
    main()
