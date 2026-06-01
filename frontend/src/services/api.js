const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function get(path) {
  const res = await fetch(`${BASE_URL}${path}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export const api = {
  summary: () => get("/api/dashboard/summary"),
  winRateHistory: (days = 90) => get(`/api/dashboard/win-rate-history?days=${days}`),
  todaysTrades: () => get("/api/dashboard/todays-trades"),
  lessons: () => get("/api/dashboard/lessons"),
  stats: () => get("/api/performance/stats"),
  openPositions: () => get("/api/trades/open"),
  dailySummary: (days = 30) => get(`/api/history/daily?days=${days}`),
  recentTrades: (days = 7) => get(`/api/trades/recent?days=${days}`),
  health: () => get("/health"),
};
