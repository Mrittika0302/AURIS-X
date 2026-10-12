
import json
import math
from pathlib import Path

import folium
import networkx as nx
import pandas as pd
import osmnx as ox
from pyproj import Transformer
from scipy.spatial import cKDTree


# ============================================================
# AURIS-X: DISCONNECTED ROAD REVIEW MAP
# Tile-free map: no external basemap requests required.
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = BASE_DIR / "reports"
DATA_DIR = BASE_DIR / "data"

MATCHES_FILE = (
    DATA_DIR / "silver" /
    "healthcare_network_matches_20261011_122708.csv"
)

DRIVING_GRAPH_FILE = (
    DATA_DIR / "raw" /
    "roads_osm_20261011_115925.graphml"
)

WALKING_GRAPH_FILE = (
    DATA_DIR / "raw" /
    "roads_walking_osm_20261011_122708.graphml"
)

OUTPUT_HTML = REPORTS_DIR / "disconnected_road_review_map.html"
OUTPUT_CSV = REPORTS_DIR / "disconnected_road_review_map_points.csv"
OUTPUT_JSON = REPORTS_DIR / "disconnected_road_review_map_summary.json"

# UTM zone 43N is suitable for the Coimbatore area.
PROJECT_CRS = "EPSG:32643"

REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def normalize_id(value):
    """Normalize IDs so numeric strings and integers can be compared."""
    if pd.isna(value):
        return None

    text = str(value).strip()

    if text.endswith(".0"):
        try:
            text = str(int(float(text)))
        except ValueError:
            pass

    return text


def numeric_coordinate(value):
    try:
        result = float(value)
        if math.isfinite(result):
            return result
    except (TypeError, ValueError):
        pass
    return None


def load_graph(path, label):
    if not path.exists():
        raise FileNotFoundError(f"{label} graph not found: {path}")

    print(f"Loading {label} graph...")
    graph = ox.load_graphml(path)

    if len(graph.nodes) == 0:
        raise ValueError(f"{label} graph contains no nodes.")

    print(f"{label} nodes: {len(graph.nodes):,}")
    return graph


def node_coordinates(graph):
    """Return node IDs and projected coordinates."""
    transformer = Transformer.from_crs(
        "EPSG:4326", PROJECT_CRS, always_xy=True
    )

    node_ids = []
    projected_points = []

    for node_id, attributes in graph.nodes(data=True):
        try:
            lon = float(attributes["x"])
            lat = float(attributes["y"])
            x, y = transformer.transform(lon, lat)

            if math.isfinite(x) and math.isfinite(y):
                node_ids.append(node_id)
                projected_points.append((x, y))
        except (KeyError, TypeError, ValueError):
            continue

    if not node_ids:
        raise ValueError("No valid graph-node coordinates were found.")

    return node_ids, projected_points


