export default function TabBar({ active, onChange }) {
  const tabs = [
    { key: "today", label: "Today" },
    { key: "history", label: "History" },
  ];

  return (
    <div className="tab-bar">
      {tabs.map((t) => (
        <button
          key={t.key}
          className={`tab-btn ${active === t.key ? "tab-active" : ""}`}
          onClick={() => onChange(t.key)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
