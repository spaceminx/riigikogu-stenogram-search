import React, { useState } from "react";
import { useSearchParams } from "react-router-dom";
import useSWR from "swr";
import { Search, X } from "lucide-react";
import { fetchDrafts } from "../lib/api";
import { DRAFT_STATUS_GROUPS, formatDraftType } from "../lib/draftUtils";
import { toRoman } from "../lib/formatters";
import Pagination from "../components/Pagination";
import DraftRow from "../components/DraftRow";
import { usePageMeta } from "../lib/usePageMeta";

const PAGE_SIZE = 50;

function withCount(label, count) {
  return count === undefined ? label : `${label} (${count.toLocaleString("et-EE")})`;
}

export function DraftsView({ memberships = [] }) {
  const [searchParams, setSearchParams] = useSearchParams();

  usePageMeta(
    "Eelnõud — Riigivaade",
    "Riigikogu eelnõud: menetlusetapp, juhtivkomisjon, täiskogu arutelud ja hääletused."
  );

  const qParam = searchParams.get("q") || "";
  const membershipParam = searchParams.get("membership") || "";
  const typeParam = searchParams.get("type") || "";
  const statusParam = searchParams.get("status") || "";
  const committeeParam = searchParams.get("committee") || "";
  const sortParam = searchParams.get("sort") === "initiated" ? "initiated" : "recent";
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
        (key === "sort" && val === "recent")
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

  const { data, error, isLoading, isValidating } = useSWR(
    [
      "drafts-list",
      membershipParam,
      typeParam,
      statusParam,
      committeeParam,
      qParam,
      sortParam,
      pageParam,
    ],
    () =>
      fetchDrafts({
        membership: membershipParam || null,
        type: typeParam || null,
        status: statusParam || null,
        committee: committeeParam || null,
        q: qParam || null,
        sort: sortParam,
        limit: PAGE_SIZE,
        offset: (pageParam - 1) * PAGE_SIZE,
      }),
    {
      revalidateOnFocus: false,
      shouldRetryOnError: false,
      keepPreviousData: true,
    }
  );

  const results = data?.results || [];
  const total = data?.total || 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);
  const facets = data?.facets || {};

  // Options come from the facets; a selected value stays listed even when nothing matches it
  const typeCounts = facets.type || {};
  const typeOptions = Object.keys(typeCounts);
  if (typeParam && !typeOptions.includes(typeParam)) typeOptions.push(typeParam);
  const statusCounts = facets.status || {};
  const statusOptions = DRAFT_STATUS_GROUPS.filter(
    (g) => g.value in statusCounts || g.value === statusParam
  );
  const committeeOptions = [...(facets.committee || [])];
  if (committeeParam && !committeeOptions.some((c) => c.uuid === committeeParam)) {
    committeeOptions.push({ uuid: committeeParam, name: "Valitud komisjon", count: 0 });
  }
  const membershipOptions = [...memberships].sort((a, b) => b.number - a.number);

  const hasFilters = Boolean(
    qParam || membershipParam || typeParam || statusParam || committeeParam
  );

  return (
    <div className="drafts-view-container">
      <div className="drafts-controls glass-panel">
        <form className="votings-search-row" onSubmit={handleSearchSubmit}>
          <div className="filter-input-wrap votings-search-input-wrap">
            <Search className="filter-search-icon" aria-hidden="true" />
            <input
              type="text"
              className="filter-text-input"
              aria-label="Otsi eelnõu pealkirja või numbri järgi"
              placeholder="Pealkiri või number (nt 919 SE)"
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

        <div className="drafts-filters-row">
          <div className="filter-group-item">
            <label htmlFor="filter-draft-membership" className="filter-label">
              Koosseis:
            </label>
            <select
              id="filter-draft-membership"
              className="filter-select"
              value={membershipParam}
              onChange={(e) => updateFilters({ membership: e.target.value })}
            >
              <option value="">Kõik</option>
              {membershipOptions.map((m) => (
                <option key={m.number} value={String(m.number)}>
                  {toRoman(m.number)} koosseis
                </option>
              ))}
            </select>
          </div>

          <div className="filter-group-item">
            <label htmlFor="filter-draft-status" className="filter-label">
              Seis:
            </label>
            <select
              id="filter-draft-status"
              className="filter-select"
              value={statusParam}
              onChange={(e) => updateFilters({ status: e.target.value })}
            >
              <option value="">Kõik</option>
              {statusOptions.map((g) => (
                <option key={g.value} value={g.value}>
                  {withCount(g.label, statusCounts[g.value] ?? 0)}
                </option>
              ))}
            </select>
          </div>

          <div className="filter-group-item">
            <label htmlFor="filter-draft-type" className="filter-label">
              Liik:
            </label>
            <select
              id="filter-draft-type"
              className="filter-select"
              value={typeParam}
              onChange={(e) => updateFilters({ type: e.target.value })}
            >
              <option value="">Kõik</option>
              {typeOptions.map((code) => (
                <option key={code} value={code}>
                  {withCount(`${formatDraftType(code)} (${code})`, typeCounts[code] ?? 0)}
                </option>
              ))}
            </select>
          </div>

          <div className="filter-group-item">
            <label htmlFor="filter-draft-committee" className="filter-label">
              Juhtivkomisjon:
            </label>
            <select
              id="filter-draft-committee"
              className="filter-select"
              value={committeeParam}
              onChange={(e) => updateFilters({ committee: e.target.value })}
            >
              <option value="">Kõik</option>
              {committeeOptions.map((c) => (
                <option key={c.uuid} value={c.uuid}>
                  {withCount(c.name, c.count)}
                </option>
              ))}
            </select>
          </div>

          <div className="filter-group-item">
            <label htmlFor="filter-draft-sort" className="filter-label">
              Järjestus:
            </label>
            <select
              id="filter-draft-sort"
              className="filter-select"
              value={sortParam}
              onChange={(e) => updateFilters({ sort: e.target.value })}
            >
              <option value="recent">Viimati muutunud</option>
              <option value="initiated">Algatamise aeg</option>
            </select>
          </div>
        </div>
      </div>

      <div className="votings-results-header">
        <h2 className="votings-heading">
          Eelnõud
          {data && (
            <span className="results-badge">
              {total.toLocaleString("et-EE")} {total === 1 ? "eelnõu" : "eelnõud"}
            </span>
          )}
        </h2>
      </div>

      {isLoading && !data && (
        <div className="glass-panel" style={{ padding: "3rem", textAlign: "center" }}>
          <p style={{ color: "var(--text-secondary)" }}>Laen eelnõusid...</p>
        </div>
      )}

      {error && (
        <div className="error-banner">
          <div className="error-content">
            <span className="error-icon">!</span>
            <span>{error?.message || "Eelnõude laadimine ebaõnnestus."}</span>
          </div>
        </div>
      )}

      {data && !error && results.length === 0 && (
        <div className="glass-panel" style={{ padding: "3rem", textAlign: "center" }}>
          <p style={{ color: "var(--text-secondary)", margin: 0 }}>
            {hasFilters ? "Nende valikutega eelnõusid ei leitud." : "Eelnõusid ei leitud."}
          </p>
        </div>
      )}

      {data && !error && results.length > 0 && (
        <div className="drafts-list" aria-busy={isValidating}>
          {results.map((draft) => (
            <DraftRow key={draft.uuid} draft={draft} />
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

export default DraftsView;