def find_fragment_candidates(graph, matches, network_prefix, graph_label):
    """
    Find matched facility nodes outside the graph's largest weak
    component, then find the nearest node in that largest component.

    The candidate gap is straight-line distance, not a verified road.
    """
    print(f"Inspecting {graph_label} network...")

    # Treat the graph as undirected for identifying weak components.
    undirected = graph.to_undirected(as_view=True)
    components = list(nx.connected_components(undirected))

    if not components:
        raise ValueError(f"No connected components in {graph_label} graph.")

    main_component = max(components, key=len)
    main_node_ids = set(main_component)

    print(f"  Components: {len(components):,}")
    print(f"  Largest component nodes: {len(main_component):,}")

    node_ids, projected_points = node_coordinates(graph)
    position_by_id = {
        normalize_id(node_id): point
        for node_id, point in zip(node_ids, projected_points)
    }

    main_ids = [
        node_id for node_id in node_ids
        if node_id in main_node_ids
    ]
    main_points = [
        point for node_id, point in zip(node_ids, projected_points)
        if node_id in main_node_ids
    ]

    if not main_points:
        raise ValueError(f"No projected nodes in largest {graph_label} component.")

    tree = cKDTree(main_points)

    node_to_component = {}
    for component_number, component in enumerate(components):
        for node_id in component:
            node_to_component[node_id] = component_number

    main_component_number = node_to_component[next(iter(main_component))]
    records = []

    node_column = f"{network_prefix}_nearest_node_id"
    snap_column = f"{network_prefix}_snap_distance_m"

    for _, row in matches.iterrows():
        facility_node_id = normalize_id(row.get(node_column))

        if facility_node_id is None:
            continue

        # Resolve the normalized ID back to the actual graph node.
        actual_node_id = next(
            (
                node_id for node_id in graph.nodes
                if normalize_id(node_id) == facility_node_id
            ),
            None,
        )

        if actual_node_id is None:
            continue

        component_number = node_to_component.get(actual_node_id)

        # Only review facilities snapped to nodes outside the main component.
        if component_number == main_component_number:
            continue

        facility_point = position_by_id.get(facility_node_id)
        if facility_point is None:
            continue

        distance_m, nearest_index = tree.query(facility_point)
        candidate_node_id = main_ids[int(nearest_index)]
        candidate_point = main_points[int(nearest_index)]

        lat = numeric_coordinate(row.get("latitude"))
        lon = numeric_coordinate(row.get("longitude"))

        if lat is None or lon is None:
            continue

        records.append({
            "network": graph_label,
            "osm_type": row.get("osm_type", ""),
            "osm_id": row.get("osm_id", ""),
            "name": row.get("name", ""),
            "category": row.get("category", ""),
            "facility_latitude": lat,
            "facility_longitude": lon,
            "facility_node_id": str(actual_node_id),
            "component_node_count": len(
                next(c for c in components if actual_node_id in c)
            ),
            "facility_snap_distance_m": row.get(snap_column, ""),
            "candidate_main_node_id": str(candidate_node_id),
            "candidate_latitude": float(
                Transformer.from_crs(
                    PROJECT_CRS, "EPSG:4326", always_xy=True
                ).transform(candidate_point[0], candidate_point[1])[1]
            ),
            "candidate_longitude": float(
                Transformer.from_crs(
                    PROJECT_CRS, "EPSG:4326", always_xy=True
                ).transform(candidate_point[0], candidate_point[1])[0]
            ),
            "candidate_gap_straight_line_m": round(float(distance_m), 2),
            "review_status": "Needs manual review",
            "warning": "Dashed gap is straight-line distance, not a verified road.",
        })

    return records


def add_legend(map_object):
    legend_html = """
    <div style="
        position: fixed;
        bottom: 25px;
        left: 25px;
        z-index: 9999;
        background: white;
        border: 1px solid #777;
        border-radius: 5px;
        padding: 10px 12px;
        font-size: 13px;
        line-height: 1.7;
        box-shadow: 0 1px 5px rgba(0,0,0,0.25);
    ">
      <b>AURIS-X Road Fragment Review</b><br>
      <span style="color:#d7191c;">●</span> Facility on disconnected component<br>
      <span style="color:#2166ac;">●</span> Candidate node in largest component<br>
      <span style="color:#777;">- - -</span> Straight-line candidate gap<br>
      <small>No road connection is inferred by this map.</small>
    </div>
    """
    map_object.get_root().html.add_child(folium.Element(legend_html))


