"""
CanopyCommons Phase 1 ETL: Parameterized Dual-City H3 Resolution-9 Builder.

Usage:
  # Fast deterministic run (CI / testing / UI prototyping):
  python -m etl.build_grid --city all --mode offline-sample

  # Live open-data run (Planetary Computer Landsat 8/9 STAC + OSM Overpass):
  python -m etl.build_grid --city all --mode live
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import time 
import geopandas as gpd
import h3
import numpy as np
import pandas as pd
import requests
import yaml
from shapely.geometry import Point, Polygon, box, mapping

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "cities.yaml"
DATA_DIR = ROOT / "data"

# QA_PIXEL bitmask: fill(0), dilated_cloud(1), cirrus(2), cloud(3), shadow(4), snow(5), water(7)
QA_MASK = (1 << 0) | (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4) | (1 << 5) | (1 << 7)


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def bbox_to_h3_gdf(bbox: list[float], res: int, utm_epsg: int) -> gpd.GeoDataFrame:
    """Generate H3 Res-9 cells intersecting bbox and compute exact land area in m2."""
    min_lon, min_lat, max_lon, max_lat = bbox
    aoi_poly = box(min_lon, min_lat, max_lon, max_lat)
    cells = sorted(h3.geo_to_cells(mapping(aoi_poly), res))

    records = []
    for cell in cells:
        boundary_latlng = h3.cell_to_boundary(cell)
        poly = Polygon([(lng, lat) for lat, lng in boundary_latlng])
        clipped = poly.intersection(aoi_poly)
        records.append({"h3_index": cell, "geometry": poly, "clipped_geom": clipped})

    gdf = gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")
    clipped_series = gpd.GeoSeries(gdf["clipped_geom"], crs="EPSG:4326").to_crs(epsg=utm_epsg)
    gdf["land_area_m2"] = clipped_series.area.round(2)
    return gdf.drop(columns=["clipped_geom"])
def h3_centers_geoseries(h3_indices: pd.Series) -> gpd.GeoSeries:
    """Exact H3 cell centers without geographic-CRS centroid warnings."""
    pts = [Point(lng, lat) for lat, lng in (h3.cell_to_latlng(c) for c in h3_indices)]
    return gpd.GeoSeries(pts, index=h3_indices.index, crs="EPSG:4326")
def fetch_live_landsat_lst(
    gdf: gpd.GeoDataFrame, bbox: list[float], stac_cfg: dict[str, Any]
) -> tuple[pd.Series, pd.Series, dict[str, Any]]:
    """Query Microsoft Planetary Computer Landsat 8/9 C2 L2 summer daytime LST."""
    import planetary_computer
    import pystac_client
    import rasterio
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds

    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )

    items = []
    for year in stac_cfg["baseline_years"]:
        search = catalog.search(
            collections=[stac_cfg["collection"]],
            bbox=bbox,
            datetime=f"{year}-06-01/{year}-08-31",
            query={"eo:cloud_cover": {"lt": 20}},
        )
        for item in search.items():
            if (
                any(item.id.startswith(p) for p in stac_cfg["item_prefixes"])
                and item.id.endswith(stac_cfg["item_suffix"])
            ):
                items.append(item)

    if not items:
        raise RuntimeError("No clear Landsat 8/9 L2SP T1 scenes found for bbox.")

    items = sorted(items, key=lambda x: x.properties.get("eo:cloud_cover", 100))[:6]
    centers_4326 = h3_centers_geoseries(gdf["h3_index"])
    scene_means: list[np.ndarray] = []
    water_votes: list[np.ndarray] = []
    scene_ids: list[str] = []

    for item in items:
        lwir_href = item.assets[stac_cfg["thermal_asset"]].href
        qa_href = item.assets[stac_cfg["qa_asset"]].href
        with rasterio.open(lwir_href) as src_t, rasterio.open(qa_href) as src_qa:
            reproj_bbox = transform_bounds("EPSG:4326", src_t.crs, *bbox)
            win = from_bounds(*reproj_bbox, src_t.transform).round_offsets().round_lengths()
            dn = src_t.read(1, window=win).astype(np.float64)
            qa = src_qa.read(1, window=win)
            win_transform = src_t.window_transform(win)

            valid = (dn > 0) & ((qa & QA_MASK) == 0)
            is_water_px = (qa & (1 << 7)) != 0
            lst_c = np.where(
                valid,
                stac_cfg["lst_scale"] * dn + stac_cfg["lst_offset_k"] + stac_cfg["kelvin_to_c"],
                np.nan,
            )

            pts_proj = centers_4326.to_crs(src_t.crs)
            vals = np.full(len(gdf), np.nan, dtype=np.float64)
            water_cell = np.zeros(len(gdf), dtype=bool)
            for idx, pt in enumerate(pts_proj):
                row, col = rasterio.transform.rowcol(win_transform, pt.x, pt.y)
                r0, r1 = max(0, row - 3), min(lst_c.shape[0], row + 4)
                c0, c1 = max(0, col - 3), min(lst_c.shape[1], col + 4)
                patch = lst_c[r0:r1, c0:c1]
                w_patch = is_water_px[r0:r1, c0:c1]
                if patch.size > 0 and np.isfinite(patch).any():
                    vals[idx] = float(np.nanmean(patch))
                elif w_patch.size > 0 and w_patch.mean() > 0.5:
                    water_cell[idx] = True

            scene_means.append(vals)
            water_votes.append(water_cell)
            scene_ids.append(item.id)

    stacked = np.vstack(scene_means)
    median_lst = np.full(len(gdf), np.nan, dtype=np.float64)
    has_val = np.isfinite(stacked).any(axis=0)
    median_lst[has_val] = np.nanmedian(stacked[:, has_val], axis=0)

    is_water = np.vstack(water_votes).mean(axis=0) > 0.5
    meta = {
        "source": "Microsoft Planetary Computer landsat-c2-l2",
        "scene_count": len(scene_ids),
        "scene_ids": scene_ids,
    }
    return pd.Series(median_lst, index=gdf.index), pd.Series(is_water, index=gdf.index), meta

def fetch_live_osm_features(gdf: gpd.GeoDataFrame, bbox: list[float]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Query OSM Overpass API for parks, trees, and transit stops with mirror fallback."""
    min_lon, min_lat, max_lon, max_lat = bbox
    query = f"""
    [out:json][timeout:60][bbox:{min_lat},{min_lon},{max_lat},{max_lon}];
    (
      nwr["natural"~"^(tree|tree_row|wood)$"];
      nwr["leisure"~"^(park|garden)$"];
      nwr["highway"="bus_stop"];
      nwr["public_transport"~"^(platform|stop_position)$"];
      nwr["railway"~"^(tram_stop|station|halt)$"];
      nwr["amenity"="bus_station"];
    );
    out center;
    """
    headers = {
        "User-Agent": "CanopyCommons-ETL/1.0 (academic urban heat co-design research)",
        "Accept": "application/json",
    }
    endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://lz4.overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    ]

    last_err: Exception | None = None
    data: dict[str, Any] | None = None
    used_endpoint = ""
    for url in endpoints:
        try:
            resp = requests.post(url, data={"data": query}, headers=headers, timeout=90)
            resp.raise_for_status()
            data = resp.json()
            used_endpoint = url
            break
        except Exception as exc:
            last_err = exc
            time.sleep(2)

    if data is None:
        raise RuntimeError(f"All Overpass mirrors failed: {last_err}")

    elements = data.get("elements", [])
    counts = {c: {"tree_nodes": 0, "park_nodes": 0, "transit_stops": 0, "sheltered_stops": 0} for c in gdf["h3_index"]}
    for el in elements:
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if lat is None or lon is None:
            continue
        cell = h3.latlng_to_cell(lat, lon, 9)
        if cell not in counts:
            continue
        tags = el.get("tags", {})
        if tags.get("natural") in {"tree", "tree_row", "wood"}:
            counts[cell]["tree_nodes"] += 1
        if tags.get("leisure") in {"park", "garden"} and tags.get("access", "yes") != "private":
            counts[cell]["park_nodes"] += 1
        if (
            tags.get("highway") == "bus_stop"
            or tags.get("public_transport") in {"platform", "stop_position"}
            or tags.get("railway") in {"tram_stop", "station", "halt"}
            or tags.get("amenity") == "bus_station"
        ):
            counts[cell]["transit_stops"] += 1
            if tags.get("shelter") == "yes":
                counts[cell]["sheltered_stops"] += 1

    df = pd.DataFrame.from_dict(counts, orient="index").reset_index().rename(columns={"index": "h3_index"})
    meta = {
        "source": "OpenStreetMap Overpass API (ODbL)",
        "endpoint": used_endpoint,
        "extract_utc": datetime.now(timezone.utc).isoformat(),
        "element_count": len(elements),
    }
    return df, meta


