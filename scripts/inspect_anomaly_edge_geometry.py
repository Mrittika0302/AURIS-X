from pathlib import Path
import glob
import os
import json
import ast
import networkx as nx

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"

PAIRS = [
    ("6965421644", "6965421653"),
    ("9068977797", "9068977796"),
    ("5655107628", "9676768874"),
    ("13999738633", "13999738634"),
]


def latest(pattern):
    files = glob.glob(str(RAW / pattern))

    if not files:
        raise FileNotFoundError(
            f"No file matches {pattern} in {RAW}"
        )

    return max(files, key=os.path.getmtime)


def parse_geometry(geometry):
    """Extract coordinates from supported geometry formats."""
    if geometry is None:
        return [], "No geometry attribute"

    if hasattr(geometry, "coords"):
        try:
            return list(geometry.coords), "Shapely geometry"
        except Exception:
            pass

    if not isinstance(geometry, str):
        return [], (
            f"Unsupported type: {type(geometry).__name__}"
        )

    text = geometry.strip()

    if not text:
        return [], "Empty geometry string"

    # Try Well-Known Text (WKT).
    try:
        from shapely import wkt

        parsed = wkt.loads(text)

        if hasattr(parsed, "coords"):
            return list(parsed.coords), "WKT"

        return [], f"WKT type: {parsed.geom_type}"

    except Exception:
        pass

    # Try JSON-encoded coordinates.
    try:
        parsed = json.loads(text)

        if isinstance(parsed, dict):
            coordinates = parsed.get("coordinates")

            if coordinates:
                return list(coordinates), "JSON coordinates"

    except Exception:
        pass

    # Try a Python list/tuple representation.
    try:
        parsed = ast.literal_eval(text)

        if isinstance(parsed, (list, tuple)):
            if parsed and isinstance(parsed[0], (list, tuple)):
                return list(parsed), "Python coordinate list"

    except Exception:
        pass

    return [], f"Could not parse: {text[:100]}"


def show_graph_edges(graph, label, u, v):
    print(f"\n{label}: {u} <-> {v}")

    if u not in graph or v not in graph:
        print("  One or both nodes are missing.")
        return

    for a, b in [(u, v), (v, u)]:
        if not graph.has_edge(a, b):
            print(f"  No edge: {a} -> {b}")
            continue

        for key, data in graph[a][b].items():
            coords, status = parse_geometry(
                data.get("geometry")
            )

            print(f"\n  Edge: {a} -> {b}")
            print(f"    Key: {key}")
            print(f"    Length: {data.get('length')} m")
            print(f"    OSM ID: {data.get('osmid')}")
            print(f"    Highway: {data.get('highway')}")
            print(f"    Name: {data.get('name')}")
            print(f"    Geometry status: {status}")
            print(f"    Geometry points: {len(coords)}")

            if coords:
                print("    First coordinates:", coords[:3])

                if len(coords) > 3:
                    print("    Last coordinates:", coords[-3:])


def show_node_coordinates(graph, label, node):
    if node not in graph:
        print(f"  {label} node {node}: not found")
        return

    data = graph.nodes[node]

    print(
        f"  {label} node {node}: "
        f"longitude={data.get('x')}, "
        f"latitude={data.get('y')}"
    )


def main():
    drive_path = latest("roads_osm_*.graphml")
    walk_path = latest("roads_walking_osm_*.graphml")

    print("READ-ONLY EDGE GEOMETRY DIAGNOSTIC")
    print("Driving graph:", Path(drive_path).name)
    print("Walking graph:", Path(walk_path).name)

    drive = nx.read_graphml(drive_path)
    walk = nx.read_graphml(walk_path)

    for u, v in PAIRS:
        print("\n" + "=" * 70)
        print(f"TARGET PAIR: {u} <-> {v}")

        show_node_coordinates(drive, "DRIVING", u)
        show_node_coordinates(drive, "DRIVING", v)

        show_graph_edges(drive, "DRIVING", u, v)
        show_graph_edges(walk, "WALKING", u, v)

    print("\nInspection complete. No files modified.")


if __name__ == "__main__":
    main()