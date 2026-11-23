Participatory Urban Heat & Green-Corridor Co-Design Simulator

Technical reference · Alexandria, Egypt / Porto, Portugal · 23 November 2026

Use H3 resolution 9 to report neighborhood conditions and compare budgets. Draw and cost an intervention at its actual location. Keep three temperature fields throughout the simulator: land surface temperature (LST), outdoor air temperature at a stated height, and pedestrian thermal exposure such as physiological equivalent temperature (PET). Each answers a different design question.

1. Open data and access paths

Input

Programmatic access

H3 processing and limits

Study areas and grid

Alexandria: CAPMAS/OCHA boundaries, HDX resource list as JSON. Porto: DGT OGC API collections, official CAOP município 1312, code list. H3 cell statistics.

Dissolve the agreed dense-core polygons of El Manshia, Karmouz, Moharam Bek, Bab Shark, Sidi Gaber and El Raml. Record source IDs and a bilingual name crosswalk. Explicitly resolve the First/Second Raml split with local partners before choosing the core extent. For Porto, clip to the municipality. Retain all intersecting hexagons, including coastal slivers. Calculate the land area inside each boundary. The global mean hexagon is 105,332.5 m² = 10.53 ha.

Landsat 8/9 Collection 2 Tier 1 Level-2 surface temperature, both cities

Microsoft STAC collection. POST an AOI and date interval to STAC search with collections=["landsat-c2-l2"]. Keep item IDs beginning LC08_L2SP_ or LC09_L2SP_ and ending _T1. Sign asset URLs with planetary_computer.sign, then read lwir11 and qa_pixel. Microsoft asset example. Earth Engine collection metadata: L8 STAC, L9 STAC. Query scenes via ee.ImageCollection using LANDSAT/LC08/C02/T1_L2 and LANDSAT/LC09/C02/T1_L2, filter PROCESSING_LEVEL=L2SP, select ST_B10.

For raw DN, LST °C = 0.00341802 × DN + 149 − 273.15. Mask fill, dilated cloud, cirrus, cloud, cloud shadow, snow and water (QA_PIXEL bits 0–5 and 7). Retain emissivity/no-data gaps. Thermal sampling is about 100 m, delivered on a 30 m grid. Suggested baseline: June–August 2022–2025, land-area-weighted cell mean per clear date, then median across dates. Publish valid area, dates and scene count. Distinguish clear-sky overpass heat from nighttime and daily maximum heat.

Resident population and age, both cities

JRC GHS-POP R2023A download or ee.Image("JRC/GHSL/P2023A/GHS_POP/2020").select("population_count") (catalogue). WorldPop population and age/sex API provides a common alternative for Egypt and Portugal.

GHS-POP is a modeled count per 100 m pixel. Allocate counts using pixel–cell intersection area divided by original pixel area and check conservation against the clipped AOI total. Use 2020 as the shared estimate, or label the 2025 GHSL epoch as a projection. For age shares use WorldPop age numerator and total from the same product/year. Keep visitor and rider exposure as separate layers.

Porto land cover and sealing

CLMS Urban Atlas Street Tree Layer 2018, Urban Atlas, Imperviousness Density. At https://land.copernicus.eu/api/, use @search, select the Porto package or bounding box, submit @datarequest_post with a bearer token, then poll @datarequest_search. API specification.

Choose a common reference year, e.g. 2018. The Street Tree Layer covers contiguous patches or rows ≥500 m² and ≥10 m wide on artificial surfaces. Calculate mapped canopy fraction and mean 10 m sealing density separately. Validate small trees against the Porto municipal tree inventory, retaining its date.

Porto historical urban climate

VITO’s daily NetCDF index and download script document per-city/year downloads of 100 m daily 2 m air-temperature mean, minimum and maximum for 2008–2017. Zenodo API record lists Portugal.zip for downloadable derived indicators, including Porto. For summer UHI intensity use the EEA numerical GeoTIFF download or ArcGIS REST layer 0. Porto application · UrbClim validation.