def generate_offline_sample_layers(gdf: gpd.GeoDataFrame, city_key: str) -> pd.DataFrame:
    """Deterministic, physically plausible synthetic baseline for fast CI/dev testing."""
    rng = np.random.default_rng(42 if city_key == "alexandria" else 1312)
    centroids = h3_centers_geoseries(gdf["h3_index"])
    lats = centroids.y.to_numpy()
    lons = centroids.x.to_numpy()

    # Coastal cooling gradient (Alexandria north shore cooler; Porto west Atlantic cooler)
    if city_key == "alexandria":
        inland_norm = (lats.max() - lats) / max(lats.max() - lats.min(), 1e-6)
        base_lst = 36.5 + 8.5 * inland_norm + rng.normal(0, 1.4, len(gdf))
        pop = np.round(rng.lognormal(mean=7.6, sigma=0.55, size=len(gdf))).astype(int)
        age65_share = np.clip(rng.normal(0.075, 0.025, len(gdf)), 0.02, 0.22)
    else:
        inland_norm = (lons - lons.min()) / max(lons.max() - lons.min(), 1e-6)
        base_lst = 30.0 + 7.5 * inland_norm + rng.normal(0, 1.3, len(gdf))
        pop = np.round(rng.lognormal(mean=6.4, sigma=0.60, size=len(gdf))).astype(int)
        age65_share = np.clip(rng.normal(0.235, 0.045, len(gdf)), 0.08, 0.42)

    tree_nodes = rng.poisson(lam=12 if city_key == "porto" else 4, size=len(gdf))
    park_nodes = rng.binomial(n=2, p=0.22 if city_key == "porto" else 0.09, size=len(gdf))
    transit_stops = rng.poisson(lam=2.5, size=len(gdf))
    sheltered_stops = np.minimum(transit_stops, rng.binomial(n=np.maximum(transit_stops, 1), p=0.45 if city_key == "porto" else 0.18))
    refuge_access_share = np.clip(0.18 + 0.35 * (park_nodes > 0) + 0.02 * tree_nodes + rng.normal(0, 0.10, len(gdf)), 0.0, 1.0)

    # Inject 3% deliberate missing-data cells to test q >= 0.67 NA gating
    missing_mask = rng.random(len(gdf)) < 0.03
    lst_series = np.where(missing_mask, np.nan, np.round(base_lst, 2))

    return pd.DataFrame(
        {
            "h3_index": gdf["h3_index"],
            "lst_summer_c": lst_series,
            "population_count": pop,
            "age_65_plus_share": np.round(age65_share, 4),
            "refuge_access_10min_share": np.round(refuge_access_share, 4),
            "tree_nodes": tree_nodes,
            "park_nodes": park_nodes,
            "transit_stops": transit_stops,
            "sheltered_stops": sheltered_stops,
            "data_status": np.where(missing_mask, "missing", "modeled"),
        }
    )


