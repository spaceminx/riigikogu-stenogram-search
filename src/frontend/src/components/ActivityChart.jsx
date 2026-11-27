import React, { lazy, Suspense } from "react";
import { formatActivityShare, formatActivityTooltip } from "../lib/activityUtils";
import {
  formatDayAxis,
  formatDayTooltip,
  formatMonthAxis,
  formatMonthTooltip,
  formatWeekAxis,
  formatWeekTooltip,
} from "../lib/formatters";

// The chart library (~100 KB gzipped) is loaded only when bars are drawn, not with the page
const ActivityBars = lazy(() => import("./ActivityBars"));

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

  const xKey =
    interval === "daily"
      ? "date"
      : interval === "weekly"
        ? activity[0]?.week_start
          ? "week_start"
          : "week"
        : "month";

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
          {/* The table below carries the same numbers for screen readers */}
          <div className="timeline-chart-bars" aria-hidden="true">
            <Suspense fallback={null}>
              <ActivityBars
                activity={activity}
                xKey={xKey}
                scale={scale}
                theme={theme}
                formatAxisTick={formatAxisTick}
                formatYAxisTick={formatYAxisTick}
                formatTooltipLabel={formatTooltipLabel}
              />
            </Suspense>
          </div>
          {/* A table ignores width: 1px, so the wrapper hides it */}
          <div className="visually-hidden">
            <table>
              <caption>{title}</caption>
              <thead>
                <tr>
                  <th scope="col">Periood</th>
                  <th scope="col">{scale === "share" ? "Osakaal" : "Sõnavõtte"}</th>
                </tr>
              </thead>
              <tbody>
                {activity.map((row) => (
                  <tr key={row[xKey]}>
                    <th scope="row">{formatTooltipLabel(row[xKey], [{ payload: row }])}</th>
                    <td>{formatActivityTooltip(row, scale)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
            : "Sõnavõttude arv valitud perioodis"}
        </div>
      )}
    </section>
  );
}

export default ActivityChart;
