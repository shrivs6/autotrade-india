import { useEffect, useState } from "react";
import { api } from "../services/api";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ReferenceLine, ResponsiveContainer,
} from "recharts";
import DailyTradeLog from "./DailyTradeLog";

const PERIODS = [
  { label: "7D", days: 7 },
  { label: "30D", days: 30 },
  { label: "All", days: 0 },
];

function formatDate(dateStr) {
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-IN", { month: "short", day: "numeric" });
}

function PnlTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <div className="tooltip-date">{formatDate(label)}</div>
      <div>Day PnL: <strong style={{ color: d.pnl >= 0 ? "#22c55e" : "#ef4444" }}>
        {d.pnl >= 0 ? "+" : ""}₹{d.pnl?.toLocaleString("en-IN")}
      </strong></div>
      <div>Cumulative: <strong>₹{d.cumulative_pnl?.toLocaleString("en-IN")}</strong></div>
      <div>Win Rate: {(d.win_rate * 100).toFixed(1)}% ({d.wins}/{d.trades})</div>
    </div>
  );
}

export default function HistoryTab() {
  const [period, setPeriod] = useState(30);
  const [daily, setDaily] = useState([]);
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.dailySummary(period),
      api.recentTrades(period === 0 ? 3650 : period),
    ]).then(([d, t]) => {
      setDaily(d);
      setTrades(t);
    }).finally(() => setLoading(false));
  }, [period]);

  // Normalise recentTrades response to match DailyTradeLog expectations
  const normalisedTrades = trades.map((t) => ({
    ...t,
    entry_time: t.entry_time ? new Date(t.entry_time).toLocaleString("en-IN", {
      timeZone: "Asia/Kolkata", month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit",
    }) : null,
    exit_time: t.exit_time ? new Date(t.exit_time).toLocaleString("en-IN", {
      timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit",
    }) : null,
    result: t.pnl >= 0 ? "WIN" : "LOSS",
    duration_min: t.entry_time && t.exit_time
      ? Math.round((new Date(t.exit_time) - new Date(t.entry_time)) / 60000)
      : 0,
    quantity: t.quantity ?? null,
    exposure: t.entry_price && t.quantity
      ? Math.round(t.entry_price * t.quantity)
      : null,
  }));

  const cumulativeColor = daily.length > 0 && daily[daily.length - 1].cumulative_pnl >= 0
    ? "#22c55e" : "#ef4444";

  return (
    <div>
      {/* Period selector */}
      <div className="period-bar">
        {PERIODS.map((p) => (
          <button
            key={p.days}
            className={`period-btn ${period === p.days ? "period-active" : ""}`}
            onClick={() => setPeriod(p.days)}
          >
            {p.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="loading">Loading...</div>
      ) : (
        <>
          {/* Cumulative PnL chart */}
          <div className="chart-container" style={{ marginBottom: 20 }}>
            <h2 className="section-title">Cumulative PnL</h2>
            {daily.length === 0 ? (
              <div className="empty-state">No data for this period.</div>
            ) : (
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={daily} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#2e303a" />
                  <XAxis dataKey="date" tickFormatter={formatDate}
                    tick={{ fontSize: 11, fill: "#9ca3af" }} interval="preserveStartEnd" />
                  <YAxis tickFormatter={(v) => `₹${(v/1000).toFixed(0)}k`}
                    tick={{ fontSize: 11, fill: "#9ca3af" }} width={48} />
                  <Tooltip content={<PnlTooltip />} />
                  <ReferenceLine y={0} stroke="#64748b" strokeDasharray="3 3" />
                  <Line type="monotone" dataKey="cumulative_pnl" stroke={cumulativeColor}
                    strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* Daily breakdown */}
          <div className="section" style={{ marginBottom: 20 }}>
            <h2 className="section-title">Day by Day</h2>
            {daily.length === 0 ? (
              <div className="empty-state">No trading days in this period.</div>
            ) : (
              <>
                {/* Desktop table */}
                <div className="table-wrapper">
                  <table className="trade-table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Trades</th>
                        <th>Wins</th>
                        <th>Win Rate</th>
                        <th>Day PnL</th>
                        <th>Cumulative PnL</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...daily].reverse().map((d) => (
                        <tr key={d.date}>
                          <td>{formatDate(d.date)}</td>
                          <td>{d.trades}</td>
                          <td>{d.wins}</td>
                          <td>{(d.win_rate * 100).toFixed(1)}%</td>
                          <td className={d.pnl >= 0 ? "pnl-win" : "pnl-loss"}>
                            {d.pnl >= 0 ? "+" : ""}₹{d.pnl?.toLocaleString("en-IN")}
                          </td>
                          <td className={d.cumulative_pnl >= 0 ? "pnl-win" : "pnl-loss"}>
                            ₹{d.cumulative_pnl?.toLocaleString("en-IN")}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Mobile cards */}
                <div className="trade-cards">
                  {[...daily].reverse().map((d) => (
                    <div key={d.date} className="trade-card">
                      <div className="trade-card-header">
                        <span style={{ fontWeight: 700, color: "#c7d2fe" }}>{formatDate(d.date)}</span>
                        <span className={`trade-card-pnl ${d.pnl >= 0 ? "pnl-win" : "pnl-loss"}`}>
                          {d.pnl >= 0 ? "+" : ""}₹{d.pnl?.toLocaleString("en-IN")}
                        </span>
                      </div>
                      <div className="trade-card-row">
                        <span>Trades / Wins</span>
                        <span>{d.trades} trades · {d.wins} wins</span>
                      </div>
                      <div className="trade-card-row">
                        <span>Win Rate</span>
                        <span>{(d.win_rate * 100).toFixed(1)}%</span>
                      </div>
                      <div className="trade-card-row">
                        <span>Cumulative PnL</span>
                        <span className={d.cumulative_pnl >= 0 ? "pnl-win" : "pnl-loss"}>
                          ₹{d.cumulative_pnl?.toLocaleString("en-IN")}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>

          {/* Full trade list */}
          <DailyTradeLog trades={normalisedTrades} />
        </>
      )}
    </div>
  );
}
