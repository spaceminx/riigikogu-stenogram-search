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

  // Local state for interactive editing of input query tokens
  const [groups, setGroups] = useState(() => parseQueryToGroups(queryParam));
  const [inputValue, setInputValue] = useState("");

  // Search results state
  const [speeches, setSpeeches] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [activity, setActivity] = useState([]);
  const [speakers, setSpeakers] = useState([]);
  const [loading, setLoading] = useState(false);
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

  const hasSearchCriteria = Boolean(
    queryParam.trim() || factionParam || speakerParam || startDateParam || endDateParam
  );

  useEffect(() => {
    if (!hasSearchCriteria) {
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
  }, [
    queryParam,
    membershipParam,
    factionParam,
    speakerParam,
    startDateParam,
    endDateParam,
    sortParam,
    intervalParam,
    pageParam,
    excludeChairParam,
    speechCategoryParam,
    hasSearchCriteria,
  ]);

  const updateUrlParams = (changes) => {
    const next = new URLSearchParams(searchParams);
    Object.entries(changes).forEach(([key, val]) => {
      if (val === null || val === undefined || val === "" || val === false) {
        next.delete(key);
      } else if (val === true) {
        next.set(key, "true");
      } else {
        next.set(key, String(val));
      }
    });
    setSearchParams(next);
  };

  const handleSearchSubmit = (e) => {
    e.preventDefault();
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

    updateUrlParams({ q: queryString || null, page: null });
  };

  const handleSortChange = (newSort) => {
    updateUrlParams({ sort: newSort === "date_desc" ? null : newSort, page: null });
  };

  const handleIntervalChange = (newInterval) => {
    updateUrlParams({ interval: newInterval === "monthly" ? null : newInterval });
  };

  const handlePageChange = (newPage) => {
    updateUrlParams({ page: newPage <= 1 ? null : newPage });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleResetFilters = () => {
    updateUrlParams({
      membership: null,
      faction: null,
      speaker: null,
      start_date: null,
      end_date: null,
      exclude_chair: null,
      speech_category: null,
      page: null,
    });
  };

  const handleOpenContext = async (speechId) => {
    try {
      const data = await fetchSpeechContext(speechId, queryParam);
      setActiveSpeechContext(data);
    } catch (err) {
      setError(err.message || "Konteksti laadimine ebaõnnestus.");
    }
  };

  const currentTotalCount = hasSearchCriteria ? totalCount : 0;
  const currentSpeeches = hasSearchCriteria ? speeches : [];
  const currentActivity = hasSearchCriteria ? activity : [];
  const currentSpeakers = hasSearchCriteria ? speakers : [];

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
        searchMembership={membershipParam}
        setSearchMembership={(m) =>
          updateUrlParams({ membership: m === "all" ? null : m, page: null })
        }
        memberships={memberships}
        searchFaction={factionParam}
        setSearchFaction={(f) => updateUrlParams({ faction: f || null, page: null })}
        searchFactionsList={searchFactionsList}
        plenaryDates={plenaryDates}
        searchDateRange={{ startDate: startDateParam, endDate: endDateParam }}
        setSearchDateRange={(range) =>
          updateUrlParams({
            start_date: range.startDate || null,
            end_date: range.endDate || null,
            page: null,
          })
        }
        searchSpeaker={speakerParam}
        setSearchSpeaker={(s) => updateUrlParams({ speaker: s || null, page: null })}
        searchSpeechCategory={speechCategoryParam}
        setSearchSpeechCategory={(c) => updateUrlParams({ speech_category: c || null, page: null })}
        searchExcludeChair={excludeChairParam}
        setSearchExcludeChair={(c) => updateUrlParams({ exclude_chair: c || null, page: null })}
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

      {currentActivity.length > 0 && (
        <div className="dashboard-grid" style={{ marginBottom: "1.5rem" }}>
          <ActivityChart
            activity={currentActivity}
            interval={intervalParam}
            onIntervalChange={handleIntervalChange}
            loading={loading}
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

        {loading ? (
          <div className="empty-state" style={{ padding: "3rem 1rem" }}>
            <p>Otsin stenogramme...</p>
          </div>
        ) : currentSpeeches.length === 0 ? (
          <div className="empty-state" style={{ padding: "3rem 1rem" }}>
            <p>Valitud filtritega kõnesid ei leitud.</p>
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
