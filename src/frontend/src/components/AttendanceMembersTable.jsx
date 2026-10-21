import React from "react";
import { Link } from "react-router-dom";
import {
  formatFactionName,
  formatMetricRatio,
  formatVoteSplit,
  isSmallSample,
} from "../lib/formatters";

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
            <th scope="col" className="att-col-combined">
              <div className="att-mobile-header-sorts">
                <button
                  type="button"
                  className={`att-sort-btn ${sortConfig.key === "votes_voted_pct" ? "is-active" : ""}`}
                  onClick={() => requestSort("votes_voted_pct")}
                >
                  Hääletustel {getSortIndicator("votes_voted_pct")}
                </button>
                <span className="att-mobile-sort-sep">·</span>
                <button
                  type="button"
                  className={`att-sort-btn ${sortConfig.key === "registered_pct" ? "is-active" : ""}`}
                  onClick={() => requestSort("registered_pct")}
                >
                  Kontrollides {getSortIndicator("registered_pct")}
                </button>
              </div>
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
            sortedStats.map((stat, idx) => {
              const checksTotal = stat.total_checks ?? stat.total_sessions ?? 0;
              const isChecksSmall = checksTotal < 20;
              const votesTotal = stat.votes_total ?? 0;
              const isVotesSmall = votesTotal < 50;
              const isRowSmall = isSmallSample(stat, sortConfig.key);

              return (
                <tr
                  key={stat.member_uuid || idx}
                  className={isRowSmall ? "att-row-small-sample" : ""}
                >
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
                    <div
                      className={`att-metric-cell ${isChecksSmall ? "att-metric-small-sample" : ""}`}
                    >
                      <span className="att-metric-main">
                        {formatMetricRatio(
                          stat.registered_pct,
                          stat.registered_checks ?? stat.present_sessions,
                          checksTotal
                        )}
                        {isChecksSmall && <span className="att-sample-note">vähe andmeid</span>}
                      </span>
                    </div>
                  </td>
                  <td className="att-col-votes">
                    <div
                      className={`att-metric-cell ${isVotesSmall ? "att-metric-small-sample" : ""}`}
                    >
                      <span className="att-metric-main">
                        {formatMetricRatio(stat.votes_voted_pct, stat.votes_voted, votesTotal)}
                        {isVotesSmall && <span className="att-sample-note">vähe andmeid</span>}
                      </span>
                      {votesTotal > 0 && (
                        <span className="att-metric-subtext">
                          {formatVoteSplit(stat.votes_not_voted, stat.votes_absent, votesTotal)}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="att-col-combined">
                    <div className="att-mobile-stacked-cell">
                      <div
                        className={`att-mobile-metric-row ${isVotesSmall ? "att-metric-small-sample" : ""}`}
                      >
                        <span className="att-mobile-metric-label">Hääletustel:</span>{" "}
                        <span className="att-mobile-metric-val">
                          {formatMetricRatio(stat.votes_voted_pct, stat.votes_voted, votesTotal)}
                          {isVotesSmall && <span className="att-sample-note">vähe andmeid</span>}
                        </span>
                      </div>
                      {votesTotal > 0 && (
                        <div className="att-metric-subtext att-mobile-subtext">
                          {formatVoteSplit(stat.votes_not_voted, stat.votes_absent, votesTotal)}
                        </div>
                      )}
                      <div
                        className={`att-mobile-metric-row ${isChecksSmall ? "att-metric-small-sample" : ""}`}
                      >
                        <span className="att-mobile-metric-label">Kontrollides:</span>{" "}
                        <span className="att-mobile-metric-val">
                          {formatMetricRatio(
                            stat.registered_pct,
                            stat.registered_checks ?? stat.present_sessions,
                            checksTotal
                          )}
                          {isChecksSmall && <span className="att-sample-note">vähe andmeid</span>}
                        </span>
                      </div>
                    </div>
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}

export default AttendanceMembersTable;
