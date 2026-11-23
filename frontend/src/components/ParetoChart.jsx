const COLORS = {
  pure_efficiency: '#64748b',
  community_neb: '#2563eb',
  rawlsian_equity: '#059669',
  current_manual: '#d97706',
};

export default function ParetoChart({ candidates, activeSimulation, rawlsianOrder, onLoadStrategy }) {
  if (!candidates || candidates.length === 0) return null;

  const width = 320;
  const height = 200;
  const pad = { top: 18, right: 18, bottom: 42, left: 42 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const points = candidates.map((c) => ({
    id: c.strategy_id,
    label: c.label,
    x: c.simulation.equity.v_residents_reached_share * 100, // 0..100%
    y: c.simulation.neb_score, // 0..1
    gini: c.simulation.equity.benefit_gini_air,
    candidate: c,
  }));

  if (activeSimulation && activeSimulation.cell_results.length > 0) {
    points.push({
      id: 'current_manual',
      label: 'Current Workspace',
      x: activeSimulation.equity.v_residents_reached_share * 100,
      y: activeSimulation.neb_score,
      gini: activeSimulation.equity.benefit_gini_air,
      candidate: null,
    });
  }

  const maxX = Math.max(60, ...points.map((p) => p.x + 10));
  const maxY = Math.min(1.0, Math.max(0.65, ...points.map((p) => p.y + 0.1)));

  const sx = (v) => pad.left + (v / maxX) * plotW;
  const sy = (v) => pad.top + plotH - (v / maxY) * plotH;

  return (
    <div className="card">
      <div className="card-header">
        <h4>Pareto Equity vs. NEB Trade-Off</h4>
        <span className="badge">Click strategy to load</span>
      </div>

      <svg viewBox={`0 0 ${width} ${height}`} className="pareto-svg">
        {/* Axes */}
        <line x1={pad.left} y1={pad.top} x2={pad.left} y2={pad.top + plotH} stroke="#cbd5e1" />
        <line x1={pad.left} y1={pad.top + plotH} x2={pad.left + plotW} y2={pad.top + plotH} stroke="#cbd5e1" />

        {/* Labels */}
        <text x={pad.left + plotW / 2} y={height - 6} textAnchor="middle" fontSize="10" fill="#475569">
          Top HVI Quintile (V) Residents Reached (%)
        </text>
        <text
          x={12}
          y={pad.top + plotH / 2}
          textAnchor="middle"
          fontSize="10"
          fill="#475569"
          transform={`rotate(-90 12 ${pad.top + plotH / 2})`}
        >
          NEB Score (0–1)
        </text>

        {/* Grid ticks */}
        {[0, 25, 50, 75].filter((t) => t <= maxX).map((t) => (
          <g key={t}>
            <line x1={sx(t)} y1={pad.top} x2={sx(t)} y2={pad.top + plotH} stroke="#f1f5f9" />
            <text x={sx(t)} y={pad.top + plotH + 12} textAnchor="middle" fontSize="9" fill="#64748b">
              {t}%
            </text>
          </g>
        ))}

        {/* Strategy dots */}
        {points.map((pt) => (
          <g
            key={pt.id}
            style={{ cursor: pt.candidate ? 'pointer' : 'default' }}
            onClick={() => pt.candidate && onLoadStrategy(pt.candidate)}
          >
            <circle
              cx={sx(pt.x)}
              cy={sy(pt.y)}
              r={pt.id === 'current_manual' ? 6.5 : 5.5}
              fill={COLORS[pt.id] || '#334155'}
              stroke="#ffffff"
              strokeWidth="1.5"
            />
            <title>{`${pt.label}: V-Reach ${pt.x.toFixed(1)}%, NEB ${pt.y.toFixed(3)}, Gini ${pt.gini ?? 'N/A'}`}</title>
          </g>
        ))}
      </svg>

      <div className="strategy-list">
        {candidates.map((c) => {
          const rank = rawlsianOrder ? rawlsianOrder.indexOf(c.strategy_id) + 1 : null;
          return (
            <button
              key={c.strategy_id}
              className="strategy-btn"
              onClick={() => onLoadStrategy(c)}
            >
              <span className="dot" style={{ background: COLORS[c.strategy_id] }} />
              <div className="strategy-meta">
                <strong>{c.label}</strong>
                <span>
                  NEB {c.simulation.neb_score.toFixed(3)} · V-Reach{' '}
                  {(c.simulation.equity.v_residents_reached_share * 100).toFixed(1)}%
                  {rank === 1 ? ' · #1 Rawlsian' : ''}
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}