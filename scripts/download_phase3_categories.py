import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

BBOX = "(10.85,76.85,11.15,77.15)"
ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

CATEGORIES = {
    "transport": 'nwr["public_transport"]{bbox};nwr["highway"="bus_stop"]{bbox};nwr["amenity"="bus_station"]{bbox};nwr["railway"~"^(station|halt|tram_stop|subway_entrance)$"]{bbox};nwr["aeroway"="terminal"]{bbox};',
    "parks": 'nwr["leisure"~"^(park|playground|garden|nature_reserve|recreation_ground|pitch)$"]{bbox};nwr["landuse"~"^(recreation_ground|village_green)$"]{bbox};',
    "water": 'nwr["amenity"="drinking_water"]{bbox};nwr["man_made"~"^(water_tower|reservoir_covered|water_works|water_well)$"]{bbox};nwr["water"="reservoir"]{bbox};nwr["waterway"="water_point"]{bbox};',
    "sanitation": 'nwr["amenity"="toilets"]{bbox};nwr["man_made"~"^(wastewater_plant|sewage_pumping_station)$"]{bbox};nwr["sewer"]{bbox};',
    "emergency_services": 'nwr["amenity"~"^(fire_station|police|ambulance_station)$"]{bbox};nwr["emergency"]{bbox};',
}

def existing_snapshot(category):
    for path in sorted(RAW.glob(f"{category}_osm_*.json"), reverse=True):
        if path.name.endswith("_metadata.json"):
            continue
        metadata = path.with_name(path.stem + "_metadata.json")
        if not metadata.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data.get("elements"), list):
                return path, len(data["elements"])
        except (OSError, ValueError, AttributeError):
            pass
    return None

def download(category, query):
    body = f"[out:json][timeout:90];({query.format(bbox=BBOX)});out center tags;"
    errors = []
    for endpoint in ENDPOINTS:
        for attempt in range(1, 3):
            try:
                request = urllib.request.Request(
                    endpoint,
                    data=body.encode("utf-8"),
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "User-Agent": "AURIS-X infrastructure research project",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=120) as response:
                    data = json.loads(response.read().decode("utf-8"))
                if not isinstance(data.get("elements"), list):
                    raise ValueError("Response has no valid elements list")

                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                path = RAW / f"{category}_osm_{stamp}.json"
                meta_path = RAW / f"{category}_osm_{stamp}_metadata.json"
                # Exclusive creation prevents overwriting existing data.
                with path.open("x", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
                metadata = {
                    "category": category,
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
                with meta_path.open("x", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=2)
                return {
                    "category": category, "status": "DOWNLOADED",
                    "count": len(data["elements"]), "file": str(path),
                    "endpoint": endpoint,
                }
            except Exception as exc:
                message = f"{endpoint} attempt {attempt}: {type(exc).__name__}: {exc}"
                errors.append(message)
                print(f"  Failed: {message}")
                time.sleep(10)
    return {
        "category": category, "status": "FAILED",
        "errors": errors,
    }

def main():
    results = []
    for index, (category, query) in enumerate(CATEGORIES.items(), 1):
        print(f"\n[{index}/{len(CATEGORIES)}] {category}")
        saved = existing_snapshot(category)
        if saved:
            path, count = saved
            print(f"  SKIPPED: existing valid snapshot ({count} elements)")
            results.append({
                "category": category, "status": "SKIPPED_EXISTING",
                "count": count, "file": str(path),
            })
            continue

        result = download(category, query)
        results.append(result)
        if result["status"] == "DOWNLOADED":
            print(f"  Saved {result['count']} elements")
            print(f"  File: {result['file']}")
        else:
            print("  FAILED on available endpoints; moving to next category.")
        # Be considerate to public Overpass services.
        time.sleep(15)

    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source": "OpenStreetMap via Overpass API",
        "results": results,
    }
    report_path = ROOT / "reports" / "phase3_category_download_summary.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n--- DOWNLOAD SUMMARY ---")
    for result in results:
        print(f"{result['category']}: {result['status']}")
    print(f"\nSummary report: {report_path}")
    print("A FAILED category can be retried later; it does not mean no data exists.")

if __name__ == "__main__":
    main()