def compute_refuge_proxy_from_osm(df: pd.DataFrame) -> pd.Series:
    """
    Fast 10-minute network-walk refuge proxy using H3 k-ring=2 (~400-500m radius)
    over public parks and dense tree patches (flagged as modeled until field-audited).
    """
    refuge_cells = set(df.loc[(df["park_nodes"] > 0) | (df["tree_nodes"] >= 15), "h3_index"])
    scores = []
    for cell in df["h3_index"]:
        ring1 = set(h3.grid_disk(cell, 1))
        ring2 = set(h3.grid_disk(cell, 2))
        if cell in refuge_cells:
            scores.append(0.90)
        elif ring1 & refuge_cells:
            scores.append(0.65)
        elif ring2 & refuge_cells:
            scores.append(0.35)
        else:
            scores.append(0.05)
    return pd.Series(scores, index=df.index)


def compute_pooled_bounds(frames: dict[str, pd.DataFrame], p_low: float, p_high: float) -> dict[str, dict[str, float]]:
    """
    Compute fixed, equally city-weighted pooled P5/P95 bounds across cities.
    Sampling each city to equal effective weight prevents cell-count imbalance.
    """
    indicators = ["lst_summer_c", "age_65_plus_share", "refuge_access_10min_share"]
    bounds: dict[str, dict[str, float]] = {}
    for col in indicators:
        weighted_samples = []
        target_n = 2000
        rng = np.random.default_rng(2026)
        for df in frames.values():
            valid = df[col].dropna().to_numpy()
            if len(valid) > 0:
                weighted_samples.append(rng.choice(valid, size=target_n, replace=True))
        pooled = np.concatenate(weighted_samples)
        bounds[col] = {
            "p_low": float(np.percentile(pooled, p_low)),
            "p_high": float(np.percentile(pooled, p_high)),
        }
    return bounds