The former CDS product was sis-urban-climate-cities. VITO currently directs users to its archive and provides hourly data by request. The EEA layer is modeled summer air-temperature excess above the rural non-water 10th-percentile reference. Use it to test hotspot ranking. For a contemporaneous Landsat comparison, use summers 2013–2017 and Landsat 8. Retain the distinction between an air-temperature anomaly and absolute satellite LST.

OSM vegetation and parks, both cities

POST Overpass QL to interpreter. Trees: natural=tree, natural=tree_row, natural=wood, landuse=forest. Parks: leisure=park, leisure=garden, plus access=*, entrance=* and paths. Tag definitions · crown diameter.

For a surveyed crown diameter d, use a disk of radius d/2. Union overlapping crowns. Keep other points as tree counts and rows as lengths unless surveyed widths exist. Park boundaries represent land use. Verify shade, opening hours and public access separately.

OSM impervious surfaces and transit, both cities

Footprints: building=* excluding no, area:highway=*, amenity=parking, highway=* with surface=asphalt/concrete/paved/paving_stones. Stops: highway=bus_stop, public_transport=platform/stop_position, railway=tram_stop/station/halt, amenity=bus_station. Inspect shelter=* and nearby amenity=shelter, shelter_type=public_transport. Overpass QL · OSM attribution and ODbL.

Union hard-surface polygons after checking materials. Buffer road centerlines by half the measured or assumed width, and flag assumptions. Permeable pavers, unpaved parking and missing surfaces require separate classes. Group a platform and its vehicle stopping point by stop-area relation or checked name/proximity. Audit informal stops and the actual waiting-area shadow with riders.

Common land-cover check

ee.ImageCollection("ESA/WorldCover/v200").first().select("Map"), year 2021, 10 m. Class legend and access.

Compare OSM with class 10 (tree cover) and 50 (built-up), and inspect a stratified sample in each district. These are categorical proxies. Neither class gives a continuous canopy or sealing percentage within its source pixel.

Overpass request pattern. Send the query in the POST form field data. This example retrieves shade-related objects in a small Alexandria bounding box. Substitute the study extent (south, west, north, east), add the selectors above and intersect results with the adopted AOI. Record the extract timestamp and preserve attribution.

[out:json][timeout:60][bbox:31.18,29.88,31.21,29.92];
(
  nwr["natural"~"^(tree|tree_row|wood)$"];
  nwr["leisure"~"^(park|garden)$"];
  nwr["highway"="bus_stop"];
  nwr["public_transport"~"^(platform|stop_position)$"];
);
out geom;

2. Intervention parameters and capital costs

A positive Δ means reference minus treated. Field contrasts, calibrated model results and design costs carry different uncertainties. The unit is one hectare of the stated treatment, or the actual project footprint inside one H3 cell. Costs retain source-year euros. They are benchmarks for scenario comparison, pending local bills of quantities.

Intervention

Local cooling evidence and interpretation

Rough CAPEX and example inside one cell

Street canopy and green corridors

Five Athens streets in exceptionally hot, mostly light-wind weather: 0.5–1.6°C air cooling at 14:00 and 0.4–2.2°C at 17:00 beneath existing canopies. Assign the effect to the newly shaded route for the relevant time and tree age. Tsiros 2010, DOI 10.1016/j.renene.2009.12.021.

İzmir: €21/m² of tree cover, €210,000/ha. An added 1,000 m² costs €21,000 on that basis. Austrian study benchmark: €76.92/m² under its planting assumptions. For an engineered street, estimate pits, soil volume, utilities and irrigation per planted tree. İzmir GCAP 2020, LU1.7 · Johnson et al., Table 3, DOI 10.1177/2399808320974689.

High-albedo paving

Los Angeles field transects: 4–6°C cooler pavement, 0.5°C cooler afternoon air, and 4°C higher midday mean radiant temperature over the reflective surface. At Flisvos, coastal Athens, 4,500 m² of reflective pavement produced an estimated up to 1.9°C peak air cooling under matched simulated weather informed by field measurements. Record the pedestrian radiant penalty separately. Middel et al. 2020, DOI 10.1088/1748-9326/ab87d4 · Santamouris et al. 2012, DOI 10.1016/j.buildenv.2012.01.022.

