
from pathlib import Path
from datetime import datetime, timezone
import glob
import json
import os

import pandas as pd
import folium
import networkx as nx
from folium.plugins import Fullscreen


# ============================================================
# AURIS-X: EDUCATION PRIORITY ZONE MAP
# Robust version: visible numbered markers, no external tiles
# ============================================================

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "data" / "gold"
RAW = ROOT / "data" / "raw"
REPORTS = ROOT / "reports"

TOP_N = 20
ZONE_BLOCK_SIZE = 10

# Road layer is context only. Limit edges for browser performance.
DRAW_ROAD_CONTEXT = True
MAX_ROAD_EDGES = 30000

# Existing read-only road graph from the frozen healthcare phase.
DRIVING_GRAPH = RAW / "roads_osm_20261011_115925.graphml"


def newest_file(pattern):
    matches = glob.glob(str(pattern))
    if not matches:
        raise FileNotFoundError(
            f"No files found matching:\n{pattern}"
        )
    return Path(max(matches, key=os.path.getmtime))


def require_columns(df, required, label):
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"{label} is missing columns: {missing}\n"
            f"Available columns: {list(df.columns)}"
        )


def find_column(df, candidates, label):
    for col in candidates:
        if col in df.columns:
            return col
    raise ValueError(
        f"Could not identify {label} column.\n"
        f"Tried: {candidates}\n"
        f"Available: {list(df.columns)}"
    )


def make_zone_id(row, col):
    return f"ER{int(row)}_EC{int(col)}"


def load_priority_zones():
    ranking_file = newest_file(
        GOLD / "education_priority_zones_*.csv"
    )
    flags_file = newest_file(
        GOLD / "education_accessibility_flags_*.csv"
    )

    zones = pd.read_csv(ranking_file)
    cells = pd.read_csv(flags_file)

    require_columns(
        zones,
        ["zone_id", "priority_score"],
        "Education priority ranking",
    )
    require_columns(
        cells,
        ["raster_row", "raster_col", "latitude", "longitude"],
        "Education accessibility flags",
    )

    # Accept slightly different column names if an earlier
    # version of the ranking script used them.
    rank_col = find_column(
        zones, ["rank", "priority_rank", "zone_rank"], "rank"
    )
    either_col = find_column(
        zones,
        [
            "flagged_either_mode_cells",
            "flagged_either_modes_cells",
            "flagged_either_cells",
        ],
        "flagged-either count",
    )
    both_col = find_column(
        zones,
        [
            "flagged_both_modes_cells",
            "flagged_both_mode_cells",
            "flagged_both_cells",
        ],
        "flagged-both count",
    )

    zones["zone_id"] = zones["zone_id"].astype(str)
    zones["rank"] = pd.to_numeric(
        zones[rank_col], errors="coerce"
    )
    zones["priority_score"] = pd.to_numeric(
        zones["priority_score"], errors="coerce"
    )
    zones["flagged_either_mode_cells"] = pd.to_numeric(
        zones[either_col], errors="coerce"
    ).fillna(0).astype(int)
    zones["flagged_both_modes_cells"] = pd.to_numeric(
        zones[both_col], errors="coerce"
    ).fillna(0).astype(int)

    zones = zones.dropna(
        subset=["rank", "priority_score"]
    ).copy()
    zones["rank"] = zones["rank"].astype(int)

    # Coordinates are taken from the accessibility grid, not
    # from the ranking CSV, which may have no coordinate columns.
    cells["raster_row"] = pd.to_numeric(
        cells["raster_row"], errors="coerce"
    )
    cells["raster_col"] = pd.to_numeric(
        cells["raster_col"], errors="coerce"
    )
    cells["latitude"] = pd.to_numeric(
        cells["latitude"], errors="coerce"
    )
    cells["longitude"] = pd.to_numeric(
        cells["longitude"], errors="coerce"
    )

    cells = cells.dropna(
        subset=[
            "raster_row", "raster_col", "latitude", "longitude"
        ]
    ).copy()

    cells["raster_row"] = cells["raster_row"].astype(int)
    cells["raster_col"] = cells["raster_col"].astype(int)

    cells["zone_row"] = (
        cells["raster_row"] // ZONE_BLOCK_SIZE
    )
    cells["zone_col"] = (
        cells["raster_col"] // ZONE_BLOCK_SIZE
    )
    cells["zone_id"] = [
        make_zone_id(r, c)
        for r, c in zip(cells["zone_row"], cells["zone_col"])
    ]

    # Use the mean of actual cell coordinates to locate each
    # analytical raster block.
    centroids = (
        cells.groupby("zone_id", as_index=False)
        .agg(
            latitude=("latitude", "mean"),
            longitude=("longitude", "mean"),
            grid_cells=("zone_id", "size"),
        )
    )

    # Drop possible coordinate fields before merging.
    zones = zones.drop(
        columns=[
            c for c in ["latitude", "longitude", "grid_cells"]
            if c in zones.columns
        ],
        errors="ignore",
    )

    zones = zones.merge(
        centroids,
        on="zone_id",
        how="left",
        validate="one_to_one",
    )

    zones = zones.sort_values(
        ["rank", "priority_score"],
        ascending=[True, False],
    ).reset_index(drop=True)

    top = zones.head(TOP_N).copy()

    if top.empty:
        raise ValueError("No ranked zones were found.")

    missing = top[
        top["latitude"].isna() | top["longitude"].isna()
    ]
    if not missing.empty:
        raise ValueError(
            "Could not calculate coordinates for these zones: "
            + ", ".join(missing["zone_id"].astype(str))
            + "\nCheck that the zone IDs in the ranking file use "
              "the same 10x10 raster-block scheme."
        )

    top = top[
        top["latitude"].between(-90, 90)
        & top["longitude"].between(-180, 180)
    ].copy()

    if top.empty:
        raise ValueError(
            "All top-zone coordinates are outside valid ranges."
        )

    return ranking_file, flags_file, zones, top


