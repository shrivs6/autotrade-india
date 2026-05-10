import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";

function formatDate(dateStr) {
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-IN", { month: "short", day: "numeric" });
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <div className="tooltip-date">{formatDate(label)}</div>
      <div>Win Rate: <strong>{(d.win_rate * 100).toFixed(1)}%</strong></div>
      <div>Trades: {d.total_trades}</div>
      <div>PnL: ₹{d.total_pnl?.toLocaleString("en-IN")}</div>
    </div>
  );
}

export default function WinRateChart({ data }) {
  if (!data || data.length === 0) {
    return (
      <div className="chart-empty">No win rate history yet. Start trading to see data.</div>
    );
  }

  const chartData = data.map((d) => ({
    ...d,
    win_rate_pct: parseFloat((d.win_rate * 100).toFixed(1)),
  }));

  return (
    <div className="chart-container">
      <h2 className="section-title">Win Rate Trend (90 days)</h2>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2e303a" />
          <XAxis
            dataKey="date"
            tickFormatter={formatDate}
            tick={{ fontSize: 11, fill: "#9ca3af" }}
            interval="preserveStartEnd"
          />
          <YAxis
            domain={[0, 100]}
            tickFormatter={(v) => `${v}%`}
            tick={{ fontSize: 11, fill: "#9ca3af" }}
            width={40}
          />
          <Tooltip content={<CustomTooltip />} />
          <ReferenceLine y={60} stroke="#22c55e" strokeDasharray="5 5" label={{ value: "60% target", fill: "#22c55e", fontSize: 11 }} />
          <Line
            type="monotone"
            dataKey="win_rate_pct"
            stroke="#818cf8"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