€57.67–81/m², or €577,000–810,000/ha paved. For 1,000 m²: €57,670–81,000. These are installed material scenarios. Obtain a separate rate for a thin coating on sound pavement. Johnson et al., 2018-value albedo rates · İzmir, LU1.7.

High-albedo roofs

Sicily field case: up to about 20°C cooler roof skin following reflective treatment. A Barcelona heatwave simulation of widespread roof conversion reported 0.67°C average daytime air cooling and 2.22°C maximum in its abstract. Use the latter as a district-scale scenario check. A single rooftop requires a separate local outdoor-air response model. Romeo & Zinzi, DOI 10.1016/j.enbuild.2011.07.023 · Gilabert et al. 2021, DOI 10.1016/j.uclim.2021.100863.

€57.23–83/m², or €572,000–830,000/ha of roof. For 1,000 m²: €57,230–83,000. İzmir’s detailed estimate includes a roof assembly and reflective finish. At scheduled replacement, cost the incremental premium separately. Johnson et al., Table 3 · İzmir, LU1.7 detailed costing.

Pocket parks and restorative shaded plazas

Athens warm-period means: 0.6–1.3°C cooler air in a green garden/courtyard compared with a shaded hard courtyard (28.8°C and 28.1°C versus 29.4°C). Lisbon’s 0.24 ha garden showed a 6.9°C maximum shaded-garden to sunlit-street air contrast. This maximum includes shade and site geometry. Score restoration and comfort through resident reports. Melas et al. 2021, Table 1, DOI 10.30955/gnj.003903 · Oliveira et al. 2011, DOI 10.1016/j.buildenv.2011.04.034.

Thessaloniki 180 m² design with drainage, paving, planting and seats: €23,885.50 for one park in a cell, including wages, equivalent to €133/m² or €1.33m/ha. The authors exclude VAT, design, supervision, contractor profit and contingencies. Existing municipal land and trees matter. Bagiouk et al. 2024, Table 3, DOI 10.1007/s40710-024-00690-x.

Shaded transit stops and pedestrian micro-corridors

Phoenix bus stops, an inland hot-arid analogue: pooled sun–shade differences 0.6–1.0°C air versus 17.3–18.7°C PET across afternoon/morning means. Córdoba street sails: peak 13.2–15.9°C pavement-surface cooling by street orientation. Model the moving shadow over the queue and route at actual travel times. Dzyuban et al., Table 2, DOI 10.1007/s00484-021-02074-4 · Garcia-Nevado et al. 2020, DOI 10.1016/j.scs.2020.102458.

Granada fixed textile pergola €110/m² and İzmir public-space shade €286/m² give €1.10m–2.86m/ha of canopy structure. A 20 m² installation in one cell gives €2,200–5,720, before stop-specific works or equipment. These are public planning estimates with different specifications. Granada project 18, budget · İzmir, LU1.7.

Applying a coefficient. Compute project CAPEX as Σ(unit rate × installed quantity) plus site-specific fixed works. Add annual watering, pruning, recoating and fabric replacement in a separate operating/lifecycle ledger. Reprice quantities in EGP for Alexandria and EUR for Porto using dated local quotes. Model benefits at installation and at mature canopy, allowing for survival, water availability, street orientation, traffic and sea breeze. Use paired treated/reference observations at pedestrian height and on surfaces, during comparable clear, hot periods in each city. Alexandria already has a dense-canyon field/model study to guide site selection. Gaber et al. 2020, DOI 10.1016/j.uclim.2020.100670.

3. Heat vulnerability, co-design and equity

The following equations are proposed simulator settings. IPCC AR4 defines vulnerability through exposure, sensitivity and adaptive capacity without prescribing numerical weights. AR6 distinguishes hazard, exposed people/assets and vulnerability. Name the map an AR4-style heat-priority index and publish its components. IPCC AR4 definitions · IPCC AR6 framing.

Parameter

Formula or decision rule

Implementation

Exposure E, sensitivity S, adaptive capacity A

Common core: E = summer daytime LST. S = share of residents aged 65+ from a common age-grid release. A = share of residents within a proposed 10-minute network walk of a verified, publicly accessible shaded refuge. Larger A means greater capacity.

