from pathlib import Path
import json
import numpy as np
import rasterio
from rasterio.windows import from_bounds, Window

root = Path(__file__).resolve().parent.parent
source = root / "data/population/ind_pop_2026_CN_100m_R2025A_v1.tif"
output = root / "data/population/coimbatore_population_2026_approx.tif"
report_path = root / "reports/module6_pixel_comparison.json"

west, south, east, north = 76.85, 10.85, 77.15, 11.15
result = {"source": str(source), "extracted": str(output),
          "method": "Read-only comparison against the source raster window"}

try:
    with rasterio.open(source) as src, rasterio.open(output) as dst:
        if src.crs is None or src.crs.to_epsg() != 4326:
            raise ValueError(f"Unexpected source CRS: {src.crs}")

        window = from_bounds(west, south, east, north, transform=src.transform)
        window = window.round_offsets().round_lengths()
        window = window.intersection(Window(0, 0, src.width, src.height))

        original = src.read(1, window=window, masked=True)
        extracted = dst.read(1, masked=True)

        same_shape = original.shape == extracted.shape
        same_crs = src.crs == dst.crs
        expected_transform = src.window_transform(window)
        same_transform = (
            same_shape and
            np.allclose(tuple(expected_transform), tuple(dst.transform),
                        rtol=0, atol=1e-10)
        )
        same_nodata = src.nodata == dst.nodata
        same_mask = same_shape and np.array_equal(
            np.ma.getmaskarray(original), np.ma.getmaskarray(extracted)
        )

        a = original.compressed()
        b = extracted.compressed()
        same_values = (
            same_shape and same_mask and a.shape == b.shape and
            np.array_equal(a, b, equal_nan=True)
        )

        result.update({
            "source_crs": str(src.crs),
            "output_crs": str(dst.crs),
            "expected_dimensions": list(original.shape[::-1]),
            "actual_dimensions": [dst.width, dst.height],
            "same_dimensions": same_shape,
            "same_crs": same_crs,
            "same_geotransform": bool(same_transform),
            "source_nodata": src.nodata,
            "output_nodata": dst.nodata,
            "same_nodata_metadata": same_nodata,
            "same_valid_data_mask": bool(same_mask),
            "valid_source_pixels": int(a.size),
            "valid_output_pixels": int(b.size),
            "same_pixel_values": bool(same_values),
            "max_absolute_pixel_difference": (
                float(np.max(np.abs(a.astype("float64") - b.astype("float64"))))
                if a.shape == b.shape and a.size else None
            ),
            "pixel_comparison_pass": all([
                same_shape, same_crs, same_transform, same_nodata,
                same_mask, same_values
            ])
        })
except Exception as e:
    result["error"] = repr(e)
    result["pixel_comparison_pass"] = False

report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
print(f"\nReport saved: {report_path}")
