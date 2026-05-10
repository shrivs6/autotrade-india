export default function LearningSummary({ lessons }) {
  if (!lessons || lessons.length === 0) {
    return (
      <div className="section">
        <h2 className="section-title">Today's Lessons</h2>
        <div className="empty-state">No lessons generated yet.</div>
      </div>
    );
  }

  return (
    <div className="section">
      <h2 className="section-title">Today's Lessons</h2>
      <ul className="lessons-list">
        {lessons.map((l, i) => (
          <li key={i} className="lesson-item">
            <div className="lesson-text">{l.lesson}</div>
            {l.conditions && (
              <div className="lesson-conditions">
                Conditions: {
                  typeof l.conditions === "object"
                    ? Object.entries(l.conditions)
                        .map(([k, v]) => `${k}: ${v}`)
                        .join(", ")
                    : l.conditions
                }
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
