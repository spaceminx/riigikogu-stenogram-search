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

  const getAriaSort = (key) => {
    if (factionSortConfig.key !== key) return "none";
    return factionSortConfig.direction === "ascending" ? "ascending" : "descending";
  };

  return (
    <div className="attendance-list" role="region" aria-label="Fraktsioonide kohaloleku koondtabel">
      <table className="attendance-table">
        <caption className="attendance-table-caption">
          Fraktsioonide kohaloleku kontrollide statistika
        </caption>
        <thead>
          <tr>
            <th scope="col" className="att-col-rank">
              #
            </th>
            <th scope="col" className="att-col-name" aria-sort={getAriaSort("faction")}>
              <button
                type="button"
                className="att-sort-btn"
                onClick={() => requestFactionSort("faction")}
              >
                Fraktsioon {getSortIndicator("faction")}
              </button>
            </th>
            <th scope="col" className="att-col-count" aria-sort={getAriaSort("member_count")}>
              <button
                type="button"
                className="att-sort-btn"
                onClick={() => requestFactionSort("member_count")}
              >
                Saadikuid {getSortIndicator("member_count")}
              </button>
            </th>
            <th scope="col" className="att-col-total" aria-sort={getAriaSort("total_sessions")}>
              <button
                type="button"
                className="att-sort-btn"
                onClick={() => requestFactionSort("total_sessions")}
              >
                Kontrolle {getSortIndicator("total_sessions")}
              </button>
            </th>
            <th scope="col" className="att-col-present" aria-sort={getAriaSort("present_sessions")}>
              <button
                type="button"
                className="att-sort-btn"
                onClick={() => requestFactionSort("present_sessions")}
              >
                <span className="att-header-text-full">Kohal kokku</span>
                <span className="att-header-text-short">Kohal</span>{" "}
                {getSortIndicator("present_sessions")}
              </button>
            </th>
            <th
              scope="col"
              className="att-col-percent"
              aria-sort={getAriaSort("attendance_percentage")}
            >
              <button
                type="button"
                className="att-sort-btn"
                onClick={() => requestFactionSort("attendance_percentage")}
              >
                <span className="att-header-text-full">Keskmine kohalolek %</span>
                <span className="att-header-text-short">%</span>{" "}
                {getSortIndicator("attendance_percentage")}
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          {sortedFactionStats.length === 0 ? (
            <tr>
              <td colSpan={6} style={{ textAlign: "center", padding: "2.5rem", color: "#64748b" }}>
                Fraktsioonide andmeid ei leitud.
              </td>
            </tr>
          ) : (
            sortedFactionStats.map((stat, idx) => (
              <tr
                key={stat.faction || idx}
                className="faction-row-interactive"
                onClick={() => onSelectFaction(stat.faction)}
              >
                <td className="att-col-rank">{idx + 1}</td>
                <td className="att-col-name">
                  <button
                    type="button"
                    className="faction-drilldown-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelectFaction(stat.faction);
                    }}
                    title={`Klõpsa, et vaadata ${stat.faction} saadikuid`}
                    aria-label={`Vaata fraktsiooni ${stat.faction} saadikuid`}
                  >
                    <span className="faction-title">{formatFactionName(stat.faction)}</span>
                    <span className="drilldown-hint" aria-hidden="true">
                      Vaata saadikuid &rarr;
                    </span>
                  </button>
                  {stat.member_count != null && (
                    <div className="att-mobile-faction-badge">
                      <span className="faction-badge">
                        {stat.member_count} {stat.member_count === 1 ? "saadik" : "saadikut"}
                      </span>
                    </div>
                  )}
                </td>
                <td className="att-col-count">{stat.member_count}</td>
                <td className="att-col-total">{stat.total_sessions}</td>
                <td className="att-col-present">{stat.present_sessions}</td>
                <td className="att-col-percent">
                  <div className="percent-bar-container">
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
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

export default AttendanceFactionsTable;
