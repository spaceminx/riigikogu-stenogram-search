import React, { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import useSWR from "swr";
import {
  fetchActivity,
  fetchPerson,
  fetchSearch,
  fetchSpeakers,
  fetchSpeechContext,
} from "../lib/api";
import { mergeInputToGroups, parseQueryToGroups, serializeGroupsToQuery } from "../lib/formatters";
import { parseScaleParam, updateScaleParam } from "../lib/activityUtils";
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
  const speakerUuidParam = searchParams.get("speaker_uuid") || "";
  const startDateParam = searchParams.get("start_date") || "";
  const endDateParam = searchParams.get("end_date") || "";
  const sortParam = searchParams.get("sort") || "date_desc";
  const intervalParam = searchParams.get("interval") || "monthly";
  const scaleParam = parseScaleParam(searchParams.get("scale"));
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
  const urlFiltersKey = `${membershipParam}|${factionParam}|${speakerParam}|${speakerUuidParam}|${startDateParam}|${endDateParam}|${excludeChairParam}|${speechCategoryParam}`;
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

  const { data: speakerPerson } = useSWR(
    speakerUuidParam ? `speaker-person-${speakerUuidParam}` : null,
    () => fetchPerson(speakerUuidParam),
    { revalidateOnFocus: false, shouldRetryOnError: false }
  );

  const handleRemoveSpeakerUuid = () => {
    const next = new URLSearchParams(searchParams);
    next.delete("speaker_uuid");
    setSearchParams(next, { replace: true });
  };

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
  const [activityError, setActivityError] = useState(null);

  // Context modal state
  const [activeSpeechContext, setActiveSpeechContext] = useState(null);

  const searchAbortRef = useRef(null);
  const searchRequestIdRef = useRef(0);
  const activityAbortRef = useRef(null);
  const activityRequestIdRef = useRef(0);

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

    const currentActivityRequestId = ++activityRequestIdRef.current;
    if (activityAbortRef.current) {
      activityAbortRef.current.abort();
    }

    Promise.resolve().then(() => {
      if (currentRequestId === searchRequestIdRef.current) {
        setLoading(true);
        setError(null);
        setActivityError(null);
        setActivityLoading(true);
      }
    });

    const offset = (pageParam - 1) * PAGE_SIZE;
    const currentInterval = searchParams.get("interval") || "monthly";

    Promise.allSettled([
      fetchSearch(
        {
          query: queryParam,
          limit: PAGE_SIZE,
          offset,
          membership: membershipParam,
          faction: factionParam || null,
          speaker: speakerParam || null,
          speakerUuid: speakerUuidParam || null,
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
          interval: currentInterval,
          membership: membershipParam,
          faction: factionParam || null,
          speaker: speakerParam || null,
          speakerUuid: speakerUuidParam || null,
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
          speakerUuid: speakerUuidParam || null,
          startDate: startDateParam || null,
          endDate: endDateParam || null,
          excludeChair: excludeChairParam,
          speechCategory: speechCategoryParam || null,
        },
        20,
        abortController.signal
      ),
    ])
      .then(([searchResult, activityResult, speakersResult]) => {
        if (currentRequestId !== searchRequestIdRef.current) return;
        if (searchResult.status === "fulfilled") {
          setSpeeches(searchResult.value.results || []);
          setTotalCount(searchResult.value.total_count || 0);
        } else if (searchResult.reason?.name !== "AbortError") {
          setSpeeches([]);
          setTotalCount(0);
          setError(searchResult.reason?.message || "Otsingupäring ebaõnnestus.");
        }

        if (currentActivityRequestId === activityRequestIdRef.current) {
          if (activityResult.status === "fulfilled") {
            setActivity(activityResult.value.activity || []);
            setActivityError(null);
          } else if (activityResult.reason?.name !== "AbortError") {
            setActivity([]);
            setActivityError(activityResult.reason?.message || "Ajajoone laadimine ebaõnnestus.");
          }
          setActivityLoading(false);
        }

        if (speakersResult.status === "fulfilled") {
          setSpeakers(speakersResult.value.speakers || []);
        } else {
          setSpeakers([]);
        }
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
        setActivityLoading(false);
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
    speakerUuidParam,
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
      finalGroups = mergeInputToGroups(finalGroups, inputValue.trim());
      setGroups(finalGroups);
      setInputValue("");
    }
    finalGroups = finalGroups.filter((g) => g.length > 0);
    const queryString = serializeGroupsToQuery(finalGroups);

    const next = new URLSearchParams();
    if (queryString) next.set("q", queryString);
    if (filterMembership && filterMembership !== "all") next.set("membership", filterMembership);
    if (filterFaction) next.set("faction", filterFaction);
    if (filterSpeaker.trim()) next.set("speaker", filterSpeaker.trim());
    if (speakerUuidParam) next.set("speaker_uuid", speakerUuidParam);
    if (filterDateRange.startDate) next.set("start_date", filterDateRange.startDate);
    if (filterDateRange.endDate) next.set("end_date", filterDateRange.endDate);
    if (filterExcludeChair) next.set("exclude_chair", "true");
    if (filterSpeechCategory) next.set("speech_category", filterSpeechCategory);
    if (sortParam && sortParam !== "date_desc") next.set("sort", sortParam);
    if (intervalParam && intervalParam !== "monthly") next.set("interval", intervalParam);
    if (scaleParam === "share") next.set("scale", "share");

    setSearchParams(next);
  };

  const handleScaleChange = (newScale) => {
    const next = updateScaleParam(searchParams, newScale);
    setSearchParams(next, { replace: true });
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
      if (activityAbortRef.current) {
        activityAbortRef.current.abort();
      }
      const abortController = new AbortController();
      activityAbortRef.current = abortController;
      const currentRequestId = ++activityRequestIdRef.current;

      setActivityLoading(true);
      setActivityError(null);
      fetchActivity(
        {
          query: queryParam,
          interval: newInterval,
          membership: membershipParam,
          faction: factionParam || null,
          speaker: speakerParam || null,
          speakerUuid: speakerUuidParam || null,
          startDate: startDateParam || null,
          endDate: endDateParam || null,
          excludeChair: excludeChairParam,
          speechCategory: speechCategoryParam || null,
        },
        "monthly",
        abortController.signal
      )
        .then((data) => {
          if (currentRequestId !== activityRequestIdRef.current) return;
          setActivity(data.activity || []);
          setActivityError(null);
        })
        .catch((err) => {
          if (err.name === "AbortError") return;
          if (currentRequestId !== activityRequestIdRef.current) return;
          setActivity([]);
          setActivityError(err.message || "Ajajoone laadimine ebaõnnestus.");
        })
        .finally(() => {
          if (currentRequestId === activityRequestIdRef.current) {
            setActivityLoading(false);
          }
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
    speakerUuid: speakerUuidParam || null,
    startDate: startDateParam || null,
    endDate: endDateParam || null,
    sortBy: sortParam,
    excludeChair: excludeChairParam,
    speechCategory: speechCategoryParam || null,
  };

  return (
    <div style={{ marginTop: "0.5rem" }}>
      {speakerUuidParam && (
        <div className="speaker-filter-chip-wrapper">
          <div className="token-pill speaker-token-pill">
            <span>
              Saadiku filter: <strong>{speakerPerson?.full_name || "Laen..."}</strong>
            </span>
            <button
              type="button"
              onClick={handleRemoveSpeakerUuid}
              title="Eemalda saadiku filter"
              aria-label="Eemalda saadiku filter"
            >
              ×
            </button>
          </div>
        </div>
      )}

      <SearchQueryInput
        groups={groups}
        setGroups={setGroups}
        inputValue={inputValue}
        setInputValue={setInputValue}
        onSearch={handleSearchSubmit}
        loading={loading}
      >
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
      </SearchQueryInput>

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

      {hasSearchQuery && (currentActivity.length > 0 || activityLoading || activityError) && (
        <div className="dashboard-grid" style={{ marginBottom: "1.5rem" }}>
          <ActivityChart
            activity={currentActivity}
            interval={intervalParam}
            onIntervalChange={handleIntervalChange}
            scale={scaleParam}
            onScaleChange={handleScaleChange}
            loading={activityLoading}
            error={activityError}
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
