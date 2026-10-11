import React from "react";
import { formatFactionName, getPercentageColor } from "../lib/formatters";

export function AttendanceFactionsTable({
  sortedFactionStats,
  factionSortConfig,
  requestFactionSort,
  onSelectFaction,
}) {
  const getSortIndicator = (key) => {
    if (factionSortConfig.key !== key) return "";
    return factionSortConfig.direction === "ascending" ? "↑" : "↓";
  };

  return (
    <div className="attendance-list">
      <div className="attendance-header-row">
        <div className="att-col-rank">#</div>
        <div
          role="button"
          tabIndex={0}
          className="att-col-name cursor-pointer"
          onClick={() => requestFactionSort("faction")}
        >
          Fraktsioon {getSortIndicator("faction")}
        </div>
        <div
          role="button"
          tabIndex={0}
          className="att-col-count cursor-pointer"
          onClick={() => requestFactionSort("member_count")}
        >
          Saadikuid {getSortIndicator("member_count")}
        </div>
        <div
          role="button"
          tabIndex={0}
          className="att-col-total cursor-pointer"
          onClick={() => requestFactionSort("total_sessions")}
        >
          Kontrolle {getSortIndicator("total_sessions")}
        </div>
        <div
          role="button"
          tabIndex={0}
          className="att-col-present cursor-pointer"
          onClick={() => requestFactionSort("present_sessions")}
        >
          Kohal kokku {getSortIndicator("present_sessions")}
        </div>
        <div
          role="button"
          tabIndex={0}
          className="att-col-percent cursor-pointer"
          onClick={() => requestFactionSort("attendance_percentage")}
        >
          Keskmine kohalolek % {getSortIndicator("attendance_percentage")}
        </div>
      </div>

      {sortedFactionStats.length === 0 ? (
        <p style={{ textAlign: "center", padding: "2.5rem", color: "#64748b" }}>
          Fraktsioonide andmeid ei leitud.
        </p>
      ) : (
        sortedFactionStats.map((stat, idx) => (
          <div
            key={idx}
            className="attendance-row faction-row-interactive"
            onClick={() => onSelectFaction(stat.faction)}
            title={`Klõpsa, et vaadata ${stat.faction} saadikuid`}
          >
            <div className="att-col-rank">{idx + 1}</div>
            <div className="att-col-name">
              <span className="faction-title">{formatFactionName(stat.faction)}</span>
              <span className="drilldown-hint">Vaata saadikuid &rarr;</span>
            </div>
            <div className="att-col-count">{stat.member_count}</div>
            <div className="att-col-total">{stat.total_sessions}</div>
            <div className="att-col-present">{stat.present_sessions}</div>
            <div className="att-col-percent">
              <div className="percent-bar-bg">
                <div
                  className="percent-bar-fill"
                  style={{
                    width: `${stat.attendance_percentage}%`,
                    backgroundColor: getPercentageColor(stat.attendance_percentage),
                  }}
                />
              </div>
              <span className="percent-text">{stat.attendance_percentage}%</span>
            </div>
          </div>
        ))
      )}
    </div>
  );
}

export default AttendanceFactionsTable;
