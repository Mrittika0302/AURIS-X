import json
from pathlib import Path

p = Path("data/reference_boundaries/coimbatore_datameet_2011_wards.geojson")
obj = json.loads(p.read_text(encoding="utf-8-sig"))

print("Top-level type:", type(obj).__name__)
if isinstance(obj, dict):
    print("Top-level keys:", list(obj.keys()))
    print("Type field:", obj.get("type"))
    features = obj.get("features")
    print("Features type:", type(features).__name__)
    print("Feature count:", len(features) if isinstance(features, list) else "not a list")
    if isinstance(features, list) and features:
        print("First feature keys:", list(features[0].keys()))
        print("Geometry:", features[0].get("geometry"))