For refuge access, use population-weighted origins, mapped entrances, opening hours and audited paths. Buffer beyond the study boundary for destinations. Audit access in both cities. Local-only extensions may use night heat, living alone, housing conditions or cooling access. Never infer age, poverty or air-conditioning ownership from building density. Heat vulnerability indicators, Reid et al., DOI 10.1289/ehp.0900683.

Normalize and handle missing data

For indicator j, z = clip[(x − P5)/(P95 − P5), 0, 1]. Reverse as 1 − z if the indicator points the wrong way. For domain D, let m=1 for valid values, else 0. D = Σ(w m z)/Σ(w m), coverage q = Σ(w m)/Σw.

Fix quantiles and weights on the baseline. Use common units and pooled, equally city-weighted quantiles for transfer comparisons. Within-city quantiles answer a local ranking question only. Drop constant indicators in both cities. Suggested reporting rule: require q ≥ 0.67 and each mandatory core indicator; otherwise output NA. Missing, survey-confirmed zero and modeled estimates get different flags. Publish local extensions separately. OECD/JRC composite indicator handbook, DOI 10.1787/9789264043466-en.

H3 priority index

HVIᵢ = 100 × [Eᵢ + Sᵢ + (1 − Aᵢ)]/3. Higher values imply higher priority.

Score inhabited cells with all three domains valid. Keep population count Nᵢ for the number of people reached. Fix baseline HVI for equity comparisons so a successful intervention cannot remove a cell from the priority group. Report missing cells and their population share.

Convert site effects to benefit

For metric m and cell i, bᵢₘ = Σₖ hᵢₖ ΔTₖₘ / Σₖ hᵢₖ; k indexes mutually exclusive locations/times, h is exposed person-minutes. Include zero-benefit time. For an area-average surface scenario, replace h with surface area at the same time.

Enter a Δ only for its measured endpoint and footprint. Combine overlapping treatments once using an explicit joint response, or bracket scenarios until calibrated. A 1°C air reduction over 10% of person-minutes gives 0.1°C average experienced air reduction under that assumption. Use stop counts, waiting times and walk audits for transit; tag estimated footfall.

Participatory weights and NEB score

Each respondent r allocates 100 points across Sustainable, Beautiful, Together. For stratum g, average respondents’ fractions. Wⱼ = Σg πg meanᵣ∈g(pointsᵣⱼ/100), where Σπg=1. Score(p) = Σⱼ Wⱼ vⱼ(p) for a feasible portfolio p and prespecified pillar values v in [0,1].

Map desired routes, waiting spots and candidate refuges in street workshops and online. Choose and disclose stratum shares π by district/user group; publish sample counts, disagreements and unrepresented groups. Score sustainability on thermal relief and irrigation need, beauty on residents’ site ratings, togetherness on step-free access and underserved users reached. Enforce budget, accessible clear width and water limits before scoring. NEB Compass · GIS-MCDA, DOI 10.1080/13658810600661508.

Benefit Gini and minimum guarantee

For nonnegative per-resident benefits bᵢ of one metric, let pᵢ=Nᵢ/ΣN and μ=Σpᵢbᵢ. G = ΣᵢΣⱼ pᵢpⱼ abs(bᵢ−bⱼ)/(2μ). For V, the highest baseline HVI quintile of inhabited cells, R(p) = minᵢ∈V bᵢ(p).

Include zero-benefit cells. G=0 means equal benefits when μ>0; if all benefits are zero, G is undefined. If an intervention causes warming, report the signed effect and harmed population separately; a gain-only Gini must say so. For a Rawlsian rule, maximize R under the budget; break ties by the next-worst benefit, then by NEB score. Publish mean benefit, V’s population-weighted mean and V’s share receiving any benefit alongside G. Repeat for riders with rider shares when data permit. Gini definition, World Bank.

Transferability test. Report the two cities’ shared-core rankings with the same indicators, normalization, eligibility and outcome units. Repeat the ranking across measured cooling ranges, cost scenarios and citizen-group weights. Publish cells that consistently remain high priority and cells whose status depends on incomplete data. A city's extra layers can improve its local design without changing the common benchmark.

