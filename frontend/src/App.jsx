import { useEffect, useState } from "react";
import { api } from "./services/api";
import PerformanceStats from "./components/PerformanceStats";
import WinRateChart from "./components/WinRateChart";
import DailyTradeLog from "./components/DailyTradeLog";
import LearningSummary from "./components/LearningSummary";
import TabBar from "./components/TabBar";
import HistoryTab from "./components/HistoryTab";
import OpenPositions from "./components/OpenPositions";
import "./App.css";

export default function App() {
  const [activeTab, setActiveTab] = useState("today");
  const [summary, setSummary] = useState(null);
  const [stats, setStats] = useState(null);
  const [winRateHistory, setWinRateHistory] = useState([]);
  const [trades, setTrades] = useState([]);
  const [lessons, setLessons] = useState([]);
  const [openPositions, setOpenPositions] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  async function loadAll() {
    try {
      const [sum, st, wrh, tod, les, open] = await Promise.all([
        api.summary(),
        api.stats(),
        api.winRateHistory(90),
        api.todaysTrades(),
        api.lessons(),
        api.openPositions(),
      ]);
      setSummary(sum);
      setStats(st);
      setWinRateHistory(wrh);
      setTrades(tod);
      setLessons(les);
      setOpenPositions(open);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
    const interval = setInterval(loadAll, 60_000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="app">
      <header className="app-header">
        <h1 className="app-title">AutoTrade India</h1>
        <button className="refresh-btn" onClick={loadAll}>Refresh</button>
      </header>

      {error && <div className="error-banner">API error: {error}</div>}

      <TabBar active={activeTab} onChange={setActiveTab} />

      {activeTab === "today" && (
        loading ? (
          <div className="loading">Loading...</div>
        ) : (
          <>
            <PerformanceStats summary={summary} stats={stats} />
            <WinRateChart data={winRateHistory} />
            <OpenPositions positions={openPositions} />
            <div className="bottom-grid">
              <DailyTradeLog trades={trades} />
              <LearningSummary lessons={lessons} />
            </div>
          </>
        )
      )}

      {activeTab === "history" && <HistoryTab />}
    </div>
  );
}
