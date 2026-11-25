import React from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { chartColors } from "../lib/chartColors";

/**
 * A member's speeches per year as stacked bars. Loaded on its own (React.lazy) so the chart
 * library does not hold up the page; the table under it carries the same numbers, so the chart is
 * hidden from assistive technology and is not a keyboard stop.
 */
export default function PersonYearChart({ data, hasUnclassified, theme }) {
  const colors = chartColors(theme);
  const tooltipStyle = {
    contentStyle: {
      backgroundColor: colors.surface,
      color: colors.text,
      border: `1px solid ${colors.border}`,
      borderRadius: "4px",
      boxShadow: "0 2px 8px rgba(0, 0, 0, 0.2)",
    },
    itemStyle: { fontWeight: 600 },
    labelStyle: { color: colors.muted, marginBottom: "4px" },
  };

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart
        data={data}
        margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
        accessibilityLayer={false}
      >
        <CartesianGrid strokeDasharray="3 3" stroke={colors.border} vertical={false} />
        <XAxis dataKey="year" stroke={colors.border} tick={{ fill: colors.muted, fontSize: 12 }} />
        <YAxis
          stroke={colors.border}
          tick={{ fill: colors.muted, fontSize: 12 }}
          allowDecimals={false}
        />
        <Tooltip {...tooltipStyle} />
        <Legend
          wrapperStyle={{ paddingTop: "10px" }}
          formatter={(value) => <span style={{ color: colors.text }}>{value}</span>}
        />
        <Bar dataKey="speeches" name="Kõned" stackId="mp" fill={colors.series[0]} />
        <Bar
          dataKey="questions"
          name="Küsimused ja repliigid"
          stackId="mp"
          fill={colors.series[1]}
        />
        <Bar dataKey="procedural" name="Protseduurilised" stackId="mp" fill={colors.series[2]} />
        {hasUnclassified && (
          <Bar dataKey="unclassified" name="Liigitamata" stackId="mp" fill={colors.series[3]} />
        )}
      </BarChart>
    </ResponsiveContainer>
  );
}
