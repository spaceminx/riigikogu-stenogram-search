import React from "react";
import { Link } from "react-router-dom";
import { formatFactionName, getPercentageColor } from "../lib/formatters";

export function AttendanceMembersTable({ sortedStats, sortConfig, requestSort }) {
  const getSortIndicator = (key) => {
    if (sortConfig.key !== key) return "";
    return sortConfig.direction === "ascending" ? "↑" : "↓";
  };

  return (
    <div className="attendance-list">
      <div className="attendance-header-row">
        <div className="att-col-rank">#</div>
        <div
          role="button"
          tabIndex={0}
          className="att-col-name cursor-pointer"
          onClick={() => requestSort("member_name")}
        >
          Saadik {getSortIndicator("member_name")}
        </div>
        <div
          role="button"
          tabIndex={0}
          className="att-col-faction cursor-pointer"
          onClick={() => requestSort("faction")}
        >
          Fraktsioon {getSortIndicator("faction")}
        </div>
        <div
          role="button"
          tabIndex={0}
          className="att-col-total cursor-pointer"
          onClick={() => requestSort("total_sessions")}
        >
          Kontrolle {getSortIndicator("total_sessions")}
        </div>
        <div
          role="button"
          tabIndex={0}
          className="att-col-present cursor-pointer"
          onClick={() => requestSort("present_sessions")}
        >
          Kohal {getSortIndicator("present_sessions")}
        </div>
        <div
          role="button"
          tabIndex={0}
          className="att-col-percent cursor-pointer"
          onClick={() => requestSort("attendance_percentage")}
        >
          % {getSortIndicator("attendance_percentage")}
        </div>
      </div>

      {sortedStats.length === 0 ? (
        <p style={{ textAlign: "center", padding: "2.5rem", color: "#64748b" }}>
          Valitud filtritele vastavaid saadikuid ei leitud.
        </p>
      ) : (
        sortedStats.map((stat, idx) => (
          <div key={idx} className="attendance-row">
            <div className="att-col-rank">{idx + 1}</div>
            <div className="att-col-name">
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
            </div>
            <div className="att-col-faction">
              <span className="faction-badge" title={stat.faction}>
                {formatFactionName(stat.faction)}
              </span>
            </div>
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

export default AttendanceMembersTable;
