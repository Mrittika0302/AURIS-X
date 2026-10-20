from pathlib import Path
import json

root = Path.cwd()
report = root / "reports/PHASE3_CLOSEOUT_AUDIT.md"
extent_file = root / "reports/module6_boundary_extent_check.json"
pixel_file = root / "reports/module6_pixel_comparison.json"

extent = json.loads(extent_file.read_text(encoding="utf-8"))
pixel = json.loads(pixel_file.read_text(encoding="utf-8")) if pixel_file.exists() else {}

section = """
## Module 6 — Population raster verification update

- Pixel extraction comparison: """ + ("PASS" if pixel.get("pixel_comparison_pass") else "See pixel comparison report; pass flag not confirmed") + """.
- Raster extent covers the DataMeet community-curated 2011 Coimbatore ward reference extent: """ + str(extent.get("raster_covers_boundary_extent")) + """.
- Reference contains """ + str(extent.get("ward_feature_count")) + """ ward features.
- Extent comparison report: `reports/module6_boundary_extent_check.json`.
- Pixel comparison report: `reports/module6_pixel_comparison.json`.
- Limitation: this does not verify current official/legal boundary compatibility, validate all polygon geometry, or clip raster cells to the boundary. Source-download provenance also remains to be confirmed.
"""

if not report.exists():
    raise FileNotFoundError(f"Closeout report not found: {report}")

content = report.read_text(encoding="utf-8")
heading = "## Module 6 — Population raster verification update"
if heading in content:
    content = content[:content.index(heading)].rstrip() + "\n\n"
report.write_text(content.rstrip() + "\n\n" + section.strip() + "\n", encoding="utf-8")
print("Updated:", report)
print("Boundary extent coverage:", extent.get("raster_covers_boundary_extent"))
print("Pixel comparison pass:", pixel.get("pixel_comparison_pass", "not confirmed"))
