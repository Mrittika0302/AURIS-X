
import json
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from scipy.spatial import cKDTree


# ============================================================
# AURIS-X: POPULATION GRID TO ROAD-NETWORK MATCHING
#
# Outputs:
#   data/silver/population_road_matches.csv
#   reports/population_road_matching_summary.json
#
# Important:
# - Snap distances are straight-line distances.
# - They are NOT road-network travel distances or travel times.
# - Original raster and graph files are never modified.
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[1]

RASTER_FILE = (
    BASE_DIR
    / "data"
    / "population"
    / "coimbatore_population_2026_approx.tif"
)

DRIVING_GRAPH_FILE = (
    BASE_DIR
    / "data"
    / "raw"
    / "roads_osm_20261011_115925.graphml"
)

WALKING_GRAPH_FILE = (
    BASE_DIR
    / "data"
    / "raw"
    / "roads_walking_osm_20261011_122708.graphml"
)

OUTPUT_CSV = (
    BASE_DIR
    / "data"
    / "silver"
    / "population_road_matches.csv"
)

OUTPUT_JSON = (
    BASE_DIR
    / "reports"
    / "population_road_matching_summary.json"
)

# Suitable projected CRS for the Coimbatore region.
PROJECTED_CRS = "EPSG:32643"

# These are review thresholds, not universal definitions of a
# valid or invalid road connection.
REVIEW_THRESHOLD_M = 100.0
HIGH_REVIEW_THRESHOLD_M = 250.0

BASE_DIR.joinpath("data", "silver").mkdir(
    parents=True, exist_ok=True
)
BASE_DIR.joinpath("reports").mkdir(
    parents=True, exist_ok=True
)


def normalize_id(value):
    """Normalize graph IDs for CSV output and comparisons."""
    text = str(value).strip()

    if text.endswith(".0"):
        try:
            text = str(int(float(text)))
        except ValueError:
            pass

    return text


def load_road_nodes(graph_file, label):
    """Load graph nodes and project their coordinates to metres."""
    if not graph_file.exists():
        raise FileNotFoundError(
            f"{label} graph not found: {graph_file}"
        )

    print(f"\nLoading {label} graph...")
    graph = nx.read_graphml(graph_file)

    node_ids = []
    longitudes = []
    latitudes = []

    for node_id, attributes in graph.nodes(data=True):
        try:
            lon = float(attributes["x"])
            lat = float(attributes["y"])

            if not (
                np.isfinite(lon)
                and np.isfinite(lat)
                and -180 <= lon <= 180
                and -90 <= lat <= 90
            ):
                continue

            node_ids.append(normalize_id(node_id))
            longitudes.append(lon)
            latitudes.append(lat)

        except (KeyError, TypeError, ValueError):
            continue

    if not node_ids:
        raise ValueError(
            f"No usable coordinates found in {label} graph."
        )

    transformer = Transformer.from_crs(
        "EPSG:4326",
        PROJECTED_CRS,
        always_xy=True,
    )

    x, y = transformer.transform(
        np.asarray(longitudes),
        np.asarray(latitudes),
    )

    coordinates = np.column_stack([x, y])
    valid = np.isfinite(coordinates).all(axis=1)

    node_ids = np.asarray(node_ids, dtype=str)[valid]
    coordinates = coordinates[valid]

    print(f"{label} usable nodes: {len(node_ids):,}")

    return node_ids, coordinates


def load_population_cells(raster_file):
    """Read valid raster cells and calculate their centre coordinates."""
    if not raster_file.exists():
        raise FileNotFoundError(
            f"Population raster not found: {raster_file}"
        )

    print("\nLoading population raster...")

    with rasterio.open(raster_file) as src:
        if src.count < 1:
            raise ValueError("Population raster has no bands.")

        if src.crs is None:
            raise ValueError(
                "Population raster has no CRS; cannot transform coordinates."
            )

        values = src.read(1, masked=True)
        valid_mask = ~np.ma.getmaskarray(values)

        raw_values = np.asarray(values.data)
        valid_mask &= np.isfinite(raw_values)

        rows, cols = np.where(valid_mask)

        if len(rows) == 0:
            raise ValueError(
                "No valid population cells were found."
            )

        population_values = raw_values[rows, cols].astype(
            np.float64
        )

        # Raster cell-centre coordinates in the raster's own CRS.
        xs, ys = rasterio.transform.xy(
            src.transform,
            rows,
            cols,
            offset="center",
        )

        raster_crs = src.crs

        # Save metadata before the raster is closed.
        metadata = {
            "width": int(src.width),
            "height": int(src.height),
            "band_count": int(src.count),
            "raster_crs": str(src.crs),
            "nodata": (
                float(src.nodata)
                if src.nodata is not None
                else None
            ),
            "valid_cell_count": int(len(rows)),
            "raster_bounds": {
                "left": float(src.bounds.left),
                "bottom": float(src.bounds.bottom),
                "right": float(src.bounds.right),
                "top": float(src.bounds.top),
            },
        }

    # Convert raster coordinates to geographic coordinates,
    # then project to metres for accurate nearest-node distances.
    to_wgs84 = Transformer.from_crs(
        raster_crs,
        "EPSG:4326",
        always_xy=True,
    )

    lon, lat = to_wgs84.transform(
        np.asarray(xs),
        np.asarray(ys),
    )

    to_projected = Transformer.from_crs(
        "EPSG:4326",
        PROJECTED_CRS,
        always_xy=True,
    )

    x, y = to_projected.transform(lon, lat)

    cells = pd.DataFrame({
        "raster_row": rows.astype(np.int32),
        "raster_col": cols.astype(np.int32),
        "latitude": np.asarray(lat, dtype=np.float64),
        "longitude": np.asarray(lon, dtype=np.float64),
        "population_raster_value": population_values,
        "projected_x_m": np.asarray(x, dtype=np.float64),
        "projected_y_m": np.asarray(y, dtype=np.float64),
    })

    finite_coordinates = (
        np.isfinite(cells["projected_x_m"])
        & np.isfinite(cells["projected_y_m"])
        & np.isfinite(cells["latitude"])
        & np.isfinite(cells["longitude"])
    )

    cells = cells.loc[finite_coordinates].reset_index(
        drop=True
    )

    metadata["cells_with_valid_projected_coordinates"] = int(
        len(cells)
    )

    print(f"Valid raster cells: {len(cells):,}")

    return cells, metadata


