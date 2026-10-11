
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import osmnx as ox

# AURIS-X study-area approximation.
# These bounds are not an official Coimbatore boundary.
SOUTH = 10.85
WEST = 76.85
NORTH = 11.15
EAST = 77.15

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
REPORT_DIR = PROJECT_ROOT / "reports"

RAW_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_path = RAW_DIR / f"roads_osm_{timestamp}.graphml"
metadata_path = RAW_DIR / f"roads_osm_{timestamp}_metadata.json"

def main():
    print("AURIS-X: downloading OpenStreetMap road network")
    print(f"Approximate bounding box: {SOUTH}, {WEST}, {NORTH}, {EAST}")
    print("This may take a few minutes. Please don't run multiple copies.")

    # Identify the data source and configure polite request handling.
    ox.settings.use_cache = True
    ox.settings.log_console = True
    ox.settings.requests_timeout = 180
    ox.settings.overpass_rate_limit = True

    try:
        # Request a drivable street network for an initial prototype.
        graph = ox.graph_from_bbox(
            bbox=(WEST, SOUTH, EAST, NORTH),
            network_type="drive",
            simplify=True,
            retain_all=True,
            truncate_by_edge=True,
        )

        node_count = len(graph.nodes)
        edge_count = len(graph.edges)

        ox.save_graphml(graph, filepath=output_path)

        metadata = {
            "project": "AURIS-X",
            "dataset": "OpenStreetMap drivable road network",
            "source": "OpenStreetMap via OSMnx",
            "source_url": "https://www.openstreetmap.org/",
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "bounding_box": {
                "south": SOUTH,
                "west": WEST,
                "north": NORTH,
                "east": EAST,
            },
            "network_type": "drive",
            "node_count": node_count,
            "edge_count": edge_count,
            "output_file": str(output_path),
            "license": "Open Database License (ODbL); verify attribution requirements",
            "limitations": [
                "Bounding box is approximate, not an official city boundary.",
                "OpenStreetMap road completeness and access tags may vary.",
                "Drive network does not represent walking access.",
                "Network topology and travel times require additional validation.",
            ],
        }

        metadata_path.write_text(
            json.dumps(metadata, indent=2),
            encoding="utf-8",
        )

        print("\nSUCCESS")
        print(f"Nodes: {node_count}")
        print(f"Edges: {edge_count}")
        print(f"Road graph: {output_path}")
        print(f"Metadata: {metadata_path}")
        print("Note: this is a drivable-road graph, not a validated travel-time model.")

    except Exception as exc:
        print("\nDOWNLOAD FAILED")
        print(f"{type(exc).__name__}: {exc}")
        print("No dataset should be treated as downloaded unless its output file exists.")
        sys.exit(1)

if __name__ == "__main__":
    main()
