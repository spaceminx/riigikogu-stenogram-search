import React from "react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatActivityShare, formatActivityTooltip } from "../lib/activityUtils";
import {
  formatDayAxis,
  formatDayTooltip,
  formatMonthAxis,
  formatMonthTooltip,
  formatWeekAxis,
  formatWeekTooltip,
} from "../lib/formatters";

const CHART_COLORS = {
  light: {
    surface: "#ffffff",
    text: "#1c1f26",
    muted: "#5e6472",
    border: "#dadce2",
    accent: "#2e3f78",
  },
  dark: {
    surface: "#1b1e25",
    text: "#e9eaee",
    muted: "#a4a9b5",
    border: "#2d313b",
    accent: "#93a5e8",
  },
};

function ActivityCustomTooltip({ active, payload, label, formatLabel, scale, style }) {
  if (!active || !payload || payload.length === 0) return null;
  const row = payload[0]?.payload;
  const formattedLabel = formatLabel(label, payload);
  const formattedText = formatActivityTooltip(row, scale);

  return (
    <div style={style.contentStyle}>
      <div style={style.labelStyle}>{formattedLabel}</div>
      <div style={style.itemStyle}>{formattedText}</div>
    </div>
  );
}

export function ActivityChart({
  activity = [],
  interval = "monthly",
  onIntervalChange,
  scale = "count",
  onScaleChange,
  loading = false,
  error = null,
  theme = "light",
  title = "Kõnede ajajoon",
  kicker = "TEEMA LÄBI AJA",
  emptyMessage = "Sellele otsingule kõnesid ei leitud.",
}) {
  // SVG attributes cannot read CSS variables, so the chart uses the token values from tokens.css
  const colors = CHART_COLORS[theme === "dark" ? "dark" : "light"];
  const tooltipStyle = {
    contentStyle: {
      backgroundColor: colors.surface,
      color: colors.text,
      border: `1px solid ${colors.border}`,
      borderRadius: "4px",
      boxShadow: "0 2px 8px rgba(0, 0, 0, 0.2)",
    },
    itemStyle: { color: colors.accent, fontWeight: 600 },
    labelStyle: { color: colors.muted, marginBottom: "4px" },
  };

  const axisStroke = colors.border;
  const axisTickColor = colors.muted;

  const formatAxisTick = (tick) => {
    if (!tick) return "";
    if (interval === "monthly") {
      return formatMonthAxis(tick);
    }
    if (interval === "daily") {
      return formatDayAxis(tick);
    }
    if (interval === "weekly") {
      if (typeof tick === "string" && tick.length === 10) {
        return formatWeekAxis(tick);
      }
      const item = activity.find((row) => row.week === tick);
      return item?.week_start ? formatWeekAxis(item.week_start) : tick;
    }
    return tick;
  };

  const formatYAxisTick = (tick) => {
    if (scale === "share") {
      return formatActivityShare(tick) || "0%";
    }
    return tick;
  };

  const formatTooltipLabel = (label, payload) => {
    if (!label && (!payload || payload.length === 0)) return "";
    if (interval === "monthly") {
      return formatMonthTooltip(label);
    }
    if (interval === "daily") {
      return formatDayTooltip(label);
    }
    if (interval === "weekly") {
      const row = payload?.[0]?.payload;
      const weekStart =
        row?.week_start || (typeof label === "string" && label.length === 10 ? label : null);
      if (weekStart) {
        return formatWeekTooltip(weekStart);
      }
      return label;
    }
    return label;
  };

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
          {onScaleChange && (
            <div className="interval-segmented" role="group" aria-label="Ajajoone skaala">
              {[
                ["count", "Arv"],
                ["share", "Osakaal"],
              ].map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  className={`interval-segment${scale === value ? " is-active" : ""}`}
                  aria-pressed={scale === value}
                  onClick={() => onScaleChange(value)}
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
            <BarChart data={activity} margin={{ top: 12, right: 8, left: -20, bottom: 0 }}>
              <XAxis
                dataKey={
                  interval === "daily"
                    ? "date"
                    : interval === "weekly"
                      ? activity[0]?.week_start
                        ? "week_start"
                        : "week"
                      : "month"
                }
                stroke={axisStroke}
                tick={{ fill: axisTickColor, fontSize: 11 }}
                tickFormatter={formatAxisTick}
                tickLine={false}
                axisLine={false}
                minTickGap={24}
              />
              <YAxis
                stroke={axisStroke}
                tick={{ fill: axisTickColor, fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                allowDecimals={scale === "share"}
                tickFormatter={scale === "share" ? formatYAxisTick : undefined}
              />
              <Tooltip
                content={
                  <ActivityCustomTooltip
                    formatLabel={formatTooltipLabel}
                    scale={scale}
                    style={tooltipStyle}
                  />
                }
                cursor={{
                  fill: theme === "dark" ? "rgba(255, 255, 255, 0.05)" : "rgba(0, 0, 0, 0.04)",
                }}
              />
              <Bar
                dataKey={scale === "share" ? "share" : "count"}
                name={scale === "share" ? "Osakaal" : "Kõnesid"}
                fill={colors.accent}
                radius={[3, 3, 0, 0]}
                maxBarSize={40}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="chart-empty-state">
          <span>{emptyMessage}</span>
        </div>
      )}
      {activity.length > 0 && (
        <div className="chart-footer">
          <span className="legend-dot" />{" "}
          {scale === "share"
            ? "Otsingule vastavate sõnavõttude osakaal perioodis"
            : "Kõnede arv valitud perioodis"}
        </div>
      )}
    </section>
  );
}

export default ActivityChart;