def add_road_context(map_object, top):
    """Draw a subset of the existing driving graph without modifying it."""
    if not DRAW_ROAD_CONTEXT:
        return {"status": "disabled", "edges_drawn": 0}

    if not DRIVING_GRAPH.exists():
        print(
            "Road context skipped: driving graph was not found at "
            f"{DRIVING_GRAPH}"
        )
        return {"status": "graph_not_found", "edges_drawn": 0}

    try:
        print("Loading existing driving graph for map context...")
        graph = nx.read_graphml(DRIVING_GRAPH)

        # Graph nodes generally store longitude in x and latitude in y.
        # Only draw roads close to the top-zone extent.
        lat_min = float(top["latitude"].min())
        lat_max = float(top["latitude"].max())
        lon_min = float(top["longitude"].min())
        lon_max = float(top["longitude"].max())

        lat_pad = max((lat_max - lat_min) * 0.25, 0.015)
        lon_pad = max((lon_max - lon_min) * 0.25, 0.015)

        lat_min -= lat_pad
        lat_max += lat_pad
        lon_min -= lon_pad
        lon_max += lon_pad

        node_coords = {}
        for node_id, attrs in graph.nodes(data=True):
            try:
                lon = float(attrs.get("x", attrs.get("lon")))
                lat = float(attrs.get("y", attrs.get("lat")))
            except (TypeError, ValueError):
                continue

            if (
                lat_min <= lat <= lat_max
                and lon_min <= lon <= lon_max
            ):
                node_coords[node_id] = (lat, lon)

        roads = folium.FeatureGroup(
            name="Local road graph (context)",
            overlay=True,
            control=True,
            show=True,
        )

        edge_count = 0
        # For a MultiDiGraph, each edge tuple has u, v, key, attrs.
        for edge in graph.edges(keys=True, data=True):
            u, v = edge[0], edge[1]

            if u not in node_coords or v not in node_coords:
                continue

            a = node_coords[u]
            b = node_coords[v]

            folium.PolyLine(
                locations=[a, b],
                color="#667b89",
                weight=1,
                opacity=0.45,
                interactive=False,
            ).add_to(roads)

            edge_count += 1
            if edge_count >= MAX_ROAD_EDGES:
                break

        roads.add_to(map_object)
        print(f"Road context edges drawn: {edge_count}")

        return {
            "status": "drawn",
            "edges_drawn": edge_count,
            "graph": str(DRIVING_GRAPH.relative_to(ROOT)),
        }

    except Exception as exc:
        print(f"WARNING: Road context could not be drawn: {exc}")
        print("The priority-zone markers will still be mapped.")
        return {
            "status": "error",
            "edges_drawn": 0,
            "error": str(exc),
        }


