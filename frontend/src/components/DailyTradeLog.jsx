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
      <div className="table-wrapper">
        <table className="trade-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Direction</th>
              <th>Entry</th>
              <th>Exit</th>
              <th>Entry ₹</th>
              <th>Exit ₹</th>
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
                  <td>{t.entry_time}</td>
                  <td>{t.exit_time}</td>
                  <td>₹{t.entry_price?.toFixed(2)}</td>
                  <td>₹{t.exit_price?.toFixed(2)}</td>
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
    </div>
  );
}
