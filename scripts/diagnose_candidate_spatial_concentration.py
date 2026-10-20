
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "data" / "gold" / "healthcare_candidate_sites.csv"

df = pd.read_csv(CANDIDATES)
top10 = df.nsmallest(10, "rank").copy()

print("=" * 68)
print("AURIS-X SPATIAL CONCENTRATION DIAGNOSTIC")
print("Read-only; no existing outputs will be modified.")
print("=" * 68)

print("\nTOP 10 GRID COORDINATES")
for _, r in top10.iterrows():
    print(
        f"Rank {int(r['rank']):2d}: {r['candidate_zone_id']:12s} "
        f"row={int(r['zone_row']):2d}, col={int(r['zone_col']):2d}"
    )

print("\nADJACENCY WITHIN TOP 10")
coords = {
    (int(r["zone_row"]), int(r["zone_col"])): r["candidate_zone_id"]
    for _, r in top10.iterrows()
}

adjacent_pairs = []
for a, id_a in coords.items():
    for b, id_b in coords.items():
        if id_a >= id_b:
            continue
        dr = abs(a[0] - b[0])
        dc = abs(a[1] - b[1])
        if max(dr, dc) == 1:
            adjacent_pairs.append((id_a, id_b))

print("Adjacent pairs, including diagonal neighbours:", len(adjacent_pairs))
for a, b in adjacent_pairs:
    print(f"  {a} <-> {b}")

print("\nTOP 10 GRID EXTENT")
print("Rows:", int(top10["zone_row"].min()), "to", int(top10["zone_row"].max()))
print("Columns:", int(top10["zone_col"].min()), "to", int(top10["zone_col"].max()))
print(
    "Distinct occupied grid positions:",
    top10[["zone_row", "zone_col"]].drop_duplicates().shape[0],
)

print("\nTOP 100 GRID EXTENT")
print("Rows:", int(df["zone_row"].min()), "to", int(df["zone_row"].max()))
print("Columns:", int(df["zone_col"].min()), "to", int(df["zone_col"].max()))
print(
    "Distinct occupied grid positions:",
    df[["zone_row", "zone_col"]].drop_duplicates().shape[0],
)

print("\nINTERPRETATION")
print(
    "Adjacency indicates spatial clustering, not overlap in the actual "
    "population served. Confirming distinct coverage requires a "
    "candidate-specific network before/after simulation."
)