def match_cells_to_nodes(cells, node_ids, node_coordinates, label):
    """Match each cell centre to the nearest graph node."""
    print(f"\nMatching population cells to {label} nodes...")

    tree = cKDTree(node_coordinates)

    cell_coordinates = cells[
        ["projected_x_m", "projected_y_m"]
    ].to_numpy()

    distances, indices = tree.query(
        cell_coordinates,
        k=1,
        workers=-1,
    )

    matched_ids = node_ids[indices]

    return matched_ids, distances


def distance_summary(distances):
    """Calculate summary statistics for straight-line snap distances."""
    distances = np.asarray(distances, dtype=np.float64)

    return {
        "minimum_m": float(np.min(distances)),
        "median_m": float(np.median(distances)),
        "p90_m": float(np.percentile(distances, 90)),
        "p95_m": float(np.percentile(distances, 95)),
        "p99_m": float(np.percentile(distances, 99)),
        "maximum_m": float(np.max(distances)),
        "over_100m": int(np.sum(distances > REVIEW_THRESHOLD_M)),
        "over_250m": int(
            np.sum(distances > HIGH_REVIEW_THRESHOLD_M)
        ),
    }


def main():
    cells, raster_metadata = load_population_cells(
        RASTER_FILE
    )

    drive_ids, drive_coordinates = load_road_nodes(
        DRIVING_GRAPH_FILE,
        "Driving",
    )

    walk_ids, walk_coordinates = load_road_nodes(
        WALKING_GRAPH_FILE,
        "Walking",
    )

    drive_match_ids, drive_distances = match_cells_to_nodes(
        cells,
        drive_ids,
        drive_coordinates,
        "driving",
    )

    walk_match_ids, walk_distances = match_cells_to_nodes(
        cells,
        walk_ids,
        walk_coordinates,
        "walking",
    )

    output = cells[
        [
            "raster_row",
            "raster_col",
            "latitude",
            "longitude",
            "population_raster_value",
        ]
    ].copy()

    output.insert(
        0,
        "population_cell_id",
        [
            f"r{row}_c{col}"
            for row, col in zip(
                output["raster_row"],
                output["raster_col"],
            )
        ],
    )

    output["drive_nearest_node_id"] = drive_match_ids
    output["drive_snap_distance_m"] = np.round(
        drive_distances, 2
    )
    output["drive_review_over_100m"] = (
        drive_distances > REVIEW_THRESHOLD_M
    )
    output["drive_review_over_250m"] = (
        drive_distances > HIGH_REVIEW_THRESHOLD_M
    )

    output["walk_nearest_node_id"] = walk_match_ids
    output["walk_snap_distance_m"] = np.round(
        walk_distances, 2
    )
    output["walk_review_over_100m"] = (
        walk_distances > REVIEW_THRESHOLD_M
    )
    output["walk_review_over_250m"] = (
        walk_distances > HIGH_REVIEW_THRESHOLD_M
    )

    output.to_csv(OUTPUT_CSV, index=False)

    summary = {
        "project": "AURIS-X",
        "task": "Population grid to road-network node matching",
        "population_raster": str(RASTER_FILE),
        "projected_crs_for_distance": PROJECTED_CRS,
        "raster_metadata": raster_metadata,
        "population_cells_matched": int(len(output)),
        "driving_graph_nodes_used": int(len(drive_ids)),
        "walking_graph_nodes_used": int(len(walk_ids)),
        "driving_snap_distance_summary": distance_summary(
            drive_distances
        ),
        "walking_snap_distance_summary": distance_summary(
            walk_distances
        ),
        "review_thresholds_m": {
            "review_over_100m": REVIEW_THRESHOLD_M,
            "high_review_over_250m": HIGH_REVIEW_THRESHOLD_M,
        },
        "output_csv": str(OUTPUT_CSV),
        "limitations": [
            "Nearest-node distances are straight-line distances.",
            "A nearest-node match does not prove safe or legal access.",
            "No network travel distances or travel times were calculated.",
            "Graph connectivity and directionality are not evaluated by this script.",
            "Population raster units have not been verified here.",
            "Population raster values are preserved, not interpreted as confirmed headcounts.",
        ],
    }

    OUTPUT_JSON.write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    print("\n" + "=" * 60)
    print("POPULATION-TO-ROAD MATCHING COMPLETE")
    print("=" * 60)
    print(f"Population cells matched: {len(output):,}")
    print(
        "Driving cells over 100 m:",
        int((drive_distances > REVIEW_THRESHOLD_M).sum()),
    )
    print(
        "Walking cells over 100 m:",
        int((walk_distances > REVIEW_THRESHOLD_M).sum()),
    )
    print("CSV:", OUTPUT_CSV)
    print("Summary:", OUTPUT_JSON)
    print("\nDistances are straight-line snapping distances,")
    print("not road-network travel distances or travel times.")


if __name__ == "__main__":
    main()
