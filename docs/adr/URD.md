# CanopyCommons — User Requirements Document (URD v1.0 — FROZEN)

## 1. Purpose & Scope
CanopyCommons is a city-agnostic Participatory Urban Heat & Green-Corridor Co-Design Simulator.
- **Primary Pilot:** Alexandria, Egypt (dense coastal core: El Manshia, Karmouz, Moharam Bek, Bab Shark, Sidi Gaber, El Raml).
- **Transferability Benchmark:** Porto, Portugal (CAOP 1312 municipality).
- **Spatial Grain:** Uber H3 Resolution 9 (~10.53 ha) for neighborhood reporting and budget comparison; actual intervention footprint (m²) for CAPEX and localized thermal benefit estimation.

## 2. Core Functional Requirements (Definition of Ready)
- **FR-01 Dual-City Spatial Grid & Provenance:** Parameterized ETL produces H3 Res-9 Parquet/GeoJSON datasets conserving population totals, recording valid land area per coastal sliver, and storing scene counts and missing-data flags (`missing` vs. `confirmed_zero` vs. `modeled`).
- **FR-02 AR4-Style Heat Priority Index (HVI):** Computes $HVI_i = 100 \times [E_i + S_i + (1 - A_i)] / 3$ using summer daytime LST ($E$), 65+ resident share ($S$), and 10-minute network walk access to verified shaded public refuge ($A$). Uses fixed, pooled, equally city-weighted $P_5$/$P_{95}$ normalization and enforces $q \ge 0.67$ plus mandatory core indicators (else `NA`).
- **FR-03 Three-Metric Footprint Physics & Signed Harm Disclosure:** Preserves LST, outdoor air temperature, and pedestrian PET separately; computes person-minute experienced benefit $b_{im} = \sum_k h_{ik}\Delta T_{km} / \sum_k h_{ik}$ including zero-benefit time; explicitly surfaces pedestrian MRT warming penalties (e.g., +4.0°C midday MRT on high-albedo paving) and harmed population counts separately from gains.
- **FR-04 NEB Participatory Co-Design & Stratified Feedback:** Stakeholders distribute 100 points across **Sustainable, Beautiful, Together** and tag specific H3 cells with lived-experience constraints (e.g., informal transit queues, unshaded elderly routes). Group weights aggregate via $W_j = \sum_g \pi_g \text{mean}_{r \in g}(\text{points}_{rj}/100)$ before ranking feasible portfolios by $\text{Score}(p) = \sum_j W_j v_j(p)$.
- **FR-05 Equity & Pareto Engine:** Evaluates feasible portfolios (respecting budget, water, and step-free clear-width constraints) using population-weighted Benefit Gini $G = \sum_i \sum_j p_i p_j |b_i - b_j| / (2\mu)$ and Rawlsian lexicographic maximin $R(p) = \min_{i \in V} b_i(p)$ over the fixed top baseline HVI quintile $V$.
- **FR-06 Traceable AI Deliberation (Google AI Studio / Gemini):** Clusters free-text resident feedback into structured JSON planning trade-offs citing exact `feedback_id` and `h3_index` values. Strictly advisory—never mutates weights without explicit human confirmation.
- **FR-07 Reproducible Dossier Export:** Exports a versioned JSON + Markdown Co-Design Dossier containing parameters, citations, before/after KPIs, unscored population share, signed warming warnings, and stakeholder objections.

## 3. BDD Acceptance Criteria (Gate 2 Verification Contract)

Feature: Dual-City Participatory Heat Simulation & Equity Auditing

  Scenario: Missing core indicator triggers strict NA gating
    Given an Alexandria H3 cell with valid LST and population but weight coverage q = 0.50 (< 0.67)
    When the HVI engine computes neighborhood priority scores
    Then the cell HVI is output as null (NA) rather than imputed
    And the city summary explicitly publishes the unscored population share

  Scenario: Shaded transit stop reports distinct air vs PET relief at footprint scale
    Given a EUR 1,500,000 Alexandria budget and a high-HVI transit hex cell
    When a user places a 20 m² Shaded Transit Stop costing between EUR 2,200 and EUR 5,720
    Then the engine computes experienced rider benefit separately for air cooling (0.6-1.0°C) and PET relief (17.3-18.7°C) weighted by waiting person-minutes
    And the response returns in under 200 ms with source DOI metadata

  Scenario: High-albedo paving surfaces signed pedestrian MRT warming warning
    Given a user applies 1,000 m² of High-Albedo Cool Paving to an inhabited cell
    When the scenario KPIs are calculated
    Then the surface cooling (4-6°C) and afternoon air cooling (0.5°C) are reported alongside a separate +4.0°C midday MRT pedestrian warning and affected population count
    And the gain-only Benefit Gini explicitly carries a disclosure label

  Scenario: Rawlsian priority breaks ties lexicographically across top HVI quintile V
    Given two budget-feasible portfolios that both leave the worst-off cell in V at b = 0
    When the optimizer ranks portfolios under Rawlsian priority
    Then it compares the next-worst cell in V sequentially and breaks remaining ties by the stratified NEB Score(p)
    And it reports the exact percentage of residents in V receiving nonzero benefit

  Scenario: Gemini deliberation synthesizer enforces strict citation traceability
    Given 8 resident comments across Alexandria transit and residential hex cells
    When the planner runs "Synthesize Stakeholder Trade-Offs"
    Then every returned theme includes valid feedback_ids and h3_indices present in the database
    And the active NEB weights remain unchanged until the user clicks "Apply Suggested Weights"