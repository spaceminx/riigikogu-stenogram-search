import React from "react";
import { Search } from "lucide-react";
import DateRangeCalendar from "../DateRangeCalendar";
import { formatFactionName } from "../lib/formatters";

export function SearchFilters({
  searchMembership,
  setSearchMembership,
  memberships,
  searchFaction,
  setSearchFaction,
  searchFactionsList,
  plenaryDates,
  searchDateRange,
  setSearchDateRange,
  searchSpeaker,
  setSearchSpeaker,
  searchSpeechCategory,
  setSearchSpeechCategory,
  searchExcludeChair,
  setSearchExcludeChair,
  searchExactMatch,
  setSearchExactMatch,
  onResetFilters,
}) {
  const hasActiveFilters =
    searchMembership !== "all" ||
    searchFaction !== "" ||
    searchSpeaker.trim() !== "" ||
    searchExcludeChair ||
    searchExactMatch ||
    searchSpeechCategory !== "" ||
    Boolean(searchDateRange.startDate || searchDateRange.endDate);

  return (
    <div className="search-filters-row">
      <div className="filter-group-item">
        <label htmlFor="filter-membership" className="filter-label">
          Koosseis:
        </label>
        <select
          id="filter-membership"
          className="filter-select"
          value={searchMembership}
          onChange={(e) => setSearchMembership(e.target.value)}
        >
          <option value="all">Kõik (2019–praegu)</option>
          {memberships.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name || `${m.id}. Riigikogu`}
            </option>
          ))}
        </select>
      </div>

      <div className="filter-group-item">
        <label htmlFor="filter-faction" className="filter-label">
          Fraktsioon:
        </label>
        <select
          id="filter-faction"
          className="filter-select"
          value={searchFaction}
          onChange={(e) => setSearchFaction(e.target.value)}
        >
          <option value="">Kõik fraktsioonid</option>
          {searchFactionsList.map((fac, idx) => (
            <option key={idx} value={fac}>
              {formatFactionName(fac)}
            </option>
          ))}
        </select>
      </div>

      <DateRangeCalendar
        dates={plenaryDates}
        memberships={memberships}
        value={searchDateRange}
        onChange={setSearchDateRange}
      />

      <div className="filter-group-item speaker-filter-item">
        <label htmlFor="filter-speaker" className="filter-label">
          Esineja:
        </label>
        <div className="filter-input-wrap">
          <Search className="filter-search-icon" aria-hidden="true" />
          <input
            id="filter-speaker"
            type="text"
            className="filter-text-input"
            placeholder="Nt Kaja Kallas..."
            value={searchSpeaker}
            onChange={(e) => setSearchSpeaker(e.target.value)}
          />
          {searchSpeaker && (
            <button
              type="button"
              className="filter-clear-icon-btn"
              onClick={() => setSearchSpeaker("")}
              title="Tühjenda esineja väli"
            >
              &times;
            </button>
          )}
        </div>
      </div>

      <div className="filter-group-item">
        <label htmlFor="filter-speech-type" className="filter-label">
          Sõnavõtu liik:
        </label>
        <select
          id="filter-speech-type"
          className="filter-select"
          value={searchSpeechCategory}
          onChange={(e) => setSearchSpeechCategory(e.target.value)}
        >
          <option value="">Kõik</option>
          <option value="speeches">Kõned</option>
          <option value="questions">Küsimused ja repliigid</option>
          <option value="procedural">Protseduurilised</option>
        </select>
      </div>

      <div className="filter-group-item filter-checkbox-item">
        <label htmlFor="filter-exclude-chair" className="filter-checkbox-label filter-label">
          <input
            id="filter-exclude-chair"
            type="checkbox"
            checked={searchExcludeChair}
            onChange={(e) => setSearchExcludeChair(e.target.checked)}
          />
          <span>Jäta istungi juhataja välja</span>
        </label>
      </div>

      <div className="filter-group-item filter-checkbox-item">
        <label htmlFor="filter-exact-match" className="filter-checkbox-label filter-label">
          <input
            id="filter-exact-match"
            type="checkbox"
            checked={searchExactMatch}
            onChange={(e) => setSearchExactMatch(e.target.checked)}
          />
          <span>Ainult täpne sõna (ilma liitsõnadeta)</span>
        </label>
      </div>

      {hasActiveFilters && (
        <button
          type="button"
          className="reset-filters-btn"
          onClick={onResetFilters}
          title="Lähtesta kõik otsingufiltrid"
        >
          Lähtesta filtrid
        </button>
      )}
    </div>
  );
}

export default SearchFilters;
