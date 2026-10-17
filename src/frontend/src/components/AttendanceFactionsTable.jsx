import React from "react";
import { formatFactionName, formatMetricRatio, formatVoteSplit } from "../lib/formatters";

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
            <th
              scope="col"
              className="att-col-registered"
              aria-sort={getAriaSort("registered_pct")}
            >
              <button
                type="button"
                className="att-sort-btn"
                onClick={() => requestFactionSort("registered_pct")}
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
                onClick={() => requestFactionSort("votes_voted_pct")}
              >
                <span className="att-header-text-full">Osales hääletustel</span>
                <span className="att-header-text-short">Hääletustel</span>{" "}
                {getSortIndicator("votes_voted_pct")}
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          {sortedFactionStats.length === 0 ? (
            <tr>
              <td colSpan={5} style={{ textAlign: "center", padding: "2.5rem", color: "#64748b" }}>
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

export default AttendanceFactionsTable;
