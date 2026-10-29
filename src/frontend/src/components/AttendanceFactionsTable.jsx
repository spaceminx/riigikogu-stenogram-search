import React from "react";
import {
  formatFactionNameBreakable,
  formatMetricRatio,
  formatVoteSplit,
  getChecksBarSegments,
  getVotesBarSegments,
  isSmallSample,
} from "../lib/formatters";
import { NO_FACTION } from "../lib/factionsUtils";
import VoteBar from "./VoteBar";

export function AttendanceFactionsTable({
  sortedFactionStats,
  factionSortConfig,
  requestFactionSort,
  onSelectFaction,
  role = "",
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
            <th scope="col" className="att-col-combined">
              <div className="att-mobile-header-sorts">
                <button
                  type="button"
                  className={`att-sort-btn ${factionSortConfig.key === "votes_voted_pct" ? "is-active" : ""}`}
                  onClick={() => requestFactionSort("votes_voted_pct")}
                >
                  Hääletustel {getSortIndicator("votes_voted_pct")}
                </button>
                <span className="att-mobile-sort-sep">·</span>
                <button
                  type="button"
                  className={`att-sort-btn ${factionSortConfig.key === "registered_pct" ? "is-active" : ""}`}
                  onClick={() => requestFactionSort("registered_pct")}
                >
                  Kontrollides {getSortIndicator("registered_pct")}
                </button>
              </div>
            </th>
          </tr>
        </thead>
        <tbody>
          {sortedFactionStats.length === 0 ? (
            <tr>
              <td
                colSpan={6}
                style={{ textAlign: "center", padding: "2.5rem", color: "var(--color-text-muted)" }}
              >
                Fraktsioonide andmeid ei leitud.
              </td>
            </tr>
          ) : (
            sortedFactionStats.map((stat, idx) => {
              const checksTotal = stat.total_checks ?? stat.total_sessions ?? 0;
              const isChecksSmall = checksTotal < 20;
              const votesTotal = stat.votes_total ?? 0;
              const isVotesSmall = votesTotal < 50;
              const isRowSmall = isSmallSample(stat, factionSortConfig.key);
              const isNonAligned = stat.faction === NO_FACTION || stat.faction === "Fraktsioonita";
              const hideForNonAligned = Boolean(role && isNonAligned);

              return (
                <tr
                  key={stat.faction || idx}
                  className={`faction-row-interactive ${isRowSmall ? "att-row-small-sample" : ""}`}
                  onClick={() => onSelectFaction(stat.faction)}
                >
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
                      <span className="faction-title">
                        {formatFactionNameBreakable(stat.faction)}
                      </span>
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
                    {hideForNonAligned ? (
                      <div className="att-metric-cell">
                        <span className="att-metric-main">—</span>
                      </div>
                    ) : (
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
                        <VoteBar segments={getChecksBarSegments(stat)} />
                      </div>
                    )}
                  </td>
                  <td className="att-col-votes">
                    {hideForNonAligned ? (
                      <div className="att-metric-cell">
                        <span className="att-metric-main">—</span>
                      </div>
                    ) : (
                      <div
                        className={`att-metric-cell ${isVotesSmall ? "att-metric-small-sample" : ""}`}
                      >
                        <span className="att-metric-main">
                          {formatMetricRatio(stat.votes_voted_pct, stat.votes_voted, votesTotal)}
                          {isVotesSmall && <span className="att-sample-note">vähe andmeid</span>}
                        </span>
                        <VoteBar segments={getVotesBarSegments(stat)} />
                        {votesTotal > 0 && (
                          <span className="att-metric-subtext">
                            {formatVoteSplit(stat.votes_not_voted, stat.votes_absent, votesTotal)}
                          </span>
                        )}
                      </div>
                    )}
                  </td>
                  <td className="att-col-combined">
                    {hideForNonAligned ? (
                      <div className="att-mobile-stacked-cell">
                        <span className="att-metric-main">—</span>
                      </div>
                    ) : (
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
                        <VoteBar segments={getVotesBarSegments(stat)} />
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
                        <VoteBar segments={getChecksBarSegments(stat)} />
                      </div>
                    )}
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

export default AttendanceFactionsTable;
