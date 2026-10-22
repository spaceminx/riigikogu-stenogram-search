import React from "react";
import { Rss } from "lucide-react";
import { getExportUrl } from "../lib/api";

export function SpeechesHeader({
  totalCount,
  sortParam,
  onSortChange,
  exportParams,
  rssUrl = null,
}) {
  return (
    <div className="chart-header speeches-header-bar">
      <div className="speeches-header-heading">
        <h2 className="speeches-view-title">
          Leitud stenogrammid
          <span className="results-badge">{totalCount.toLocaleString("et-EE")} tk</span>
        </h2>
      </div>

      <div className="speeches-header-controls">
        {rssUrl && (
          <a
            href={rssUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="rss-feed-link"
            title="Telli selle otsingu RSS-voog"
          >
            <Rss size={13} aria-hidden="true" />
            <span>Telli RSS-voog</span>
          </a>
        )}

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

        <div className="export-actions-wrap">
          <span className="export-label">Eksport:</span>
          <a
            href={getExportUrl({ ...exportParams, format: "csv" })}
            className="export-btn-link"
            download
            title="Laadi otsingutulemused alla CSV failina"
          >
            CSV
          </a>
          <a
            href={getExportUrl({ ...exportParams, format: "json" })}
            className="export-btn-link"
            download
            title="Laadi otsingutulemused alla JSON failina"
          >
            JSON
          </a>
        </div>
      </div>
    </div>
  );
}

export default SpeechesHeader;
