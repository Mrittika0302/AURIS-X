import json
from pathlib import Path
import rasterio

root = Path(__file__).resolve().parent.parent
boundary_file = root / "data/reference_boundaries/coimbatore_datameet_2011_wards.geojson"
raster_file = root / "data/population/coimbatore_population_2026_approx.tif"

geo = json.loads(boundary_file.read_text(encoding="utf-8-sig"))
coords = []

def collect_coordinates(obj):
    if isinstance(obj, (list, tuple)):
        if len(obj) >= 2 and all(isinstance(v, (int, float)) for v in obj[:2]):
            coords.append((obj[0], obj[1]))
        else:
            for item in obj:
                collect_coordinates(item)

for feature in geo.get("features", []):
    geometry = feature.get("geometry")
    if geometry:
        collect_coordinates(geometry.get("coordinates", []))

if not coords:
    raise ValueError("No coordinates found in GeoJSON geometries")

west = min(x for x, y in coords)
east = max(x for x, y in coords)
south = min(y for x, y in coords)
north = max(y for x, y in coords)

with rasterio.open(raster_file) as ds:
    b = ds.bounds
    raster_bbox = {
        "west": b.left, "south": b.bottom,
        "east": b.right, "north": b.top
    }

covers = (
    b.left <= west and b.bottom <= south
    and b.right >= east and b.top >= north
)

result = {
    "boundary_source": "DataMeet community-curated Coimbatore 2011 ward polygons; not verified as the current official boundary",
    "ward_feature_count": len(geo.get("features", [])),
    "boundary_bbox": {
        "west": west, "south": south, "east": east, "north": north
    },
    "raster_bbox": raster_bbox,
    "raster_covers_boundary_extent": covers,
    "coordinate_count": len(coords),
    "note": "Extent comparison only. This does not validate current legal boundaries or clip population pixels to ward/corporation polygons."
}

out = root / "reports/module6_boundary_extent_check.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
print(f"\nReport saved: {out}")
