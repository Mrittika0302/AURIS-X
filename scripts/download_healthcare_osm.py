
from pathlib import Path
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import json
import time

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"

# Approximate Coimbatore-area bounding box, not an official boundary.
SOUTH, WEST, NORTH, EAST = 10.85, 76.85, 11.15, 77.15

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    bbox = f"{SOUTH},{WEST},{NORTH},{EAST}"
    query = f"""
    [out:json][timeout:45];
    (
      nwr["amenity"="hospital"]({bbox});
      nwr["amenity"="clinic"]({bbox});
      nwr["amenity"="doctors"]({bbox});
    );
    out center tags;
    """

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = RAW_DIR / f"healthcare_osm_{timestamp}.json"
    metadata_path = RAW_DIR / f"healthcare_osm_{timestamp}_metadata.json"

    print("AURIS-X | Healthcare data download")
    print(f"Bounding box: {bbox}")
    print("Query: hospitals, clinics, doctors")
    print("Note: broad healthcare=* tags are excluded for this first test.")

    last_error = None

    for endpoint in ENDPOINTS:
        print(f"\nTrying endpoint: {endpoint}")

        request = Request(
            endpoint,
            data=query.encode("utf-8"),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "AURIS-X-Student-Research/1.0",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=90) as response:
                raw = response.read()

            data = json.loads(raw.decode("utf-8"))

            if not isinstance(data.get("elements"), list):
                raise ValueError("Response has no valid elements list.")

            # Save only after a valid response is received.
            output.write_bytes(raw)
            elements = data["elements"]

            counts = {}
            for element in elements:
                tags = element.get("tags", {})
                category = tags.get("amenity", "unclassified")
                counts[category] = counts.get(category, 0) + 1

            metadata = {
                "source": "OpenStreetMap via Overpass API",
                "endpoint": endpoint,
                "downloaded_at": datetime.now().astimezone().isoformat(),
                "bounding_box": {
                    "south": SOUTH,
                    "west": WEST,
                    "north": NORTH,
                    "east": EAST,
                },
                "element_count": len(elements),
                "counts_by_amenity": counts,
                "raw_file": output.name,
                "limitations": [
                    "Bounding box is approximate, not an official boundary.",
                    "Only amenity=hospital, clinic, and doctors were queried.",
                    "OpenStreetMap records may be incomplete or duplicated.",
                ],
                "license": "Open Database License (ODbL)",
                "attribution": "© OpenStreetMap contributors",
            }

            metadata_path.write_text(
                json.dumps(metadata, indent=2),
                encoding="utf-8",
            )

            print("\nSUCCESS")
            print(f"Records returned: {len(elements)}")
            print(f"Raw data: {output}")
            print(f"Metadata: {metadata_path}")
            print("Counts:", counts)
            print("Next: validate coordinates and duplicate records.")
            return

        except (HTTPError, URLError, TimeoutError,
                json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
            last_error = error
            print(f"Endpoint failed: {error}")
            time.sleep(3)

    raise RuntimeError(
        "Both endpoints failed. No successful download was confirmed. "
        f"Last error: {last_error}"
    )


if __name__ == "__main__":
    main()
