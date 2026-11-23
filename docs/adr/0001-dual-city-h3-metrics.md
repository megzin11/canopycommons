# ADR-0001: Dual-City H3 Reporting vs. Footprint Costing & Pooled Normalization

- **Status:** Accepted (Phase 0 Freeze)
- **Context:** Combining Alexandria (primary lived-experience pilot) and Porto (EU open-data benchmark) creates two risks: (1) diluting small, high-impact micro-interventions like 20 m² bus-stop shelters across 10.53 ha H3 hexagons, and (2) distorting cross-city comparisons due to uneven EU vs. Egyptian municipal census layers.
- **Decisions:**
  1. **Decoupled Spatial Grain:** Report neighborhood exposure, HVI, and equity on Uber H3 Resolution 9, while calculating CAPEX and person-minute thermal relief strictly at the treated footprint scale.
  2. **Three-Field Temperature Model:** Never collapse LST, 2 m air temperature, and pedestrian PET into one number; log signed radiant warming penalties separately.
  3. **Shared-Core Pooled Normalization:** Compute the cross-city HVI using only common indicators (Landsat 8/9 LST, GHS-POP/WorldPop 65+, OSM 10-min shaded refuge access) normalized on fixed, equal-city-weighted P5/P95 bounds. Keep Porto-only CLMS/UrbClim layers as optional local validation overlays.
- **Consequences:** Slightly more explicit Pydantic schema fields, in exchange for zero black-box assumptions and direct scientific defensibility across both AISS and GeoTech admissions reviews.