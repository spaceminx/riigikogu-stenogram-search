import React from "react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatActivityTooltip } from "../lib/activityUtils";
import { chartColors } from "../lib/chartColors";

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

/**
 * The bars of ActivityChart. A module of its own so that React.lazy can load the chart library
 * after the page; ActivityChart keeps the header, the states and a table with the same numbers.
 */
export default function ActivityBars({
  activity,
  xKey,
  scale,
  theme,
  formatAxisTick,
  formatYAxisTick,
  formatTooltipLabel,
}) {
  const colors = chartColors(theme);
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

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart
        data={activity}
        margin={{ top: 12, right: 8, left: -20, bottom: 0 }}
        accessibilityLayer={false}
      >
        <XAxis
          dataKey={xKey}
          stroke={colors.border}
          tick={{ fill: colors.muted, fontSize: 11 }}
          tickFormatter={formatAxisTick}
          tickLine={false}
          axisLine={false}
          minTickGap={24}
        />
        <YAxis
          stroke={colors.border}
          tick={{ fill: colors.muted, fontSize: 11 }}
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
          name={scale === "share" ? "Osakaal" : "Sõnavõtte"}
          fill={colors.accent}
          radius={[3, 3, 0, 0]}
          maxBarSize={40}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}
