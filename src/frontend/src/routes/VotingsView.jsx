import React, { useState } from "react";
import { useSearchParams } from "react-router-dom";
import useSWR from "swr";
import { Search, X } from "lucide-react";
import { fetchVotings } from "../lib/api";
import DateRangeCalendar from "../DateRangeCalendar";
import Pagination from "../components/Pagination";
import VotingRow from "../components/VotingRow";
import { usePageMeta } from "../lib/usePageMeta";

const PAGE_SIZE = 50;

export function VotingsView({ plenaryDates = [], memberships = [] }) {
  const [searchParams, setSearchParams] = useSearchParams();

  usePageMeta(
    "Hääletused — Riigivaade",
    "Riigikogu täiskogu hääletuste tulemused, saadikute hääled ja fraktsioonide jaotused."
  );

  const qParam = searchParams.get("q") || "";
  const startDateParam = searchParams.get("start_date") || "";
  const endDateParam = searchParams.get("end_date") || "";
  const typeParam = searchParams.get("type") || "";
  const pageParam = Math.max(1, parseInt(searchParams.get("page") || "1", 10) || 1);

  const [searchInput, setSearchInput] = useState(qParam);
  const [prevQParam, setPrevQParam] = useState(qParam);
  if (prevQParam !== qParam) {
    setPrevQParam(qParam);
    setSearchInput(qParam);
  }

  const updateFilters = (updates) => {
    const nextParams = new URLSearchParams(searchParams);
    for (const [key, val] of Object.entries(updates)) {
      if (val === null || val === undefined || val === "" || (key === "page" && val === 1)) {
        nextParams.delete(key);
      } else {
        nextParams.set(key, String(val));
      }
    }
    if (!("page" in updates)) {
      nextParams.delete("page");
    }
    setSearchParams(nextParams, { replace: true });
  };

  const handleSearchSubmit = (e) => {
    e?.preventDefault();
    updateFilters({ q: searchInput.trim() });
  };

  const handleClearSearch = () => {
    setSearchInput("");
    updateFilters({ q: "" });
  };

  const { data, error, isLoading } = useSWR(
    ["votings-list", startDateParam, endDateParam, qParam, typeParam, pageParam],
    () =>
      fetchVotings({
        startDate: startDateParam || null,
        endDate: endDateParam || null,
        q: qParam || null,
        type: typeParam || null,
        limit: PAGE_SIZE,
        offset: (pageParam - 1) * PAGE_SIZE,
      }),
    {
      revalidateOnFocus: false,
      shouldRetryOnError: false,
    }
  );

  const results = data?.results || [];
  const total = data?.total || 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="votings-view-container">
      <div className="votings-controls glass-panel">
        <form className="votings-search-row" onSubmit={handleSearchSubmit}>
          <div className="filter-input-wrap votings-search-input-wrap">
            <Search className="filter-search-icon" aria-hidden="true" />
            <input
              type="text"
              className="filter-text-input"
              aria-label="Otsi hääletuse või eelnõu nime järgi"
              placeholder="Otsi hääletust või eelnõu"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
            />
            {searchInput && (
              <button
                type="button"
                className="filter-clear-icon-btn"
                onClick={handleClearSearch}
                title="Tühjenda otsing"
              >
                <X size={14} aria-hidden="true" />
              </button>
            )}
          </div>
          <button type="submit" className="search-button votings-search-submit">
            Otsi
          </button>
        </form>

        <div className="votings-filters-row">
          <DateRangeCalendar
            dates={plenaryDates}
            memberships={memberships}
            value={{ startDate: startDateParam, endDate: endDateParam }}
            onChange={({ startDate, endDate }) => {
              updateFilters({ start_date: startDate, end_date: endDate });
            }}
          />

          <div className="filter-group-item">
            <label htmlFor="filter-voting-type" className="filter-label">
              Liik:
            </label>
            <select
              id="filter-voting-type"
              className="filter-select"
              value={typeParam}
              onChange={(e) => updateFilters({ type: e.target.value })}
            >
              <option value="">Kõik</option>
              <option value="AVALIK">Avalikud</option>
              <option value="SALAJANE">Salajased</option>
            </select>
          </div>
        </div>
      </div>

      <div className="votings-results-header">
        <h2 className="votings-heading">
          Hääletused
          {!isLoading && (
            <span className="results-badge">
              {total.toLocaleString("et-EE")} {total === 1 ? "tulemus" : "tulemust"}
            </span>
          )}
        </h2>
      </div>

      {isLoading && (
        <div className="glass-panel" style={{ padding: "3rem", textAlign: "center" }}>
          <p style={{ color: "var(--text-secondary)" }}>Laen hääletusi...</p>
        </div>
      )}

      {error && (
        <div className="error-banner">
          <div className="error-content">
            <span className="error-icon">!</span>
            <span>{error?.message || "Hääletuste laadimine ebaõnnestus."}</span>
          </div>
        </div>
      )}

      {!isLoading && !error && results.length === 0 && (
        <div className="glass-panel" style={{ padding: "3rem", textAlign: "center" }}>
          <p style={{ color: "var(--text-secondary)", margin: 0 }}>Hääletusi ei leitud.</p>
        </div>
      )}

      {!isLoading && !error && results.length > 0 && (
        <div className="votings-list">
          {results.map((voting) => (
            <VotingRow key={voting.uuid} voting={voting} showDate={true} />
          ))}
        </div>
      )}

      <Pagination
        currentPage={pageParam}
        totalPages={totalPages}
        onPageChange={(page) => updateFilters({ page })}
        loading={isLoading}
      />
    </div>
  );
}

export default VotingsView;
