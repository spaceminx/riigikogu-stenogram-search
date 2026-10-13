import React from "react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export function ActivityChart({
  activity = [],
  interval = "monthly",
  onIntervalChange,
  loading = false,
  error = null,
  theme = "light",
  title = "Kõnede ajajoon",
  kicker = "TEEMA LÄBI AJA",
  emptyMessage = "Sellele otsingule kõnesid ei leitud.",
}) {
  const tooltipStyle = {
    contentStyle: {
      backgroundColor: theme === "dark" ? "#1e293b" : "#ffffff",
      color: theme === "dark" ? "#f1f5f9" : "#25364a",
      border: `1px solid ${theme === "dark" ? "#334155" : "#cbd3dc"}`,
      borderRadius: "4px",
      boxShadow: "0 2px 8px rgba(0, 0, 0, 0.2)",
    },
    itemStyle: { color: theme === "dark" ? "#60a5fa" : "#315b84", fontWeight: 600 },
    labelStyle: { color: theme === "dark" ? "#94a3b8" : "#536477", marginBottom: "4px" },
  };

  const axisStroke = theme === "dark" ? "#334155" : "#cbd3dc";
  const axisTickColor = theme === "dark" ? "#94a3b8" : "#64748b";

  return (
    <section className="glass-panel timeline-panel" aria-labelledby="timeline-title">
      <div className="chart-header">
        <div>
          <span className="section-kicker">{kicker}</span>
          <h2 id="timeline-title">{title}</h2>
        </div>
        <div className="timeline-header-controls">
          {activity.length > 0 && <span className="chart-period">{activity.length} perioodi</span>}
          {onIntervalChange && (
            <div className="interval-segmented" role="group" aria-label="Ajajoone ajavahemik">
              {[
                ["daily", "Päev"],
                ["weekly", "Nädal"],
                ["monthly", "Kuu"],
              ].map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  className={`interval-segment${interval === value ? " is-active" : ""}`}
                  aria-pressed={interval === value}
                  onClick={() => onIntervalChange(value)}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
      {error ? (
        <div className="chart-empty-state chart-error-state" role="alert">
          <span>
            {typeof error === "string" ? error : error?.message || "Viga andmete laadimisel."}
          </span>
        </div>
      ) : loading ? (
        <div className="chart-empty-state" role="status">
          <span>Laen arutelude andmeid…</span>
        </div>
      ) : activity.length > 0 ? (
        <div className="timeline-chart">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={activity} margin={{ top: 12, right: 8, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="colorCount" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#315b84" stopOpacity={0.16} />
                  <stop offset="95%" stopColor="#315b84" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey={interval === "daily" ? "date" : interval === "weekly" ? "week" : "month"}
                stroke={axisStroke}
                tick={{ fill: axisTickColor, fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                minTickGap={24}
              />
              <YAxis
                stroke={axisStroke}
                tick={{ fill: axisTickColor, fontSize: 11 }}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip {...tooltipStyle} cursor={{ stroke: "#9eabb9", strokeWidth: 1 }} />
              <Area
                type="monotone"
                dataKey="count"
                name="Kõnesid"
                stroke="#315b84"
                strokeWidth={2}
                fillOpacity={1}
                fill="url(#colorCount)"
                activeDot={{ r: 4, fill: "#315b84", stroke: "#ffffff", strokeWidth: 2 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="chart-empty-state">
          <span>{emptyMessage}</span>
        </div>
      )}
      {activity.length > 0 && (
        <div className="chart-footer">
          <span className="legend-dot" /> Kõnede arv valitud perioodis
        </div>
      )}
    </section>
  );
}

export default ActivityChart;