def apply_hvi_and_gating(df: pd.DataFrame, bounds: dict[str, dict[str, float]], min_q: float) -> pd.DataFrame:
    """Apply AR4-style HVI = 100 * [E + S + (1 - A)] / 3 with strict q >= 0.67 NA gating."""
    out = df.copy()

    def norm(series: pd.Series, col: str) -> pd.Series:
        lo, hi = bounds[col]["p_low"], bounds[col]["p_high"]
        denom = hi - lo if not math.isclose(hi, lo) else 1.0
        return ((series - lo) / denom).clip(0.0, 1.0)

    out["e_score"] = norm(out["lst_summer_c"], "lst_summer_c")
    out["s_score"] = norm(out["age_65_plus_share"], "age_65_plus_share")
    out["a_score"] = norm(out["refuge_access_10min_share"], "refuge_access_10min_share")

    valid_e = out["e_score"].notna().astype(float)
    valid_s = out["s_score"].notna().astype(float)
    valid_a = out["a_score"].notna().astype(float)
    out["weight_coverage_q"] = ((valid_e + valid_s + valid_a) / 3.0).round(4)

    mandatory_ok = (valid_e == 1.0) & (valid_s == 1.0) & (valid_a == 1.0) & (out["weight_coverage_q"] >= min_q)
    out["baseline_hvi"] = np.where(
        mandatory_ok & (out["population_count"] > 0),
        np.round(100.0 * (out["e_score"] + out["s_score"] + (1.0 - out["a_score"])) / 3.0, 2),
        np.nan,
    )

    # Freeze top baseline HVI quintile V among valid inhabited cells
    valid_hvi = out["baseline_hvi"].dropna()
    q80 = float(valid_hvi.quantile(0.80)) if len(valid_hvi) > 0 else np.nan
    out["in_top_hvi_quintile_v"] = out["baseline_hvi"] >= q80
    return out