def add_priority_markers(map_object, top):
    layer = folium.FeatureGroup(
        name="TOP 20 EDUCATION PRIORITY ZONES",
        overlay=True,
        control=True,
        show=True,
    )

    marker_count = 0

    for _, row in top.iterrows():
        rank = int(row["rank"])
        zone_id = str(row["zone_id"])
        score = float(row["priority_score"])
        lat = float(row["latitude"])
        lon = float(row["longitude"])

        either_count = int(row["flagged_either_mode_cells"])
        both_count = int(row["flagged_both_modes_cells"])
        grid_cells = int(row["grid_cells"])

        if rank <= 5:
            color = "#d7191c"
        elif rank <= 10:
            color = "#fdae61"
        else:
            color = "#2c7bb6"

        popup_html = f"""
        <div style="font-family:Arial,sans-serif;width:260px">
          <h3 style="margin-bottom:6px">Education Priority Zone</h3>
          <b>Zone ID:</b> {zone_id}<br>
          <b>Rank:</b> {rank}<br>
          <b>Priority score:</b> {score:.2f}<br>
          <b>Cells flagged in either mode:</b> {either_count}<br>
          <b>Cells flagged in both modes:</b> {both_count}<br>
          <b>Raster cells in zone:</b> {grid_cells}<br>
          <b>Latitude:</b> {lat:.6f}<br>
          <b>Longitude:</b> {lon:.6f}<hr>
          <small>Exploratory screening result. This analytical
          raster block is not an official neighbourhood or a
          confirmed school construction site.</small>
        </div>
        """

        # Numbered circle: the circle itself contains the rank.
        folium.Marker(
            location=[lat, lon],
            tooltip=f"Rank {rank}: {zone_id} | Score {score:.2f}",
            popup=folium.Popup(popup_html, max_width=340),
            icon=folium.DivIcon(
                icon_size=(38, 38),
                icon_anchor=(19, 19),
                html=f"""
                <div style="
                    width:34px;
                    height:34px;
                    border-radius:50%;
                    background:{color};
                    border:3px solid white;
                    box-shadow:0 1px 5px #333;
                    display:flex;
                    align-items:center;
                    justify-content:center;
                    color:#111;
                    font-family:Arial,sans-serif;
                    font-weight:bold;
                    font-size:14px;
                    box-sizing:border-box;
                ">{rank}</div>
                """,
            ),
        ).add_to(layer)

        # Larger halo behind each numbered marker.
        folium.Circle(
            location=[lat, lon],
            radius=120,
            color=color,
            weight=1,
            fill=True,
            fill_color=color,
            fill_opacity=0.12,
            tooltip=f"{zone_id} | rank {rank}",
        ).add_to(layer)

        marker_count += 1

    layer.add_to(map_object)
    print(f"Visible priority zones created: {marker_count}")

    if marker_count == 0:
        raise ValueError("No priority-zone markers were created.")

    return marker_count


