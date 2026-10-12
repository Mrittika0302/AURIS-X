
from pathlib import Path
import osmnx as ox

ROOT = Path(__file__).resolve().parents[1]

FILES = {
    "DRIVING": ROOT / "data" / "raw" / "roads_osm_20261011_115925.graphml",
    "WALKING": ROOT / "data" / "raw" / "roads_walking_osm_20261011_122708.graphml",
}

TARGET_OSMID = "1262117427"

def as_list(value):
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def main():
    for mode, path in FILES.items():
        print(f"\n{'=' * 70}")
        print(f"{mode} GRAPH")
        print(f"File: {path.name}")

        graph = ox.load_graphml(path)
        found = 0

        for u, v, key, data in graph.edges(keys=True, data=True):
            ids = [str(x) for x in as_list(data.get("osmid"))]

            if TARGET_OSMID not in ids:
                continue

            found += 1
            node_u = graph.nodes[u]
            node_v = graph.nodes[v]

            print(f"\nEdge #{found}")
            print(f"  from node: {u}")
            print(f"  to node:   {v}")
            print(f"  key:       {key}")
            print(f"  OSM IDs:   {data.get('osmid')}")
            print(f"  length m:  {data.get('length')}")
            print(f"  highway:   {data.get('highway')}")
            print(f"  name:      {data.get('name')}")
            print(
                "  start lon/lat: "
                f"{node_u.get('x')}, {node_u.get('y')}"
            )
            print(
                "  end lon/lat:   "
                f"{node_v.get('x')}, {node_v.get('y')}"
            )
            print(
                "  geometry present: "
                f"{data.get('geometry') is not None}"
            )

        if found == 0:
            print(f"No edge records found for OSM way {TARGET_OSMID}.")

        print(f"\nTotal matching directed edge records: {found}")


if __name__ == "__main__":
    main()