def main():
    if not MATCHES_FILE.exists():
        raise FileNotFoundError(f"Facility matches file not found: {MATCHES_FILE}")

    matches = pd.read_csv(MATCHES_FILE, dtype={"osm_id": str})
    print(f"Facility match records loaded: {len(matches):,}")

    driving_graph = load_graph(DRIVING_GRAPH_FILE, "Driving")
    walking_graph = load_graph(WALKING_GRAPH_FILE, "Walking")

    all_records = []

    all_records.extend(
        find_fragment_candidates(
            driving_graph, matches, "drive", "Driving"
        )
    )
    all_records.extend(
        find_fragment_candidates(
            walking_graph, matches, "walk", "Walking"
        )
    )

    if not all_records:
        raise RuntimeError(
            "No disconnected facility records found. "
            "Check graph IDs and the facility-match CSV."
        )

    points_df = pd.DataFrame(all_records)
    points_df.to_csv(OUTPUT_CSV, index=False)

    # Centre the map using all facility and candidate locations.
    centre_lat = points_df["facility_latitude"].mean()
    centre_lon = points_df["facility_longitude"].mean()

    # tiles=None prevents all external basemap tile requests.
    map_object = folium.Map(
        location=[centre_lat, centre_lon],
        zoom_start=13,
        tiles=None,
        control_scale=True,
    )

    driving_group = folium.FeatureGroup(
        name="Driving network fragments", show=True
    )
    walking_group = folium.FeatureGroup(
        name="Walking network fragments", show=True
    )

    for _, row in points_df.iterrows():
        group = (
            driving_group
            if row["network"] == "Driving"
            else walking_group
        )

        facility_popup = f"""
        <b>Facility:</b> {row['name']}<br>
        <b>Category:</b> {row['category']}<br>
        <b>Network:</b> {row['network']}<br>
        <b>OSM ID:</b> {row['osm_id']}<br>
        <b>Disconnected component nodes:</b> {row['component_node_count']}<br>
        <b>Candidate gap:</b> {row['candidate_gap_straight_line_m']} m<br>
        <b>Status:</b> Needs manual review<br>
        <b>Warning:</b> Straight-line gap only; not a verified road.
        """

        folium.CircleMarker(
            location=[
                row["facility_latitude"],
                row["facility_longitude"],
            ],
            radius=7,
            color="#d7191c",
            fill=True,
            fill_color="#d7191c",
            fill_opacity=0.9,
            tooltip=f"Facility: {row['name']} ({row['network']})",
            popup=folium.Popup(facility_popup, max_width=350),
        ).add_to(group)

        folium.CircleMarker(
            location=[
                row["candidate_latitude"],
                row["candidate_longitude"],
            ],
            radius=6,
            color="#2166ac",
            fill=True,
            fill_color="#2166ac",
            fill_opacity=0.9,
            tooltip=f"Nearest main-component node: {row['candidate_main_node_id']}",
        ).add_to(group)

        folium.PolyLine(
            locations=[
                [
                    row["facility_latitude"],
                    row["facility_longitude"],
                ],
                [
                    row["candidate_latitude"],
                    row["candidate_longitude"],
                ],
            ],
            color="#777777",
            weight=2,
            opacity=0.85,
            dash_array="6, 8",
            tooltip=(
                f"Straight-line gap: "
                f"{row['candidate_gap_straight_line_m']} m "
                "(not a verified road)"
            ),
        ).add_to(group)

    driving_group.add_to(map_object)
    walking_group.add_to(map_object)

    folium.LayerControl(collapsed=False).add_to(map_object)
    add_legend(map_object)

    # Fit the map to the facility and candidate markers.
    bounds = []
    for _, row in points_df.iterrows():
        bounds.append([
            row["facility_latitude"], row["facility_longitude"]
        ])
        bounds.append([
            row["candidate_latitude"], row["candidate_longitude"]
        ])

    if bounds:
        map_object.fit_bounds(bounds, padding=(25, 25))

    map_object.save(str(OUTPUT_HTML))

    summary = {
        "title": "AURIS-X disconnected road review",
        "tile_free_map": True,
        "facility_match_rows_loaded": int(len(matches)),
        "review_records": int(len(points_df)),
        "driving_review_records": int(
            (points_df["network"] == "Driving").sum()
        ),
        "walking_review_records": int(
            (points_df["network"] == "Walking").sum()
        ),
        "html_output": str(OUTPUT_HTML),
        "csv_output": str(OUTPUT_CSV),
        "warning": (
            "Dashed lines are straight-line gaps to candidate nodes. "
            "They do not represent verified roads or network travel distances."
        ),
    }

    OUTPUT_JSON.write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    print("\nMap saved:", OUTPUT_HTML)
    print("Point report saved:", OUTPUT_CSV)
    print("Summary saved:", OUTPUT_JSON)
    print("Review records:", len(points_df))
    print("Basemap tiles: disabled")
    print("Dashed lines are straight-line gaps, not verified roads.")


if __name__ == "__main__":
    main()
