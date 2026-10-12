
import json
from pathlib import Path

import networkx as nx
import osmnx as ox
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)

GRAPH_FILES = {
    "driving": ROOT / "data/raw/roads_osm_20261011_115925.graphml",
    "walking": ROOT / "data/raw/roads_walking_osm_20261011_122708.graphml",
}

MATCHES_FILE = (
    ROOT / "data/silver/healthcare_network_matches_20261011_122708.csv"
)

OUTPUT_CSV = REPORTS / "road_fragment_review_candidates.csv"
OUTPUT_JSON = REPORTS / "road_fragment_review_summary.json"

transformer = Transformer.from_crs(
    "EPSG:4326", "EPSG:32643", always_xy=True
)


def normalize_id(value):
    """Normalize numeric IDs read from CSV and GraphML."""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def main():
    matches = pd.read_csv(MATCHES_FILE, dtype=str)
    matches.columns = matches.columns.str.strip()

    all_rows = []
    summary = {}

    for network, graph_path in GRAPH_FILES.items():
        print(f"\nLoading {network} graph...")
        graph = ox.load_graphml(graph_path)

        # Build a normalized-ID lookup to avoid string/int/float mismatches.
        graph_id_lookup = {}
        for graph_node in graph.nodes:
            normalized = normalize_id(graph_node)
            graph_id_lookup.setdefault(normalized, graph_node)

        components = list(nx.weakly_connected_components(graph))
        largest_component = max(components, key=len)
        main_nodes = list(largest_component)

        node_component_size = {}
        for component in components:
            for node in component:
                node_component_size[node] = len(component)

        projected_main_nodes = [
            transformer.transform(
                float(graph.nodes[node]["x"]),
                float(graph.nodes[node]["y"]),
            )
            for node in main_nodes
        ]
        tree = cKDTree(projected_main_nodes)

        match_column = (
            "drive_nearest_node_id"
            if network == "driving"
            else "walk_nearest_node_id"
        )

        disconnected_records = 0
        missing_records = 0
        disconnected_node_ids = set()

        for _, facility in matches.iterrows():
            raw_id = facility.get(match_column, "")
            normalized_id = normalize_id(raw_id)

            # Match using normalized IDs, then retain the graph's real ID.
            graph_node = graph_id_lookup.get(normalized_id)

            if graph_node is None:
                missing_records += 1
                all_rows.append({
                    "network": network,
                    "osm_id": facility.get("osm_id", ""),
                    "name": facility.get("name", ""),
                    "category": facility.get("category", ""),
                    "matched_node_id_csv": raw_id,
                    "review_status": "MATCHED_NODE_NOT_IN_GRAPH",
                    "warning": (
                        "No normalized ID match. Check IDs before "
                        "considering any network repair."
                    ),
                })
                continue

            if graph_node in largest_component:
                continue

            disconnected_records += 1
            disconnected_node_ids.add(str(graph_node))

            latitude = float(facility["latitude"])
            longitude = float(facility["longitude"])

            facility_x, facility_y = transformer.transform(
                longitude, latitude
            )

            distance, nearest_index = tree.query(
                [facility_x, facility_y]
            )
            candidate_node = main_nodes[int(nearest_index)]
            candidate_data = graph.nodes[candidate_node]

            if graph.is_directed():
                incident_edges = (
                    list(graph.in_edges(graph_node, data=True))
                    + list(graph.out_edges(graph_node, data=True))
                )
            else:
                incident_edges = list(
                    graph.edges(graph_node, data=True)
                )

            edge_details = []
            for source, target, data in incident_edges[:30]:
                edge_details.append({
                    "from_node": str(source),
                    "to_node": str(target),
                    "length_m": data.get("length"),
                    "highway": data.get("highway"),
                    "name": data.get("name"),
                    "access": data.get("access"),
                    "geometry_present": data.get("geometry") is not None,
                })

            all_rows.append({
                "network": network,
                "osm_id": facility.get("osm_id", ""),
                "name": facility.get("name", ""),
                "category": facility.get("category", ""),
                "latitude": latitude,
                "longitude": longitude,
                "matched_node_id": str(graph_node),
                "matched_component_nodes": node_component_size[graph_node],
                "candidate_main_node_id": str(candidate_node),
                "candidate_main_node_latitude": candidate_data["y"],
                "candidate_main_node_longitude": candidate_data["x"],
                "facility_to_main_node_straight_line_m": round(
                    float(distance), 2
                ),
                "isolated_node_incident_edges_json": json.dumps(
                    edge_details, ensure_ascii=False
                ),
                "review_status": "REVIEW_REQUIRED",
                "warning": (
                    "Straight-line distance is not proof of a road link. "
                    "Inspect the mapped roads before any repair."
                ),
            })

        summary[network] = {
            "graph_nodes": graph.number_of_nodes(),
            "graph_edges": graph.number_of_edges(),
            "weak_components": len(components),
            "largest_component_nodes": len(largest_component),
            "facility_records_checked": len(matches),
            "disconnected_facility_records": disconnected_records,
            "distinct_disconnected_matched_nodes": len(
                disconnected_node_ids
            ),
            "matched_nodes_missing_from_graph": missing_records,
        }

        print(f"Graph nodes: {graph.number_of_nodes():,}")
        print(f"Weak components: {len(components):,}")
        print(f"Disconnected facility records: {disconnected_records}")
        print(f"Matched nodes missing from graph: {missing_records}")

    pd.DataFrame(all_rows).to_csv(
        OUTPUT_CSV, index=False, encoding="utf-8-sig"
    )

    with open(OUTPUT_JSON, "w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2, ensure_ascii=False)

    print("\n========== SUMMARY ==========")
    print(json.dumps(summary, indent=2))
    print(f"\nCSV saved: {OUTPUT_CSV}")
    print(f"JSON saved: {OUTPUT_JSON}")
    print("\nOriginal road graphs were not modified.")


if __name__ == "__main__":
    main()