def main():
    GOLD.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    print("=" * 66)
    print("AURIS-X — EDUCATION PRIORITY ZONE MAP")
    print("=" * 66)

    ranking_file, flags_file, zones, top = load_priority_zones()

    print(f"Ranking input: {ranking_file}")
    print(f"Accessibility input: {flags_file}")
    print(f"Total ranked zones: {len(zones)}")
    print(f"Zones to map: {len(top)}")
    print(
        "Coordinate range: "
        f"lat {top['latitude'].min():.6f} to "
        f"{top['latitude'].max():.6f}, lon "
        f"{top['longitude'].min():.6f} to "
        f"{top['longitude'].max():.6f}"
    )

    center_lat = float(top["latitude"].mean())
    center_lon = float(top["longitude"].mean())

    # No external tiles. This avoids OpenStreetMap/Carto tile
    # blocking. The road graph is an optional local context layer.
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=11,
        tiles=None,
        control_scale=True,
        prefer_canvas=True,
    )

    # Light neutral background instead of a misleading tile map.
    m.get_root().html.add_child(
        folium.Element("""
        <style>
          html, body { height:100%; margin:0; }
          .leaflet-container { background:#f4f5f6; }
        </style>
        """)
    )

    Fullscreen(
        position="topright",
        title="Full screen",
        title_cancel="Exit full screen",
    ).add_to(m)

    road_summary = add_road_context(m, top)
    marker_count = add_priority_markers(m, top)

    legend = """
    <div style="
      position:fixed;bottom:22px;left:22px;z-index:9999;
      background:white;border:1px solid #555;border-radius:7px;
      padding:12px 14px;font:13px/1.55 Arial,sans-serif;
      box-shadow:0 2px 7px rgba(0,0,0,.25);max-width:300px">
      <b>AURIS-X: Education Priority Zones</b><br>
      <span style="color:#d7191c;font-weight:bold">●</span> Ranks 1–5<br>
      <span style="color:#fdae61;font-weight:bold">●</span> Ranks 6–10<br>
      <span style="color:#2c7bb6;font-weight:bold">●</span> Ranks 11–20<br>
      <b>Click a numbered marker</b> for zone details.<br>
      Use the layer control to toggle the road graph.
      <hr>
      Zones are analytical raster blocks, not official
      neighbourhoods or parcels. Scores are screening indicators,
      not confirmed service gaps or construction recommendations.
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend))

    folium.LayerControl(
        collapsed=False,
        position="topright",
    ).add_to(m)

    # Add padding around the plotted zones.
    lat_span = max(
        float(top["latitude"].max() - top["latitude"].min()),
        0.02,
    )
    lon_span = max(
        float(top["longitude"].max() - top["longitude"].min()),
        0.02,
    )

    bounds = [
        [
            float(top["latitude"].min()) - lat_span * 0.20,
            float(top["longitude"].min()) - lon_span * 0.20,
        ],
        [
            float(top["latitude"].max()) + lat_span * 0.20,
            float(top["longitude"].max()) + lon_span * 0.20,
        ],
    ]
    m.fit_bounds(bounds)

    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    map_path = REPORTS / (
        f"education_priority_zones_map_{timestamp}.html"
    )
    csv_path = GOLD / (
        f"education_priority_zones_mapped_top20_{timestamp}.csv"
    )
    summary_path = REPORTS / (
        f"education_priority_zones_map_summary_{timestamp}.json"
    )

    m.save(str(map_path))
    top.to_csv(csv_path, index=False)

    summary = {
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "ranking_input": str(ranking_file.relative_to(ROOT)),
        "accessibility_flags_input": str(flags_file.relative_to(ROOT)),
        "map_output": str(map_path.relative_to(ROOT)),
        "top20_csv_output": str(csv_path.relative_to(ROOT)),
        "summary_output": str(summary_path.relative_to(ROOT)),
        "total_ranked_zones": int(len(zones)),
        "zones_mapped": int(len(top)),
        "markers_created": int(marker_count),
        "zone_block_size_raster_cells": ZONE_BLOCK_SIZE,
        "map_center": {
            "latitude": center_lat,
            "longitude": center_lon,
        },
        "road_context": road_summary,
        "basemap": "None; local road graph is optional context",
        "notes": [
            "Zone coordinates are calculated from accessibility-grid cells.",
            "Numbered markers are drawn without external tile dependencies.",
            "Zones are analytical blocks, not official neighbourhoods or parcels.",
            "Scores are exploratory screening indicators.",
            "Healthcare source files and road graphs are read-only in this script.",
        ],
    }

    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print()
    print("-" * 66)
    print("MAP GENERATION COMPLETE")
    print("-" * 66)
    print(f"Zones mapped: {len(top)}")
    print(f"Markers created: {marker_count}")
    print(f"Interactive map: {map_path}")
    print(f"Top 20 CSV: {csv_path}")
    print(f"Summary JSON: {summary_path}")
    print()
    print("Open the newly generated HTML file.")
    print("No healthcare files or source data were modified.")


if __name__ == "__main__":
    main()
