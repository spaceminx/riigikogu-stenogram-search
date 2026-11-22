import React from "react";

export function SpeechesHeader({ totalCount, sortParam, onSortChange }) {
  return (
    <div className="chart-header speeches-header-bar">
      <div className="speeches-header-heading">
        <h2 className="speeches-view-title">
          Leitud stenogrammid
          <span className="results-badge" aria-live="polite">
            {totalCount.toLocaleString("et-EE")} tk
          </span>
        </h2>
      </div>

      <div className="speeches-header-controls">
        <div className="sort-control-wrap">
          <label htmlFor="search-sort-select" className="sort-label">
            Järjestus:
          </label>
          <select
            id="search-sort-select"
            className="search-sort-select"
            value={sortParam}
            onChange={(e) => onSortChange(e.target.value)}
          >
            <option value="date_desc">Uuemad enne</option>
            <option value="date_asc">Vanemad enne</option>
            <option value="match_count_desc">Märksõnade sagedus</option>
          </select>
        </div>
      </div>
    </div>
  );
}

export default SpeechesHeader;