def build_city_raw(city_key: str, cfg: dict[str, Any], mode: str) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    city_cfg = cfg["cities"][city_key]
    utm_epsg = city_cfg.get("utm_epsg", 32636 if city_key == "alexandria" else 32629)
    gdf = bbox_to_h3_gdf(city_cfg["bbox"], cfg["h3_resolution"], utm_epsg)
    prov: dict[str, Any] = {"city": city_key, "mode": mode, "built_utc": datetime.now(timezone.utc).isoformat()}

    if mode == "offline-sample":
        layers = generate_offline_sample_layers(gdf, city_key)
        gdf = gdf.merge(layers, on="h3_index", how="left")
        prov["note"] = "Deterministic offline sample for CI/dev testing; rerun with --mode live for Landsat + OSM."
        return gdf, prov

    lst_series, is_water, lst_meta = fetch_live_landsat_lst(gdf, city_cfg["bbox"], cfg["stac_landsat"])
    osm_df, osm_meta = fetch_live_osm_features(gdf, city_cfg["bbox"])
    time.sleep(2)
    gdf = gdf.merge(osm_df, on="h3_index", how="left")
    gdf["lst_summer_c"] = lst_series.round(2)
    gdf["refuge_access_10min_share"] = compute_refuge_proxy_from_osm(gdf)

    sample_demo = generate_offline_sample_layers(gdf, city_key)[["h3_index", "population_count", "age_65_plus_share"]]
    gdf = gdf.merge(sample_demo, on="h3_index", how="left")
    gdf.loc[is_water, "population_count"] = 0
    gdf["data_status"] = np.where(
        is_water,
        "water_masked",
        np.where(gdf["lst_summer_c"].isna(), "missing", "measured_lst_osm_modeled_demo"),
    )

    prov["landsat"] = lst_meta
    prov["osm"] = osm_meta
    prov["demographics_note"] = "Replace with GHS-POP R2023A + WorldPop 65+ GeoTIFF clipping for final publication run."
    return gdf, prov


def main() -> None:
    parser = argparse.ArgumentParser(description="CanopyCommons Dual-City H3 ETL")
    parser.add_argument("--city", choices=["alexandria", "porto", "all"], default="all")
    parser.add_argument("--mode", choices=["offline-sample", "live"], default="offline-sample")
    args = parser.parse_args()

    cfg = load_config()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    target_cities = ["alexandria", "porto"] if args.city == "all" else [args.city]

    raw_gdfs: dict[str, gpd.GeoDataFrame] = {}
    provenance: dict[str, Any] = {}

    for city_key in target_cities:
        print(f"[ETL] Building {city_key} ({args.mode})...")
        gdf, prov = build_city_raw(city_key, cfg, args.mode)
        raw_gdfs[city_key] = gdf
        provenance[city_key] = prov

    bounds = compute_pooled_bounds(
        raw_gdfs,
        cfg["normalization"]["lower_percentile"],
        cfg["normalization"]["upper_percentile"],
    )
    min_q = cfg["normalization"]["min_domain_weight_coverage_q"]

    for city_key, gdf in raw_gdfs.items():
        final_gdf = apply_hvi_and_gating(gdf, bounds, min_q)
        total_pop = int(final_gdf["population_count"].sum())
        unscored_pop = int(final_gdf.loc[final_gdf["baseline_hvi"].isna(), "population_count"].sum())
        provenance[city_key]["summary"] = {
            "cell_count": len(final_gdf),
            "scored_cells": int(final_gdf["baseline_hvi"].notna().sum()),
            "total_population": total_pop,
            "unscored_population_share": round(unscored_pop / max(total_pop, 1), 4),
        }
        final_gdf.to_parquet(DATA_DIR / f"{city_key}_h3.parquet", index=False)
        final_gdf.to_file(DATA_DIR / f"{city_key}_h3.geojson", driver="GeoJSON")
        print(f"[ETL] Wrote {city_key}: {len(final_gdf)} H3 cells, unscored pop share = {provenance[city_key]['summary']['unscored_population_share']:.2%}")

    with (DATA_DIR / "provenance.json").open("w", encoding="utf-8") as f:
        json.dump({"pooled_bounds": bounds, "cities": provenance}, f, indent=2)
    print("[ETL] Saved data/provenance.json")


if __name__ == "__main__":
    main()