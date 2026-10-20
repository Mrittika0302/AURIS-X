import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[1]
raw = root / "data" / "raw"
raw.mkdir(parents=True, exist_ok=True)

bbox = "(10.85,76.85,11.15,77.15)"
query = (
    'nwr["leisure"~"^(park|playground|garden|nature_reserve|recreation_ground|pitch)$"]'
    + bbox + ';'
    + 'nwr["landuse"~"^(recreation_ground|village_green)$"]'
    + bbox + ';'
)
body = f"[out:json][timeout:90];({query});out center tags;"

endpoints = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

for endpoint in endpoints:
    for attempt in range(1, 3):
        print(f"Trying {endpoint} (attempt {attempt}/2)...")
        try:
            req = urllib.request.Request(
                endpoint,
                data=body.encode("utf-8"),
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "AURIS-X infrastructure research project",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as response:
                data = json.loads(response.read().decode("utf-8"))

            if not isinstance(data.get("elements"), list):
                raise ValueError("Invalid response: elements list missing")

            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            output = raw / f"parks_osm_{stamp}.json"
            metadata_path = raw / f"parks_osm_{stamp}_metadata.json"

            with output.open("x", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)

            metadata = {
                "category": "parks",
                "source": "OpenStreetMap",
                "endpoint": endpoint,
                "retrieved_utc": datetime.now(timezone.utc).isoformat(),
                "bbox_south_west_north_east": [10.85, 76.85, 11.15, 77.15],
                "query": body,
                "element_count": len(data["elements"]),
                "license": "Open Database License (ODbL)",
                "attribution": "© OpenStreetMap contributors",
                "copyright_url": "https://www.openstreetmap.org/copyright",
                "status": "downloaded; validation pending",
            }
            with metadata_path.open("x", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)

            print(f"\nSUCCESS: downloaded {len(data['elements'])} parks-related elements.")
            print(f"Raw file: {output}")
            print(f"Metadata: {metadata_path}")
            raise SystemExit(0)

        except SystemExit:
            raise
        except Exception as exc:
            print(f"Failed: {type(exc).__name__}: {exc}")
            time.sleep(15)

print("\nPARKS DOWNLOAD FAILED on both endpoints.")
print("No existing category files were intentionally changed.")
raise SystemExit(1)
