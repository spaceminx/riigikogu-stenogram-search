import React from "react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export function ActivityChart({
  activity = [],
  interval = "monthly",
  onIntervalChange,
  loading = false,
  theme = "light",
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

  return (
    <section className="glass-panel timeline-panel" aria-labelledby="timeline-title">
      <div className="chart-header">
        <div>
          <span className="section-kicker">TEEMA LÄBI AJA</span>
          <h2 id="timeline-title">Kõnede ajajoon</h2>
        </div>
        <div className="timeline-header-controls">
          {activity.length > 0 && <span className="chart-period">{activity.length} perioodi</span>}
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
        </div>
      </div>
      {activity.length > 0 ? (
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
                stroke="#cbd3dc"
                tick={{ fill: "#64748b", fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                minTickGap={24}
              />
              <YAxis
                stroke="#cbd3dc"
                tick={{ fill: "#64748b", fontSize: 11 }}
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
      ) : loading ? (
        <div className="chart-empty-state" role="status">
          Laen arutelude andmeid…
        </div>
      ) : (
        <div className="sample-preview">
          <div className="sample-preview-header">
            <div>
              <span className="sample-preview-kicker">ARHIIVI NÄIDIS</span>
              <strong>Teemade aktiivsus ajas</strong>
            </div>
            <span className="sample-badge">Illustratiivne</span>
          </div>
          <div className="timeline-chart sample-chart" aria-label="Illustratiivne kõnede ajajoon">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart
                data={[
                  { month: "jaan", count: 14 },
                  { month: "veebr", count: 22 },
                  { month: "märts", count: 18 },
                  { month: "apr", count: 34 },
                  { month: "mai", count: 27 },
                  { month: "juuni", count: 42 },
                  { month: "juuli", count: 31 },
                  { month: "aug", count: 48 },
                  { month: "sept", count: 39 },
                  { month: "okt", count: 58 },
                  { month: "nov", count: 46 },
                  { month: "dets", count: 63 },
                ]}
                margin={{ top: 8, right: 8, left: -20, bottom: 0 }}
              >
                <defs>
                  <linearGradient id="sampleArea" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#315b84" stopOpacity={0.14} />
                    <stop offset="95%" stopColor="#315b84" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis
                  dataKey="month"
                  stroke="#d4dce5"
                  tick={{ fill: "#738195", fontSize: 10 }}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis hide />
                <Area
                  type="monotone"
                  dataKey="count"
                  stroke="#315b84"
                  strokeWidth={2}
                  fill="url(#sampleArea)"
                  dot={false}
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <p>
            Graafik kuvab näidisandmeid. Sisesta märksõna, et vaadata arhiivi tegelikke tulemusi.
          </p>
        </div>
      )}
      <div className="chart-footer">
        <span className="legend-dot" /> Kõnede arv valitud perioodis
      </div>
    </section>
  );
}

export default ActivityChart;
