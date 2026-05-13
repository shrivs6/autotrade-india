function relativeTime(isoStr) {
  if (!isoStr) return null;
  const diff = Math.floor((Date.now() - new Date(isoStr)) / 1000);
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} hr ago`;
  return null;
}

export default function PerformanceStats({ summary, stats }) {
  const statusColor = summary?.status === "TRADING" ? "#22c55e" : "#f59e0b";
  const lastScanLabel = relativeTime(summary?.last_scan_time);

  function fmt(val, prefix = "") {
    if (val == null) return "—";
    return `${prefix}${val}`;
  }

  function fmtPnl(val) {
    if (val == null) return "—";
    const color = val >= 0 ? "#22c55e" : "#ef4444";
    const sign = val >= 0 ? "+" : "";
    return <span style={{ color }}>{sign}₹{val.toLocaleString("en-IN")}</span>;
  }

  function fmtPct(val) {
    if (val == null) return "—";
    return `${(val * 100).toFixed(1)}%`;
  }

  return (
    <>
    <div className="stats-bar">
      <div className="stat-card">
        <div className="stat-label">Today's PnL</div>
        <div className="stat-value">{fmtPnl(summary?.today_pnl)}</div>
        <div className="stat-sub">{summary?.today_trades ?? 0} trades</div>
      </div>

      <div className="stat-card">
        <div className="stat-label">Today Win Rate</div>
        <div className="stat-value">{fmtPct(summary?.today_win_rate)}</div>
        <div className="stat-sub">All-time: {fmtPct(summary?.all_time_win_rate)}</div>
      </div>

      <div className="stat-card">
        <div className="stat-label">Total PnL</div>
        <div className="stat-value">{fmtPnl(stats?.total_pnl)}</div>
        <div className="stat-sub">{stats?.total_trades ?? 0} total trades</div>
      </div>

      <div className="stat-card">
        <div className="stat-label">Profit Factor</div>
        <div className="stat-value">{fmt(stats?.profit_factor)}</div>
        <div className="stat-sub">Avg win: ₹{stats?.avg_win ?? "—"}</div>
      </div>

      <div className="stat-card">
        <div className="stat-label">Open Positions</div>
        <div className="stat-value">{summary?.open_positions ?? 0}</div>
        <div className="stat-sub">Model: {summary?.model_version ?? "none"}</div>
      </div>

      <div className="stat-card">
        <div className="stat-label">System Status</div>
        <div className="stat-value" style={{ color: statusColor, fontSize: "1rem" }}>
          {summary?.status ?? "—"}
        </div>
        <div className="stat-sub">{summary?.date ?? ""}</div>
      </div>
    </div>

    <div className="scanner-status">
      <span className="scanner-badge">Paper Trading</span>
      <span className="scanner-dot">·</span>
      {lastScanLabel
        ? <span>Scanner last ran: <strong>{lastScanLabel}</strong></span>
        : <span className="scanner-inactive">Scanner not yet active today</span>
      }
      <span className="scanner-dot">·</span>
      <span>Signals today: <strong>{summary?.signals_today ?? 0}</strong></span>
    </div>
    </>
  );
}
