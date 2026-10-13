import React from "react";
import { Link } from "react-router-dom";
import { formatFactionName, getPercentageColor } from "../lib/formatters";

export function AttendanceMembersTable({ sortedStats, sortConfig, requestSort }) {
  const getSortIndicator = (key) => {
    if (sortConfig.key !== key) return "";
    return sortConfig.direction === "ascending" ? "↑" : "↓";
  };

  const getAriaSort = (key) => {
    if (sortConfig.key !== key) return "none";
    return sortConfig.direction === "ascending" ? "ascending" : "descending";
  };

  return (
    <div className="attendance-list" role="region" aria-label="Saadikute kohaloleku tabel">
      <table className="attendance-table">
        <caption className="attendance-table-caption">
          Saadikute kohaloleku kontrollide statistika
        </caption>
        <thead>
          <tr className="attendance-header-row">
            <th scope="col" className="att-col-rank">
              #
            </th>
            <th scope="col" className="att-col-name" aria-sort={getAriaSort("member_name")}>
              <button
                type="button"
                className="att-sort-btn"
                onClick={() => requestSort("member_name")}
              >
                Saadik {getSortIndicator("member_name")}
              </button>
            </th>
            <th scope="col" className="att-col-faction" aria-sort={getAriaSort("faction")}>
              <button type="button" className="att-sort-btn" onClick={() => requestSort("faction")}>
                Fraktsioon {getSortIndicator("faction")}
              </button>
            </th>
            <th scope="col" className="att-col-total" aria-sort={getAriaSort("total_sessions")}>
              <button
                type="button"
                className="att-sort-btn"
                onClick={() => requestSort("total_sessions")}
              >
                Kontrolle {getSortIndicator("total_sessions")}
              </button>
            </th>
            <th scope="col" className="att-col-present" aria-sort={getAriaSort("present_sessions")}>
              <button
                type="button"
                className="att-sort-btn"
                onClick={() => requestSort("present_sessions")}
              >
                Kohal {getSortIndicator("present_sessions")}
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
                onClick={() => requestSort("attendance_percentage")}
              >
                % {getSortIndicator("attendance_percentage")}
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          {sortedStats.length === 0 ? (
            <tr>
              <td colSpan={6} style={{ textAlign: "center", padding: "2.5rem", color: "#64748b" }}>
                Valitud filtritele vastavaid saadikuid ei leitud.
              </td>
            </tr>
          ) : (
            sortedStats.map((stat, idx) => (
              <tr key={stat.member_uuid || idx} className="attendance-row">
                <td className="att-col-rank">{idx + 1}</td>
                <td className="att-col-name">
                  {stat.member_uuid ? (
                    <Link
                      to={`/saadik/${encodeURIComponent(stat.member_uuid)}`}
                      className="speaker-name-link"
                    >
                      {stat.member_name}
                    </Link>
                  ) : (
                    stat.member_name
                  )}
                </td>
                <td className="att-col-faction">
                  <span className="faction-badge" title={stat.faction}>
                    {formatFactionName(stat.faction)}
                  </span>
                </td>
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

export default AttendanceMembersTable;
