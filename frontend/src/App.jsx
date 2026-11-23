import { useEffect, useState } from 'react';
import { api } from './api';
import HeatMap from './components/HeatMap';
import ParetoChart from './components/ParetoChart';
import ParticipatoryDrawer from './components/ParticipatoryDrawer';
import './styles.css';

function downloadTextFile(filename, content, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function App() {
  const [citiesMeta, setCitiesMeta] = useState(null);
  const [interventions, setInterventions] = useState({});
  const [city, setCity] = useState('alexandria');
  const [grid, setGrid] = useState(null);

  const [mode, setMode] = useState('paint'); // 'paint' | 'inspect'
  const [activeTool, setActiveTool] = useState('shaded_transit_stop');
  const [budget, setBudget] = useState(1500000);
  const [costScenario, setCostScenario] = useState('mid');
  const [coolingScenario, setCoolingScenario] = useState('mid');
  const [highlightV, setHighlightV] = useState(true);

  const [nebPoints, setNebPoints] = useState({ sustainable: 40, beautiful: 30, together: 30 });
  const [placements, setPlacements] = useState([]);
  const [selectedCell, setSelectedCell] = useState(null);
  const [selectedProps, setSelectedProps] = useState(null);

  const [simulation, setSimulation] = useState(null);
  const [pareto, setPareto] = useState(null);
  const [feedbackData, setFeedbackData] = useState(null);
  const [feedbackVersion, setFeedbackVersion] = useState(0);
  const [deliberation, setDeliberation] = useState(null);
  const [busyDelib, setBusyDelib] = useState(false);

  const [dossier, setDossier] = useState(null);
  const [busyDossier, setBusyDossier] = useState(false);
  const [error, setError] = useState('');

  const totalPts = Math.max(1, nebPoints.sustainable + nebPoints.beautiful + nebPoints.together);
  const nebWeights = {
    sustainable: nebPoints.sustainable / totalPts,
    beautiful: nebPoints.beautiful / totalPts,
    together: nebPoints.together / totalPts,
  };

  useEffect(() => {
    Promise.all([api.getCities(), api.getInterventions()])
      .then(([cData, iData]) => {
        setCitiesMeta(cData);
        setInterventions(iData.interventions);
      })
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    setError('');
    setPlacements([]);
    setSelectedCell(null);
    setSelectedProps(null);
    setDeliberation(null);

    if (citiesMeta?.cities?.[city]) {
      setBudget(citiesMeta.cities[city].default_budget_eur);
    }

    Promise.all([api.getCityGrid(city), api.getFeedback(city)])
      .then(([g, fb]) => {
        setGrid(g);
        setFeedbackData(fb);
      })
      .catch((err) => setError(err.message));
  }, [city, citiesMeta]);

  useEffect(() => {
    if (!grid) return;
    api
      .simulate({
        city,
        budget_eur: budget,
        placements,
        neb_weights: nebWeights,
        cost_scenario: costScenario,
        cooling_scenario: coolingScenario,
      })
      .then(setSimulation)
      .catch((err) => setError(err.message));
  }, [city, grid, budget, placements, nebPoints, costScenario, coolingScenario]);

  useEffect(() => {
    if (!grid) return;
    api
      .optimize({
        city,
        budget_eur: budget,
        neb_weights: nebWeights,
        cost_scenario: costScenario,
        cooling_scenario: coolingScenario,
      })
      .then(setPareto)
      .catch((err) => setError(err.message));
  }, [city, grid, budget, nebPoints, costScenario, coolingScenario, feedbackVersion]);

  const handleCellClick = (props) => {
    setSelectedCell(props.h3_index);
    setSelectedProps(props);

    if (mode !== 'paint') return;
    if (props.baseline_hvi === null) {
      setError(`Cell ${props.h3_index} is NA/unscored (water or q < 0.67); pick a scored land cell.`);
      return;
    }
    setError('');

    setPlacements((prev) => {
      const idx = prev.findIndex(
        (p) => p.h3_index === props.h3_index && p.intervention_id === activeTool
      );
      if (idx >= 0) {
        return prev.filter((_, i) => i !== idx);
      }
      return [...prev, { h3_index: props.h3_index, intervention_id: activeTool, units: 1 }];
    });
  };

  const handleSelectCellId = (h3Id) => {
    setSelectedCell(h3Id);
    const feat = grid?.features?.find((f) => f.properties.h3_index === h3Id);
    if (feat) setSelectedProps(feat.properties);
  };

  const handleSubmitFeedback = async (payload) => {
    await api.postFeedback(payload);
    const updated = await api.getFeedback(city);
    setFeedbackData(updated);
    setFeedbackVersion((v) => v + 1); // Triggers Community NEB Pareto refresh
  };

  const handleRunDeliberation = async () => {
    setBusyDelib(true);
    setError('');
    try {
      const res = await api.runDeliberation(city, true);
      setDeliberation(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyDelib(false);
    }
  };

  const handleApplySuggestedWeights = (w) => {
    setNebPoints({
      sustainable: Math.round(w.sustainable * 100),
      beautiful: Math.round(w.beautiful * 100),
      together: Math.round(w.together * 100),
    });
  };

  const handleExportDossier = async () => {
    setBusyDossier(true);
    setError('');
    try {
      const res = await api.exportDossier({
        scenario_name: `${city === 'alexandria' ? 'Alexandria' : 'Porto'} Participatory Heat Co-Design`,
        simulation_request: {
          city,
          budget_eur: budget,
          placements,
          neb_weights: nebWeights,
          cost_scenario: costScenario,
          cooling_scenario: coolingScenario,
        },
      });
      setDossier(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyDossier(false);
    }
  };

  const currentCityInfo = citiesMeta?.cities?.[city];

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <h1>CanopyCommons</h1>
          <span className="subtitle">Participatory Urban Heat &amp; Green-Corridor Co-Design Studio</span>
        </div>

        <div className="city-switcher">
          <button
            className={city === 'alexandria' ? 'active' : ''}
            onClick={() => setCity('alexandria')}
          >
            Alexandria (Primary Pilot)
          </button>
          <button
            className={city === 'porto' ? 'active' : ''}
            onClick={() => setCity('porto')}
          >
            Porto (EU Transfer Preset)
          </button>
        </div>

        <div className="topbar-controls">
          <label>
            Budget (€):
            <input
              type="number"
              step={100000}
              min={100000}
              max={10000000}
              value={budget}
              onChange={(e) => setBudget(Math.max(100000, Number(e.target.value) || 100000))}
            />
          </label>
          <select value={costScenario} onChange={(e) => setCostScenario(e.target.value)}>
            <option value="low">Cost: Low</option>
            <option value="mid">Cost: Mid</option>
            <option value="high">Cost: High</option>
          </select>
          <select value={coolingScenario} onChange={(e) => setCoolingScenario(e.target.value)}>
            <option value="min">Cooling: Conservative</option>
            <option value="mid">Cooling: Mid</option>
            <option value="max">Cooling: Upper Bound</option>
          </select>
          <button className="export-btn" onClick={handleExportDossier} disabled={busyDossier}>
            {busyDossier ? 'Building...' : 'Export Dossier'}
          </button>
        </div>
      </header>

      {error && <div className="error-bar">{error}</div>}

      <main className="studio-grid">
        {/* Left Control Rail */}
        <aside className="sidebar left">
          <div className="card">
            <div className="card-header">
              <h4>Map Interaction Mode</h4>
              <button className="link-btn" onClick={() => setPlacements([])}>
                Clear ({placements.length})
              </button>
            </div>
            <div className="mode-toggle">
              <button className={mode === 'paint' ? 'active' : ''} onClick={() => setMode('paint')}>
                Paint Intervention
              </button>
              <button className={mode === 'inspect' ? 'active' : ''} onClick={() => setMode('inspect')}>
                Inspect / Tag Cell
              </button>
            </div>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={highlightV}
                onChange={(e) => setHighlightV(e.target.checked)}
              />
              Highlight Fixed Top HVI Quintile (V)
            </label>
          </div>

          <div className="card">
            <h4>Intervention Palette (Footprint Costing)</h4>
            <div className="tool-list">
              {Object.entries(interventions).map(([id, spec]) => (
                <button
                  key={id}
                  className={`tool-btn ${activeTool === id ? 'active' : ''}`}
                  onClick={() => {
                    setActiveTool(id);
                    setMode('paint');
                  }}
                >
                  <div className="tool-title">
                    <strong>{spec.name}</strong>
                    {spec.metrics.pedestrian_mrt_penalty_c > 0 && (
                      <span className="warn-pill">+4°C MRT</span>
                    )}
                  </div>
                  <div className="tool-sub">
                    {spec.default_unit_footprint_m2} m² · €{spec.capex_eur_per_m2.low}–{spec.capex_eur_per_m2.high}/m²
                  </div>
                </button>
              ))}
            </div>
          </div>

          <div className="card">
            <h4>New European Bauhaus Weights</h4>
            {['sustainable', 'beautiful', 'together'].map((pillar) => (
              <div key={pillar} className="slider-row">
                <div className="slider-label">
                  <span>{pillar.charAt(0).toUpperCase() + pillar.slice(1)}</span>
                  <strong>{Math.round(nebWeights[pillar] * 100)}%</strong>
                </div>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={nebPoints[pillar]}
                  onChange={(e) =>
                    setNebPoints((prev) => ({ ...prev, [pillar]: Number(e.target.value) }))
                  }
                />
              </div>
            ))}
          </div>
        </aside>

        {/* Center Map Canvas */}
        <section className="center-pane">
          <HeatMap
            grid={grid}
            center={currentCityInfo?.default_center}
            zoom={currentCityInfo?.default_zoom}
            placements={placements}
            selectedCell={selectedCell}
            highlightQuintileV={highlightV}
            onCellClick={handleCellClick}
          />
        </section>

        {/* Right Analytics & Participatory Rail */}
        <aside className="sidebar right">
          {simulation && (
            <div className="card">
              <div className="card-header">
                <h4>Live Scenario KPIs</h4>
                <span className="badge">{simulation.latency_ms} ms</span>
              </div>

              <div className="kpi-grid">
                <div className="kpi">
                  <span>Spent / Remaining</span>
                  <strong className={simulation.within_budget ? '' : 'text-danger'}>
                    €{Math.round(simulation.total_capex_eur).toLocaleString()}
                  </strong>
                  <small>Rem: €{Math.round(simulation.budget_remaining_eur).toLocaleString()}</small>
                </div>
                <div className="kpi">
                  <span>NEB Score</span>
                  <strong>{simulation.neb_score.toFixed(3)}</strong>
                  <small>
                    S:{simulation.neb_pillars.sustainable.toFixed(2)} B:{simulation.neb_pillars.beautiful.toFixed(2)} T:{simulation.neb_pillars.together.toFixed(2)}
                  </small>
                </div>
                <div className="kpi">
                  <span>Mean Air / PET Relief</span>
                  <strong>{simulation.equity.mean_air_benefit_c.toFixed(3)} °C</strong>
                  <small>PET: {simulation.equity.mean_pet_benefit_c.toFixed(3)} °C</small>
                </div>
                <div className="kpi">
                  <span>Top Quintile V Reached</span>
                  <strong>{(simulation.equity.v_residents_reached_share * 100).toFixed(1)}%</strong>
                  <small>Gini: {simulation.equity.benefit_gini_air ?? 'Undefined'}</small>
                </div>
              </div>

              <div className="disclosure-note">
                <strong>Equity &amp; Data Disclosure:</strong> {simulation.equity.gini_disclosure} Unscored pop share:{' '}
                <strong>{(simulation.unscored_population_share * 100).toFixed(2)}%</strong>.
              </div>

              {simulation.warming_warnings.length > 0 && (
                <div className="mrt-warning">
                  <strong>
                    Signed Pedestrian Warming Alert ({simulation.warming_warnings.length}{' '}
                    {simulation.warming_warnings.length === 1 ? 'cell' : 'cells'}):
                  </strong>{' '}
                  {simulation.warming_warnings[0].note} Affected residents:{' '}
                  {simulation.warming_warnings
                    .reduce((acc, w) => acc + w.affected_population, 0)
                    .toLocaleString()}.
                </div>
              )}
            </div>
          )}

          <ParetoChart
            candidates={pareto?.candidates}
            activeSimulation={simulation}
            rawlsianOrder={pareto?.rawlsian_ranked_order}
            onLoadStrategy={(cand) => setPlacements(cand.placements)}
          />

          {selectedProps && (
            <div className="card">
              <h4>Selected H3 Cell Inspector</h4>
              <div className="mono">{selectedProps.h3_index}</div>
              <div className="inspector-grid">
                <div>HVI: <strong>{selectedProps.baseline_hvi ?? 'NA'}</strong></div>
                <div>LST: <strong>{selectedProps.lst_summer_c ?? 'Masked'} °C</strong></div>
                <div>Pop: <strong>{Number(selectedProps.population_count).toLocaleString()}</strong></div>
                <div>65+ Share: <strong>{(selectedProps.age_65_plus_share * 100).toFixed(1)}%</strong></div>
                <div>10m Refuge: <strong>{(selectedProps.refuge_access_10min_share * 100).toFixed(0)}%</strong></div>
                <div>Transit Stops: <strong>{selectedProps.transit_stops}</strong></div>
              </div>
            </div>
          )}

          <ParticipatoryDrawer
            city={city}
            selectedCell={selectedCell}
            feedbackData={feedbackData}
            deliberation={deliberation}
            busyDelib={busyDelib}
            onSubmitFeedback={handleSubmitFeedback}
            onRunDeliberation={handleRunDeliberation}
            onApplySuggestedWeights={handleApplySuggestedWeights}
            onSelectCellId={handleSelectCellId}
          />

          {simulation?.citations?.length > 0 && (
            <div className="card">
              <h4>Active Peer-Reviewed Citations</h4>
              <ul className="citation-list">
                {simulation.citations.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            </div>
          )}
        </aside>
      </main>

      {/* Dossier Export Modal */}
      {dossier && (
        <div className="modal-backdrop" onClick={() => setDossier(null)}>
          <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
            <div className="card-header">
              <h4>Co-Design Impact Dossier Preview</h4>
              <button className="link-btn" onClick={() => setDossier(null)}>
                Close ✕
              </button>
            </div>
            <pre className="dossier-pre">{dossier.markdown_report}</pre>
            <div className="modal-actions">
              <button
                className="primary-btn"
                onClick={() =>
                  downloadTextFile(
                    `canopycommons_${city}_dossier.md`,
                    dossier.markdown_report,
                    'text/markdown'
                  )
                }
              >
                Download Markdown (.md)
              </button>
              <button
                className="secondary-btn"
                onClick={() =>
                  downloadTextFile(
                    `canopycommons_${city}_dossier.json`,
                    JSON.stringify(dossier.json_payload, null, 2),
                    'application/json'
                  )
                }
              >
                Download Full Audit (.json)
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}