import { useState } from 'react';

const PRESET_TAGS = [
  'Unshaded Transit Hub',
  'Elderly Clinic Route',
  'School Walk Corridor',
  'Informal Microbus Queue',
  'Preserve Street Access',
];

const DEFAULT_STRATA = {
  alexandria: ['Karmouz Residents', 'Daily Tram Commuters', 'El Manshia Shopkeepers', 'Senior Clinic Visitors'],
  porto: ['Campanhã Residents', 'STCP Bus Riders', 'Historic Core Seniors', 'Local NGO Delegates'],
};

export default function ParticipatoryDrawer({
  city,
  selectedCell,
  feedbackData,
  deliberation,
  busyDelib,
  onSubmitFeedback,
  onRunDeliberation,
  onApplySuggestedWeights,
  onSelectCellId,
}) {
  const [stratum, setStratum] = useState(DEFAULT_STRATA[city]?.[0] || 'Local Residents');
  const [personaRole, setPersonaRole] = useState('resident');
  const [priorityTag, setPriorityTag] = useState(PRESET_TAGS[0]);
  const [rationale, setRationale] = useState('');
  const [ptsS, setPtsS] = useState(40);
  const [ptsB, setPtsB] = useState(20);
  const [ptsT, setPtsT] = useState(40);
  const [submitting, setSubmitting] = useState(false);
  const [formMsg, setFormMsg] = useState('');

  const sumPts = Number(ptsS) + Number(ptsB) + Number(ptsT);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!selectedCell) {
      setFormMsg('Click any land hexagon on the map first to attach your lived-experience tag.');
      return;
    }
    if (sumPts !== 100) {
      setFormMsg(`NEB points must total exactly 100 (currently ${sumPts}).`);
      return;
    }
    if (rationale.trim().length < 5) {
      setFormMsg('Enter a brief rationale (at least 5 characters).');
      return;
    }

    setSubmitting(true);
    setFormMsg('');
    try {
      await onSubmitFeedback({
        city,
        h3_index: selectedCell,
        stratum: stratum.trim() || 'Local Residents',
        persona_role: personaRole,
        priority_tag: priorityTag,
        rationale_text: rationale.trim(),
        points_sustainable: Number(ptsS),
        points_beautiful: Number(ptsB),
        points_together: Number(ptsT),
      });
      setRationale('');
      setFormMsg('Submitted! Community NEB strategy updated.');
    } catch (err) {
      setFormMsg(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="card">
      <div className="card-header">
        <h4>Participatory Feedback &amp; AI Deliberation</h4>
        <span className="badge">{feedbackData?.count || 0} logged</span>
      </div>

      <form className="fb-form" onSubmit={handleSubmit}>
        <div className="fb-cell-pill">
          Target H3 Cell:{' '}
          <strong>{selectedCell ? selectedCell : 'Click a hex cell on map'}</strong>
        </div>

        <div className="fb-row-2">
          <label>
            Stratum / Group
            <input
              list={`strata-${city}`}
              value={stratum}
              onChange={(e) => setStratum(e.target.value)}
            />
            <datalist id={`strata-${city}`}>
              {(DEFAULT_STRATA[city] || []).map((s) => (
                <option key={s} value={s} />
              ))}
            </datalist>
          </label>
          <label>
            Role
            <select value={personaRole} onChange={(e) => setPersonaRole(e.target.value)}>
              <option value="resident">Resident</option>
              <option value="transit_rider">Transit Rider</option>
              <option value="ngo">Local NGO</option>
              <option value="planner">Urban Planner</option>
            </select>
          </label>
        </div>

        <label>
          Lived-Experience Priority Tag
          <select value={priorityTag} onChange={(e) => setPriorityTag(e.target.value)}>
            {PRESET_TAGS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>

        <label>
          Field Observation / Objection
          <textarea
            rows={2}
            placeholder="e.g., Unshaded afternoon microbus queue with elderly riders..."
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
          />
        </label>

        <div className="neb-vote-box">
          <div className="neb-vote-head">
            <span>Distribute 100 NEB Points</span>
            <strong className={sumPts === 100 ? 'ok-txt' : 'err-txt'}>
              Sum: {sumPts}/100
            </strong>
          </div>
          <div className="fb-row-3">
            <label>
              Sust.
              <input
                type="number"
                min={0}
                max={100}
                value={ptsS}
                onChange={(e) => setPtsS(Number(e.target.value) || 0)}
              />
            </label>
            <label>
              Beaut.
              <input
                type="number"
                min={0}
                max={100}
                value={ptsB}
                onChange={(e) => setPtsB(Number(e.target.value) || 0)}
              />
            </label>
            <label>
              Togeth.
              <input
                type="number"
                min={0}
                max={100}
                value={ptsT}
                onChange={(e) => setPtsT(Number(e.target.value) || 0)}
              />
            </label>
          </div>
        </div>

        {formMsg && <div className="form-msg">{formMsg}</div>}

        <button type="submit" className="primary-btn" disabled={submitting}>
          {submitting ? 'Saving...' : 'Submit Citizen Tag & Vote'}
        </button>
      </form>

      {/* Traceable AI Deliberation Block */}
      <div className="delib-section">
        <button
          className="secondary-btn"
          disabled={busyDelib || !feedbackData?.count}
          onClick={onRunDeliberation}
        >
          {busyDelib ? 'Synthesizing Trade-Offs...' : 'Synthesize Stakeholder Trade-Offs (AI)'}
        </button>

        {deliberation && (
          <div className="delib-results">
            <div className="delib-meta">
              Provider: <span className="mono">{deliberation.provider}</span> · Advisory only (no silent weight changes)
            </div>

            {deliberation.themes.map((th, i) => (
              <div key={i} className="theme-box">
                <strong>{th.theme_title}</strong>
                <p>{th.summary}</p>
                <div className="cite-chips">
                  {th.cited_feedback_ids.map((fid) => (
                    <span key={fid} className="cite-chip">
                      #{fid}
                    </span>
                  ))}
                  {th.cited_h3_indices.map((cid) => (
                    <button
                      key={cid}
                      type="button"
                      className="cite-chip cell-link"
                      onClick={() => onSelectCellId(cid)}
                      title="Highlight H3 cell on map"
                    >
                      {cid.slice(0, 10)}…
                    </button>
                  ))}
                </div>
              </div>
            ))}

            {deliberation.stratified_citizen_weights && (
              <button
                type="button"
                className="apply-weights-btn"
                onClick={() => onApplySuggestedWeights(deliberation.stratified_citizen_weights)}
              >
                Apply Citizen-Stratified Weights (S:{Math.round(deliberation.stratified_citizen_weights.sustainable * 100)}% · B:{Math.round(deliberation.stratified_citizen_weights.beautiful * 100)}% · T:{Math.round(deliberation.stratified_citizen_weights.together * 100)}%)
              </button>
            )}
          </div>
        )}
      </div>

      {/* Recent Feedback Log */}
      {feedbackData?.records?.length > 0 && (
        <div className="fb-log">
          <h5>Recent Field Tags ({feedbackData.records.length})</h5>
          {feedbackData.records.slice(0, 5).map((r) => (
            <div key={r.feedback_id} className="fb-item">
              <div className="fb-item-head">
                <strong>#{r.feedback_id} · {r.priority_tag}</strong>
                <button
                  type="button"
                  className="link-btn"
                  onClick={() => onSelectCellId(r.h3_index)}
                >
                  {r.h3_index.slice(0, 9)}…
                </button>
              </div>
              <div className="fb-item-sub">{r.stratum} ({r.persona_role})</div>
              <p>{r.rationale_text}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}