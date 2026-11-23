"""Gate 1 automated verification for CanopyCommons H3 datasets."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
import h3

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
REQUIRED_COLS = {
    "h3_index",
    "geometry",
    "land_area_m2",
    "lst_summer_c",
    "population_count",
    "age_65_plus_share",
    "refuge_access_10min_share",
    "weight_coverage_q",
    "baseline_hvi",
    "in_top_hvi_quintile_v",
    "data_status",
}


def validate_city(city: str) -> list[str]:
    errors: list[str] = []
    pq = DATA_DIR / f"{city}_h3.parquet"
    gj = DATA_DIR / f"{city}_h3.geojson"
    if not pq.exists() or not gj.exists():
        return [f"{city}: missing Parquet or GeoJSON output."]

    gdf = gpd.read_parquet(pq)
    missing = REQUIRED_COLS - set(gdf.columns)
    if missing:
        errors.append(f"{city}: missing required columns {sorted(missing)}")
        return errors

    if not gdf["h3_index"].apply(h3.is_valid_cell).all():
        errors.append(f"{city}: invalid H3 cell index detected.")
    if (gdf["land_area_m2"] <= 0).any():
        errors.append(f"{city}: non-positive land_area_m2 detected.")
    if not gdf.geometry.is_valid.all():
        errors.append(f"{city}: invalid polygon geometry detected.")

    # Verify strict q >= 0.67 NA gating
    low_q = gdf[gdf["weight_coverage_q"] < 0.67]
    if low_q["baseline_hvi"].notna().any():
        errors.append(f"{city}: HVI was silently populated on a cell with q < 0.67.")

    # Verify physical LST sanity bounds
    valid_lst = gdf["lst_summer_c"].dropna()
    if ((valid_lst < 10.0) | (valid_lst > 68.0)).any():
        errors.append(f"{city}: implausible summer LST values outside [10, 68] C.")

    # Verify top quintile V contains ~20% of scored cells
    scored = gdf[gdf["baseline_hvi"].notna()]
    v_ratio = scored["in_top_hvi_quintile_v"].mean()
    if not (0.15 <= v_ratio <= 0.25):
        errors.append(f"{city}: top quintile V share out of bounds ({v_ratio:.2%}).")

    print(f"[PASS] {city}: {len(gdf)} cells | {len(scored)} scored | V share = {v_ratio:.1%}")
    return errors


def main() -> None:
    prov_path = DATA_DIR / "provenance.json"
    if not prov_path.exists():
        print("[FAIL] Missing data/provenance.json")
        sys.exit(1)

    with prov_path.open("r", encoding="utf-8") as f:
        prov = json.load(f)
    assert "pooled_bounds" in prov, "Missing pooled_bounds in provenance.json"

    all_errors: list[str] = []
    for city in ["alexandria", "porto"]:
        all_errors.extend(validate_city(city))

    if all_errors:
        for e in all_errors:
            print(f"[FAIL] {e}")
        sys.exit(1)

    print("[GATE 1 PASSED] Both dual-city H3 datasets and provenance verified.")


if __name__ == "__main__":
    main()