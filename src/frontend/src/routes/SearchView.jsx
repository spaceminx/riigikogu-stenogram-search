import React, { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { fetchActivity, fetchSearch, fetchSpeakers, fetchSpeechContext } from "../lib/api";
import { parseQueryToGroups } from "../lib/formatters";
import SearchQueryInput from "../components/SearchQueryInput";
import SearchFilters from "../components/SearchFilters";
import SpeechCard from "../components/SpeechCard";
import ActivityChart from "../components/ActivityChart";
import SpeakersPanel from "../components/SpeakersPanel";
import ContextModal from "../components/ContextModal";
import SpeechesHeader from "../components/SpeechesHeader";
import Pagination from "../components/Pagination";

const PAGE_SIZE = 50;

export function SearchView({
  memberships = [],
  searchFactionsList = [],
  plenaryDates = [],
  theme = "light",
}) {
  const [searchParams, setSearchParams] = useSearchParams();

  // Search parameters from URL
  const queryParam = searchParams.get("q") || "";
  const membershipParam = searchParams.get("membership") || "all";
  const factionParam = searchParams.get("faction") || "";
  const speakerParam = searchParams.get("speaker") || "";
  const startDateParam = searchParams.get("start_date") || "";
  const endDateParam = searchParams.get("end_date") || "";
  const sortParam = searchParams.get("sort") || "date_desc";
  const intervalParam = searchParams.get("interval") || "monthly";
  const pageParam = parseInt(searchParams.get("page") || "1", 10) || 1;
  const excludeChairParam =
    searchParams.get("exclude_chair") === "true" || searchParams.get("exclude_chair") === "1";
  const speechCategoryParam = searchParams.get("speech_category") || "";

  // Local state for filter form - only written to URL upon search submit
  const [filterMembership, setFilterMembership] = useState(membershipParam);
  const [filterFaction, setFilterFaction] = useState(factionParam);
  const [filterSpeaker, setFilterSpeaker] = useState(speakerParam);
  const [filterDateRange, setFilterDateRange] = useState({
    startDate: startDateParam,
    endDate: endDateParam,
  });
  const [filterExcludeChair, setFilterExcludeChair] = useState(excludeChairParam);
  const [filterSpeechCategory, setFilterSpeechCategory] = useState(speechCategoryParam);

  // Sync draft filters during render if URL changes externally (e.g. Back/Forward)
  const urlFiltersKey = `${membershipParam}|${factionParam}|${speakerParam}|${startDateParam}|${endDateParam}|${excludeChairParam}|${speechCategoryParam}`;
  const [prevUrlFiltersKey, setPrevUrlFiltersKey] = useState(urlFiltersKey);
  if (prevUrlFiltersKey !== urlFiltersKey) {
    setPrevUrlFiltersKey(urlFiltersKey);
    setFilterMembership(membershipParam);
    setFilterFaction(factionParam);
    setFilterSpeaker(speakerParam);
    setFilterDateRange({ startDate: startDateParam, endDate: endDateParam });
    setFilterExcludeChair(excludeChairParam);
    setFilterSpeechCategory(speechCategoryParam);
  }

  // Local state for interactive editing of input query tokens
  const [groups, setGroups] = useState(() => parseQueryToGroups(queryParam));
  const [inputValue, setInputValue] = useState("");

  // Search results state
  const [speeches, setSpeeches] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [activity, setActivity] = useState([]);
  const [speakers, setSpeakers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [activityLoading, setActivityLoading] = useState(false);
  const [error, setError] = useState(null);

  // Context modal state
  const [activeSpeechContext, setActiveSpeechContext] = useState(null);

  const searchAbortRef = useRef(null);
  const searchRequestIdRef = useRef(0);

  const [prevQuery, setPrevQuery] = useState(queryParam);
  if (prevQuery !== queryParam) {
    setPrevQuery(queryParam);
    setGroups(parseQueryToGroups(queryParam));
  }

  const hasSearchQuery = Boolean(queryParam.trim());

  // Main search effect: triggered only when search parameters change (excluding interval)
  useEffect(() => {
    if (!hasSearchQuery) {
      return;
    }

    if (searchAbortRef.current) {
      searchAbortRef.current.abort();
    }
    const abortController = new AbortController();
    searchAbortRef.current = abortController;
    const currentRequestId = ++searchRequestIdRef.current;

    Promise.resolve().then(() => {
      if (currentRequestId === searchRequestIdRef.current) {
        setLoading(true);
        setError(null);
      }
    });

    const offset = (pageParam - 1) * PAGE_SIZE;

    Promise.all([
      fetchSearch(
        {
          query: queryParam,
          limit: PAGE_SIZE,
          offset,
          membership: membershipParam,
          faction: factionParam || null,
          speaker: speakerParam || null,
          startDate: startDateParam || null,
          endDate: endDateParam || null,
          sortBy: sortParam,
          excludeChair: excludeChairParam,
          speechCategory: speechCategoryParam || null,
        },
        abortController.signal
      ),
      fetchActivity(
        {
          query: queryParam,
          interval: intervalParam,
          membership: membershipParam,
          faction: factionParam || null,
          speaker: speakerParam || null,
          startDate: startDateParam || null,
          endDate: endDateParam || null,
          excludeChair: excludeChairParam,
          speechCategory: speechCategoryParam || null,
        },
        "monthly",
        abortController.signal
      ),
      fetchSpeakers(
        {
          query: queryParam,
          limit: 20,
          membership: membershipParam,
          faction: factionParam || null,
          speaker: speakerParam || null,
          startDate: startDateParam || null,
          endDate: endDateParam || null,
          excludeChair: excludeChairParam,
          speechCategory: speechCategoryParam || null,
        },
        20,
        abortController.signal
      ),
    ])
      .then(([searchData, activityData, speakersData]) => {
        if (currentRequestId !== searchRequestIdRef.current) return;
        setSpeeches(searchData.results || []);
        setTotalCount(searchData.total_count || 0);
        setActivity(activityData.activity || []);
        setSpeakers(speakersData.speakers || []);
        setLoading(false);
      })
      .catch((err) => {
        if (err.name === "AbortError") return;
        if (currentRequestId !== searchRequestIdRef.current) return;
        setSpeeches([]);
        setTotalCount(0);
        setActivity([]);
        setSpeakers([]);
        setError(err.message || "Otsingupäring ebaõnnestus.");
        setLoading(false);
      });

    return () => {
      abortController.abort();
    };
    // intervalParam is intentionally omitted: interval changes only re-fetch activity in handleIntervalChange
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    queryParam,
    membershipParam,
    factionParam,
    speakerParam,
    startDateParam,
    endDateParam,
    sortParam,
    pageParam,
    excludeChairParam,
    speechCategoryParam,
    hasSearchQuery,
  ]);

  const handleSearchSubmit = (e) => {
    if (e) e.preventDefault();
    let finalGroups = [...groups];
    if (inputValue.trim()) {
      finalGroups[finalGroups.length - 1] = [
        ...finalGroups[finalGroups.length - 1],
        inputValue.trim(),
      ];
      setGroups(finalGroups);
      setInputValue("");
    }
    finalGroups = finalGroups.filter((g) => g.length > 0);
    const queryString = finalGroups.map((g) => g.join(" ")).join(", ");

    const next = new URLSearchParams();
    if (queryString) next.set("q", queryString);
    if (filterMembership && filterMembership !== "all") next.set("membership", filterMembership);
    if (filterFaction) next.set("faction", filterFaction);
    if (filterSpeaker.trim()) next.set("speaker", filterSpeaker.trim());
    if (filterDateRange.startDate) next.set("start_date", filterDateRange.startDate);
    if (filterDateRange.endDate) next.set("end_date", filterDateRange.endDate);
    if (filterExcludeChair) next.set("exclude_chair", "true");
    if (filterSpeechCategory) next.set("speech_category", filterSpeechCategory);
    if (sortParam && sortParam !== "date_desc") next.set("sort", sortParam);
    if (intervalParam && intervalParam !== "monthly") next.set("interval", intervalParam);

    setSearchParams(next);
  };

  const handleSortChange = (newSort) => {
    const next = new URLSearchParams(searchParams);
    if (newSort === "date_desc") {
      next.delete("sort");
    } else {
      next.set("sort", newSort);
    }
    next.delete("page");
    setSearchParams(next, { replace: true });
  };

  const handleIntervalChange = (newInterval) => {
    const next = new URLSearchParams(searchParams);
    if (newInterval === "monthly") {
      next.delete("interval");
    } else {
      next.set("interval", newInterval);
    }
    setSearchParams(next, { replace: true });

    if (hasSearchQuery) {
      setActivityLoading(true);
      fetchActivity({
        query: queryParam,
        interval: newInterval,
        membership: membershipParam,
        faction: factionParam || null,
        speaker: speakerParam || null,
        startDate: startDateParam || null,
        endDate: endDateParam || null,
        excludeChair: excludeChairParam,
        speechCategory: speechCategoryParam || null,
      })
        .then((data) => {
          setActivity(data.activity || []);
        })
        .catch(() => {})
        .finally(() => {
          setActivityLoading(false);
        });
    }
  };

  const handlePageChange = (newPage) => {
    const next = new URLSearchParams(searchParams);
    if (newPage <= 1) {
      next.delete("page");
    } else {
      next.set("page", String(newPage));
    }
    setSearchParams(next, { replace: true });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleResetFilters = () => {
    setFilterMembership("all");
    setFilterFaction("");
    setFilterSpeaker("");
    setFilterDateRange({ startDate: "", endDate: "" });
    setFilterExcludeChair(false);
    setFilterSpeechCategory("");
  };

  const handleOpenContext = async (speechId) => {
    try {
      const data = await fetchSpeechContext(speechId, queryParam);
      setActiveSpeechContext(data);
    } catch (err) {
      setError(err.message || "Konteksti laadimine ebaõnnestus.");
    }
  };

  const currentTotalCount = hasSearchQuery ? totalCount : 0;
  const currentSpeeches = hasSearchQuery ? speeches : [];
  const currentActivity = hasSearchQuery ? activity : [];
  const currentSpeakers = hasSearchQuery ? speakers : [];

  const totalPages = Math.max(1, Math.ceil(currentTotalCount / PAGE_SIZE));

  const exportParams = {
    query: queryParam,
    membership: membershipParam,
    faction: factionParam || null,
    speaker: speakerParam || null,
    startDate: startDateParam || null,
    endDate: endDateParam || null,
    sortBy: sortParam,
    excludeChair: excludeChairParam,
    speechCategory: speechCategoryParam || null,
  };

  return (
    <div style={{ marginTop: "0.5rem" }}>
      <SearchQueryInput
        groups={groups}
        setGroups={setGroups}
        inputValue={inputValue}
        setInputValue={setInputValue}
        onSearch={handleSearchSubmit}
        loading={loading}
      />

      <SearchFilters
        searchMembership={filterMembership}
        setSearchMembership={setFilterMembership}
        memberships={memberships}
        searchFaction={filterFaction}
        setSearchFaction={setFilterFaction}
        searchFactionsList={searchFactionsList}
        plenaryDates={plenaryDates}
        searchDateRange={filterDateRange}
        setSearchDateRange={setFilterDateRange}
        searchSpeaker={filterSpeaker}
        setSearchSpeaker={setFilterSpeaker}
        searchSpeechCategory={filterSpeechCategory}
        setSearchSpeechCategory={setFilterSpeechCategory}
        searchExcludeChair={filterExcludeChair}
        setSearchExcludeChair={setFilterExcludeChair}
        onResetFilters={handleResetFilters}
      />

      {error && (
        <div className="error-banner">
          <div className="error-content">
            <span className="error-icon">!</span>
            <span>{error}</span>
          </div>
          <button className="error-dismiss" onClick={() => setError(null)}>
            &times;
          </button>
        </div>
      )}

      {hasSearchQuery && currentActivity.length > 0 && (
        <div className="dashboard-grid" style={{ marginBottom: "1.5rem" }}>
          <ActivityChart
            activity={currentActivity}
            interval={intervalParam}
            onIntervalChange={handleIntervalChange}
            loading={activityLoading}
            theme={theme}
          />
          <aside className="dashboard-rail">
            <SpeakersPanel speakers={currentSpeakers} showingArchiveSpeakers={false} />
          </aside>
        </div>
      )}

      <div className="glass-panel">
        <SpeechesHeader
          totalCount={currentTotalCount}
          sortParam={sortParam}
          onSortChange={handleSortChange}
          exportParams={exportParams}
        />

        {!hasSearchQuery ? (
          <div className="empty-state" style={{ padding: "3rem 1rem" }}>
            <p>Sisesta otsisõna või vali huvipakkuv teema stenogrammidest otsimiseks.</p>
          </div>
        ) : loading ? (
          <div className="empty-state" style={{ padding: "3rem 1rem" }}>
            <p>Otsin stenogramme...</p>
          </div>
        ) : currentSpeeches.length === 0 ? (
          <div className="empty-state" style={{ padding: "3rem 1rem" }}>
            <p>Otsingutingimustele vastavaid kõnesid ei leitud.</p>
          </div>
        ) : (
          <>
            <div className="speeches-list">
              {currentSpeeches.map((speech) => (
                <SpeechCard
                  key={speech.id}
                  speech={speech}
                  mode="search"
                  groups={groups}
                  onOpenContext={handleOpenContext}
                />
              ))}
            </div>

            <Pagination
              currentPage={pageParam}
              totalPages={totalPages}
              onPageChange={handlePageChange}
              loading={loading}
            />
          </>
        )}
      </div>

      {activeSpeechContext && (
        <ContextModal
          activeSpeechContext={activeSpeechContext}
          onClose={() => setActiveSpeechContext(null)}
          groups={groups}
        />
      )}
    </div>
  );
}

export default SearchView;
