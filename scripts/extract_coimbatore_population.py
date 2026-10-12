
from pathlib import Path
import json

import numpy as np
import rasterio
from rasterio.windows import from_bounds


ROOT = Path(__file__).resolve().parent.parent

SOURCE = (
    ROOT / "data" / "population"
    / "ind_pop_2026_CN_100m_R2025A_v1.tif"
)

OUTPUT = (
    ROOT / "data" / "population"
    / "coimbatore_population_2026_approx.tif"
)

REPORT = ROOT / "reports" / "coimbatore_population_extraction.json"

# Approximate study bounds used in our earlier OSM downloads.
# These are NOT an official Coimbatore administrative boundary.
WEST, SOUTH, EAST, NORTH = 76.85, 10.85, 77.15, 11.15


def main():
    if not SOURCE.exists():
        raise FileNotFoundError(f"Source raster not found: {SOURCE}")

    with rasterio.open(SOURCE) as src:
        if src.crs is None:
            raise ValueError("Source raster has no coordinate reference system.")

        if src.crs.to_epsg() != 4326:
            raise ValueError(
                f"Expected EPSG:4326, found {src.crs}. "
                "Reprojection is needed before using these bounds."
            )

        window = from_bounds(
            WEST, SOUTH, EAST, NORTH,
            transform=src.transform
        )
        window = window.round_offsets().round_lengths()
        window = window.intersection(
            rasterio.windows.Window(0, 0, src.width, src.height)
        )

        if window.width <= 0 or window.height <= 0:
            raise ValueError("Study bounds do not overlap the raster.")

        data = src.read(1, window=window, masked=True)
        profile = src.profile.copy()
        profile.update(
            width=data.shape[1],
            height=data.shape[0],
            transform=src.window_transform(window),
            compress="deflate"
        )

        valid = data.compressed()
        if valid.size == 0:
            raise ValueError("No valid population pixels in the study bounds.")

        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(OUTPUT, "w", **profile) as dst:
            dst.write(data.filled(src.nodata).astype(src.dtypes[0]), 1)

        report = {
            "source_file": str(SOURCE),
            "output_file": str(OUTPUT),
            "crs": str(src.crs),
            "approximate_study_bounds": {
                "west": WEST,
                "south": SOUTH,
                "east": EAST,
                "north": NORTH,
            },
            "boundary_note": (
                "Rectangular extraction only; not an official city boundary."
            ),
            "width_pixels": int(data.shape[1]),
            "height_pixels": int(data.shape[0]),
            "valid_pixel_count": int(valid.size),
            "nodata_value": src.nodata,
            "minimum_valid_value": float(valid.min()),
            "maximum_valid_value": float(valid.max()),
            "mean_valid_value": float(valid.mean()),
            "sum_of_valid_raster_values": float(valid.sum(dtype=np.float64)),
            "sum_interpretation": (
                "Raster-value sum only. Treat as population total only after "
                "confirming the dataset units and product documentation."
            ),
        }

    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("POPULATION EXTRACTION COMPLETE")
    print(json.dumps(report, indent=2))
    print(f"\nRaster saved to: {OUTPUT}")
    print(f"Report saved to: {REPORT}")


if __name__ == "__main__":
    main()
