
import json
from pathlib import Path

import networkx as nx
import pandas as pd
from scipy.spatial import cKDTree
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
MATCHES = ROOT / "data/silver/healthcare_network_matches_20261011_122708.csv"
OUT = ROOT / "reports/disconnected_nearest_main_network.csv"

GRAPHS = {
    "driving": (
        ROOT / "data/raw/roads_osm_20261011_115925.graphml",
        "drive_nearest_node_id",
    ),
    "walking": (
        ROOT / "data/raw/roads_walking_osm_20261011_122708.graphml",
        "walk_nearest_node_id",
    ),
}

# UTM zone 43N, appropriate for projected distance calculations here.
transformer = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)


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
    results = []

    for mode, (path, node_column) in GRAPHS.items():
        graph = nx.read_graphml(path)
        components = list(nx.weakly_connected_components(graph))
        largest = max(components, key=len)
        node_lookup = {norm_id(n): n for n in graph.nodes}

        main_nodes = list(largest)
        main_xy = []

        for node in main_nodes:
            x = float(graph.nodes[node]["x"])
            y = float(graph.nodes[node]["y"])
            east, north = transformer.transform(x, y)
            main_xy.append((east, north))

        tree = cKDTree(main_xy)

        for _, row in df.iterrows():
            matched_id = norm_id(row[node_column])
            matched_node = node_lookup.get(matched_id)

            if matched_node is None or matched_node in largest:
                continue

            lon = float(graph.nodes[matched_node]["x"])
            lat = float(graph.nodes[matched_node]["y"])
            east, north = transformer.transform(lon, lat)

            distance, index = tree.query((east, north), k=1)
            nearest_main_node = main_nodes[int(index)]

            results.append({
                "network": mode,
                "name": row.get("name", ""),
                "category": row.get("category", ""),
                "osm_id": row.get("osm_id", ""),
                "facility_latitude": row.get("latitude", ""),
                "facility_longitude": row.get("longitude", ""),
                "matched_node_id": matched_id,
                "nearest_main_node_id": str(nearest_main_node),
                "nearest_main_node_latitude": graph.nodes[nearest_main_node]["y"],
                "nearest_main_node_longitude": graph.nodes[nearest_main_node]["x"],
                "straight_line_gap_to_main_network_m": round(float(distance), 2),
                "main_component_nodes": len(largest),
                "warning": (
                    "Candidate connection only; inspect roads and access before "
                    "considering any graph repair."
                ),
            })

    OUT.parent.mkdir(exist_ok=True)
    pd.DataFrame(results).to_csv(OUT, index=False)

    print("Records analysed:", len(results))
    if results:
        print(pd.DataFrame(results).to_string(index=False))
    print("Saved:", OUT)


if __name__ == "__main__":
    main()
