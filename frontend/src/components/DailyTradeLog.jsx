export default function DailyTradeLog({ trades }) {
  if (!trades || trades.length === 0) {
    return (
      <div className="section">
        <h2 className="section-title">Today's Trades</h2>
        <div className="empty-state">No trades today.</div>
      </div>
    );
  }

  return (
    <div className="section">
      <h2 className="section-title">Today's Trades</h2>

      {/* Desktop table */}
      <div className="table-wrapper">
        <table className="trade-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Direction</th>
              <th>Qty</th>
              <th>Entry</th>
              <th>Exit</th>
              <th>Entry ₹</th>
              <th>Exit ₹</th>
              <th>Exposure</th>
              <th>Duration</th>
              <th>Result</th>
              <th>PnL</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t) => {
              const isWin = t.result === "WIN";
              return (
                <tr key={t.id}>
                  <td className="symbol">{t.symbol}</td>
                  <td>
                    <span className={`badge ${t.direction}`}>
                      {t.direction?.toUpperCase()}
                    </span>
                  </td>
                  <td>{t.quantity ?? "—"}</td>
                  <td>{t.entry_time}</td>
                  <td>{t.exit_time}</td>
                  <td>₹{t.entry_price?.toFixed(2)}</td>
                  <td>₹{t.exit_price?.toFixed(2)}</td>
                  <td>₹{t.exposure?.toLocaleString("en-IN")}</td>
                  <td>{t.duration_min}m</td>
                  <td>
                    <span className={`badge result ${isWin ? "win" : "loss"}`}>
                      {t.result}
                    </span>
                  </td>
                  <td className={isWin ? "pnl-win" : "pnl-loss"}>
                    {t.pnl >= 0 ? "+" : ""}₹{t.pnl?.toLocaleString("en-IN")}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Mobile cards */}
      <div className="trade-cards">
        {trades.map((t) => {
          const isWin = t.result === "WIN";
          return (
            <div key={t.id} className="trade-card">
              <div className="trade-card-header">
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span className="trade-card-symbol">{t.symbol}</span>
                  <span className={`badge ${t.direction}`}>{t.direction?.toUpperCase()}</span>
                </div>
                <span className={`trade-card-pnl ${isWin ? "pnl-win" : "pnl-loss"}`}>
                  {t.pnl >= 0 ? "+" : ""}₹{t.pnl?.toLocaleString("en-IN")}
                </span>
              </div>
              <div className="trade-card-row">
                <span>Time</span>
                <span>{t.entry_time} → {t.exit_time} ({t.duration_min}m)</span>
              </div>
              <div className="trade-card-row">
                <span>Price</span>
                <span>₹{t.entry_price?.toFixed(2)} → ₹{t.exit_price?.toFixed(2)}</span>
              </div>
              <div className="trade-card-row">
                <span>Qty / Exposure</span>
                <span>{t.quantity ?? "—"} shares · ₹{t.exposure?.toLocaleString("en-IN")}</span>
              </div>
              <div className="trade-card-row">
                <span>Result</span>
                <span className={`badge result ${isWin ? "win" : "loss"}`}>{t.result}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
