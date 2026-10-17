import React from "react";
import { Link } from "react-router-dom";
import { formatFactionName, formatMetricRatio, formatVoteSplit } from "../lib/formatters";

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
          <tr>
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
            <th
              scope="col"
              className="att-col-registered"
              aria-sort={getAriaSort("registered_pct")}
            >
              <button
                type="button"
                className="att-sort-btn"
                onClick={() => requestSort("registered_pct")}
              >
                <span className="att-header-text-full">Registreerus kontrollides</span>
                <span className="att-header-text-short">Kontrollides</span>{" "}
                {getSortIndicator("registered_pct")}
              </button>
            </th>
            <th scope="col" className="att-col-votes" aria-sort={getAriaSort("votes_voted_pct")}>
              <button
                type="button"
                className="att-sort-btn"
                onClick={() => requestSort("votes_voted_pct")}
              >
                <span className="att-header-text-full">Osales hääletustel</span>
                <span className="att-header-text-short">Hääletustel</span>{" "}
                {getSortIndicator("votes_voted_pct")}
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          {sortedStats.length === 0 ? (
            <tr>
              <td colSpan={5} style={{ textAlign: "center", padding: "2.5rem", color: "#64748b" }}>
                Valitud filtritele vastavaid saadikuid ei leitud.
              </td>
            </tr>
          ) : (
            sortedStats.map((stat, idx) => (
              <tr key={stat.member_uuid || idx}>
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
                  {stat.faction && (
                    <div className="att-mobile-faction-badge">
                      <span className="faction-badge" title={stat.faction}>
                        {formatFactionName(stat.faction)}
                      </span>
                    </div>
                  )}
                </td>
                <td className="att-col-faction">
                  <span className="faction-badge" title={stat.faction}>
                    {formatFactionName(stat.faction)}
                  </span>
                </td>
                <td className="att-col-registered">
                  <div className="att-metric-cell">
                    <span className="att-metric-main">
                      {formatMetricRatio(
                        stat.registered_pct,
                        stat.registered_checks ?? stat.present_sessions,
                        stat.total_checks ?? stat.total_sessions
                      )}
                    </span>
                  </div>
                </td>
                <td className="att-col-votes">
                  <div className="att-metric-cell">
                    <span className="att-metric-main">
                      {formatMetricRatio(stat.votes_voted_pct, stat.votes_voted, stat.votes_total)}
                    </span>
                    {stat.votes_total > 0 && (
                      <span className="att-metric-subtext">
                        {formatVoteSplit(stat.votes_not_voted, stat.votes_absent, stat.votes_total)}
                      </span>
                    )}
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
