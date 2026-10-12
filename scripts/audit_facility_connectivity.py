
import json
from pathlib import Path

import networkx as nx
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)

MATCHES = ROOT / "data/silver/healthcare_network_matches_20261011_122708.csv"

GRAPHS = {
    "driving": ROOT / "data/raw/roads_osm_20261011_115925.graphml",
    "walking": ROOT / "data/raw/roads_walking_osm_20261011_122708.graphml",
}


def norm_id(value):
    if pd.isna(value):
        return None
    value = str(value).strip()
    try:
        f = float(value)
        if f.is_integer():
            return str(int(f))
    except (ValueError, OverflowError):
        pass
    return value


def main():
    df = pd.read_csv(MATCHES, dtype=str).fillna("")
    results = {}

    for mode, graph_path in GRAPHS.items():
        graph = nx.read_graphml(graph_path)

        if mode == "driving":
            column = "drive_nearest_node_id"
        else:
            column = "walk_nearest_node_id"

        if column not in df.columns:
            raise ValueError(f"Missing required column: {column}")

        node_lookup = {norm_id(node): node for node in graph.nodes}
        components = list(nx.weakly_connected_components(graph))
        component_by_node = {}

        for component_index, component in enumerate(components):
            for node in component:
                component_by_node[node] = component_index

        component_sizes = sorted(
            (len(component) for component in components),
            reverse=True,
        )
        facility_component_counts = {}

        missing = []
        for _, row in df.iterrows():
            node_id = norm_id(row[column])
            graph_node = node_lookup.get(node_id)

            if graph_node is None:
                missing.append({
                    "name": row.get("name", ""),
                    "osm_id": row.get("osm_id", ""),
                    "matched_node_id": node_id,
                })
                continue

            component_index = component_by_node[graph_node]
            facility_component_counts[str(component_index)] = (
                facility_component_counts.get(str(component_index), 0) + 1
            )

        results[mode] = {
            "graph_nodes": graph.number_of_nodes(),
            "weak_components": len(components),
            "largest_component_nodes": component_sizes[0],
            "facilities_missing_from_graph": len(missing),
            "facilities_in_largest_component": sum(
                count for component, count in facility_component_counts.items()
                if len(components[int(component)]) == component_sizes[0]
            ),
            "distinct_components_containing_facilities": len(
                facility_component_counts
            ),
            "facility_counts_by_component": facility_component_counts,
            "unmatched_facilities": missing,
        }

    output = REPORTS / "facility_connectivity_audit.json"
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print(json.dumps(results, indent=2))
    print(f"\nSaved report: {output}")


if __name__ == "__main__":
    main()
