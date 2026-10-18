import React, { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import useSWR from "swr";
import { Search, X } from "lucide-react";
import { fetchVotings } from "../lib/api";
import { formatDate } from "../lib/calendarUtils";
import { formatOvernightTime, formatVotingSummary } from "../lib/votingUtils";
import DateRangeCalendar from "../DateRangeCalendar";
import Pagination from "../components/Pagination";

const PAGE_SIZE = 50;

export function VotingsView({ plenaryDates = [], memberships = [] }) {
  const [searchParams, setSearchParams] = useSearchParams();

  useEffect(() => {
    const prevTitle = document.title;
    document.title = "Hääletused — Riigivaade";
    return () => {
      document.title = prevTitle;
    };
  }, []);

  const qParam = searchParams.get("q") || "";
  const startDateParam = searchParams.get("start_date") || "";
  const endDateParam = searchParams.get("end_date") || "";
  const typeParam = searchParams.get("type") || "";
  const includeTechnicalParam =
    searchParams.get("include_technical") === "true" ||
    searchParams.get("include_technical") === "1";
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
      if (
        val === null ||
        val === undefined ||
        val === "" ||
        (key === "page" && val === 1) ||
        (key === "include_technical" && !val)
      ) {
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
    [
      "votings-list",
      startDateParam,
      endDateParam,
      qParam,
      typeParam,
      includeTechnicalParam,
      pageParam,
    ],
    () =>
      fetchVotings({
        startDate: startDateParam || null,
        endDate: endDateParam || null,
        q: qParam || null,
        type: typeParam || null,
        includeTechnical: includeTechnicalParam,
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
              placeholder="Otsi hääletuse või eelnõu nime järgi"
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

          <label className="checkbox-label votings-tech-checkbox">
            <input
              type="checkbox"
              checked={includeTechnicalParam}
              onChange={(e) =>
                updateFilters({ include_technical: e.target.checked ? "true" : null })
              }
            />
            <span>Näita tehnilisi kirjeid</span>
          </label>
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
          <p style={{ color: "var(--color-text-muted, #64748b)" }}>Laen hääletusi...</p>
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
          <p style={{ color: "var(--color-text-muted, #64748b)", margin: 0 }}>
            Hääletusi ei leitud.
          </p>
        </div>
      )}

      {!isLoading && !error && results.length > 0 && (
        <div className="votings-list">
          {results.map((voting) => {
            const sittingDateFormatted = formatDate(voting.sitting_date);
            const timeFormatted = formatOvernightTime(
              voting.start_time,
              voting.sitting_date,
              voting.date
            );
            const dateTimeDisplay = sittingDateFormatted
              ? `${sittingDateFormatted} ${timeFormatted}`.trim()
              : timeFormatted;
            const summary = formatVotingSummary(voting.totals);

            return (
              <Link key={voting.uuid} to={`/haaletus/${voting.uuid}`} className="voting-row-link">
                <div className="voting-row-main">
                  <div className="voting-row-meta">
                    <span className="voting-row-time">{dateTimeDisplay}</span>
                    <div className="voting-badges">
                      {voting.type === "SALAJANE" && (
                        <span className="voting-badge voting-badge-secret">Salajane</span>
                      )}
                      {voting.is_technical && (
                        <span className="voting-badge voting-badge-technical">Tehniline</span>
                      )}
                    </div>
                  </div>
                  <div className="voting-row-desc">{voting.description}</div>
                  {voting.related_document?.title && (
                    <div className="voting-row-doc">
                      {voting.related_document.reference
                        ? `${voting.related_document.reference} · `
                        : ""}
                      {voting.related_document.title}
                    </div>
                  )}
                  {summary && <div className="voting-row-summary">{summary}</div>}
                </div>
              </Link>
            );
          })}
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
