export default function OpenPositions({ positions }) {
  if (!positions || positions.length === 0) return null;

  return (
    <div className="section open-positions-section">
      <h2 className="section-title">
        Open Positions
        <span className="open-count">{positions.length}</span>
      </h2>

      {/* Desktop table */}
      <div className="table-wrapper">
        <table className="trade-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Direction</th>
              <th>Entry</th>
              <th>Target</th>
              <th>Stop Loss</th>
              <th>Qty</th>
              <th>Exposure</th>
              <th>Confidence</th>
              <th>Since</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => (
              <tr key={p.id}>
                <td className="symbol">{p.symbol}</td>
                <td>
                  <span className={`badge ${p.direction}`}>
                    {p.direction?.toUpperCase()}
                  </span>
                </td>
                <td>₹{p.entry_price?.toFixed(2)}</td>
                <td className="pnl-win">₹{p.target?.toFixed(2)}</td>
                <td className="pnl-loss">₹{p.stop_loss?.toFixed(2)}</td>
                <td>{p.quantity ?? "—"}</td>
                <td>₹{p.exposure?.toLocaleString("en-IN")}</td>
                <td>{p.confidence != null ? `${p.confidence}%` : "—"}</td>
                <td>{p.entry_time}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile cards */}
      <div className="trade-cards">
        {positions.map((p) => (
          <div key={p.id} className="trade-card open-card">
            <div className="trade-card-header">
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span className="trade-card-symbol">{p.symbol}</span>
                <span className={`badge ${p.direction}`}>{p.direction?.toUpperCase()}</span>
              </div>
              <span className="open-badge">OPEN</span>
            </div>
            <div className="trade-card-row">
              <span>Entry</span>
              <span>₹{p.entry_price?.toFixed(2)} @ {p.entry_time}</span>
            </div>
            <div className="trade-card-row">
              <span>Target</span>
              <span className="pnl-win">₹{p.target?.toFixed(2)}</span>
            </div>
            <div className="trade-card-row">
              <span>Stop Loss</span>
              <span className="pnl-loss">₹{p.stop_loss?.toFixed(2)}</span>
            </div>
            <div className="trade-card-row">
              <span>Qty / Exposure</span>
              <span>{p.quantity ?? "—"} shares · ₹{p.exposure?.toLocaleString("en-IN")}</span>
            </div>
            {p.confidence != null && (
              <div className="trade-card-row">
                <span>Model confidence</span>
                <span>{p.confidence}%</span>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
