import React, { useState, useEffect, useRef, useMemo } from "react";
import { XAxis, YAxis, Tooltip, ResponsiveContainer, AreaChart, Area } from "recharts";
import {
  fetchSearch,
  fetchActivity,
  fetchSpeakers,
  fetchSpeechContext,
  getExportUrl,
  fetchAttendance,
  fetchFactionAttendance,
  fetchFactionsList,
} from "./api";
import "./App.css";

function formatDateTime(dateStr, timeStr) {
  if (!dateStr && !timeStr) return "";
  const months = [
    "jaanuar",
    "veebruar",
    "märts",
    "aprill",
    "mai",
    "juuni",
    "juuli",
    "august",
    "september",
    "oktoober",
    "november",
    "detsember",
  ];
  let formattedDate = dateStr || "";
  try {
    if (dateStr) {
      const parts = dateStr.split("-");
      if (parts.length === 3) {
        const year = parts[0];
        const month = parseInt(parts[1], 10) - 1;
        const day = parseInt(parts[2], 10);
        formattedDate = `${day}. ${months[month]} ${year}`;
      }
    }
  } catch {
    // fallback to original dateStr if parsing fails
  }

  let formattedTime = "";
  if (timeStr) {
    if (timeStr.length === 4 && !timeStr.includes(":")) {
      formattedTime = ` kell ${timeStr.slice(0, 2)}:${timeStr.slice(2, 4)}`;
    } else {
      const tParts = timeStr.split(":");
      if (tParts.length >= 2) {
        formattedTime = ` kell ${tParts[0]}:${tParts[1]}`;
      } else {
        formattedTime = ` kell ${timeStr}`;
      }
    }
  }
  return `${formattedDate}${formattedTime}`.trim();
}

function formatFactionName(name) {
  if (!name) return "";
  const nameMap = {
    "Eesti Reformierakonna fraktsioon": "Reformierakond",
    "Eesti Keskerakonna fraktsioon": "Keskerakond",
    "Eesti Konservatiivse Rahvaerakonna fraktsioon": "EKRE",
    "Eesti 200 fraktsioon": "Eesti 200",
    "Isamaa fraktsioon": "Isamaa",
    "Sotsiaaldemokraatliku Erakonna fraktsioon": "Sotsiaaldemokraadid",
    "Fraktsiooni mittekuuluvad Riigikogu liikmed": "Fraktsiooni mittekuuluvad",
  };
  if (nameMap[name]) return nameMap[name];

  const clean = name.replace(/ fraktsioon$/i, "").replace(/ fraktsiooni$/i, "");
  const fallbackMap = {
    "Eesti Reformierakonna": "Reformierakond",
    "Eesti Reformierakond": "Reformierakond",
    "Eesti Keskerakonna": "Keskerakond",
    "Eesti Keskerakond": "Keskerakond",
    "Eesti Konservatiivse Rahvaerakonna": "EKRE",
    "Eesti Konservatiivne Rahvaerakond": "EKRE",
    "Sotsiaaldemokraatliku Erakonna": "Sotsiaaldemokraadid",
    "Sotsiaaldemokraatlik Erakond": "Sotsiaaldemokraadid",
  };
  return fallbackMap[clean] || clean;
}

function getPercentageColor(percentage) {
  if (percentage >= 75) return "#10b981"; // green
  if (percentage >= 50) return "#f59e0b"; // yellow
  return "#ef4444"; // red
}

function highlightKeywords(text, groups, extraTerm = "") {
  if (!text) return "";
  const allTerms = groups ? groups.flat().map((w) => w.trim().toLowerCase()) : [];
  if (extraTerm && extraTerm.trim().length >= 2) {
    allTerms.push(extraTerm.trim().toLowerCase());
  }
  const keywords = Array.from(new Set(allTerms.filter((w) => w.length >= 2)));
  if (keywords.length === 0) return text;
  keywords.sort((a, b) => b.length - a.length);

  const escaped = keywords.map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const regex = new RegExp(`(${escaped.join("|")})`, "gi");

  const parts = text.split(regex);
  return parts.map((part, index) => {
    const isMatch = keywords.some((k) => part.toLowerCase() === k.toLowerCase());
    return isMatch ? (
      <mark key={index} className="keyword-highlight">
        {part}
      </mark>
    ) : (
      part
    );
  });
}

function parseQueryToGroups(queryString) {
  if (!queryString || !queryString.trim()) return [[]];
  const parts = queryString
    .split(",")
    .map((p) => p.trim())
    .filter(Boolean);
  if (parts.length === 0) return [[]];
  return parts.map((part) => part.split(/\s+/).filter(Boolean));
}

function syncUrl(state) {
  const params = new URLSearchParams();
  if (state.view && state.view !== "dashboard") {
    params.set("view", state.view);
  }
  if (state.query && state.query.trim()) {
    params.set("q", state.query.trim());
  }
  if (state.membership && state.membership !== "all") {
    params.set("membership", state.membership);
  }
  if (state.faction && state.faction.trim()) {
    params.set("faction", state.faction.trim());
  }
  if (state.speaker && state.speaker.trim()) {
    params.set("speaker", state.speaker.trim());
  }
  if (state.sortBy && state.sortBy !== "date_desc") {
    params.set("sort", state.sortBy);
  }
  if (state.interval && state.interval !== "monthly") {
    params.set("interval", state.interval);
  }
  if (state.page && state.page > 1) {
    params.set("page", String(state.page));
  }
  if (state.view === "attendance") {
    if (state.attendanceTab && state.attendanceTab !== "members") {
      params.set("att_tab", state.attendanceTab);
    }
    if (state.attendanceMembership && state.attendanceMembership !== "15") {
      params.set("att_membership", state.attendanceMembership);
    }
    if (state.selectedFaction && state.selectedFaction.trim()) {
      params.set("att_faction", state.selectedFaction.trim());
    }
    if (state.activeOnly) {
      params.set("att_active", "1");
    }
  }
  const queryString = params.toString();
  const newUrl = queryString ? `?${queryString}` : window.location.pathname;
  const currentSearch = window.location.search;
  const targetSearch = queryString ? `?${queryString}` : "";
  if (currentSearch !== targetSearch) {
    window.history.replaceState(null, "", newUrl);
  }
}

function App() {
  const [groups, setGroups] = useState([[]]); // Array of arrays of strings
  const [inputValue, setInputValue] = useState("");
  const [interval, setSelectedInterval] = useState("monthly");
  const [speeches, setSpeeches] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [searchPage, setSearchPage] = useState(1);
  const searchPageSize = 50;
  const [activity, setActivity] = useState([]);
  const [speakers, setSpeakers] = useState([]);
  const [view, setView] = useState("dashboard"); // "dashboard" | "speeches" | "attendance"
  const [errorMessage, setErrorMessage] = useState(null);
  const [loading, setLoading] = useState(false);

  // Search filters state
  const [searchMembership, setSearchMembership] = useState("all"); // "all" | "15" | "14"
  const [searchFaction, setSearchFaction] = useState("");
  const [searchSpeaker, setSearchSpeaker] = useState("");
  const [searchSortBy, setSearchSortBy] = useState("date_desc"); // "date_desc" | "date_asc" | "match_count_desc"

  // Context Modal state
  const [activeSpeechContext, setActiveSpeechContext] = useState(null);
  const [contextSearchTerm, setContextSearchTerm] = useState("");
  const targetSpeechRef = useRef(null);
  const isInitialMount = useRef(true);

  // Attendance state
  const [attendanceTab, setAttendanceTab] = useState("members"); // "members" | "factions"
  const [attendanceMembership, setAttendanceMembership] = useState("15"); // "15" | "14" | "all"
  const [selectedFaction, setSelectedFaction] = useState("");
  const [activeOnly, setActiveOnly] = useState(false);
  const [attendanceStats, setAttendanceStats] = useState([]);
  const [factionStats, setFactionStats] = useState([]);
  const [factionsList, setFactionsList] = useState([]);
  const [attendanceLoading, setAttendanceLoading] = useState(false);

  const [sortConfig, setSortConfig] = useState({
    key: "present_sessions",
    direction: "descending",
  });
  const [factionSortConfig, setFactionSortConfig] = useState({
    key: "attendance_percentage",
    direction: "descending",
  });

  const totalPages = Math.max(1, Math.ceil(totalCount / searchPageSize));

  const buildBackendQuery = () => {
    let finalGroups = [...groups];
    if (inputValue.trim()) {
      finalGroups[finalGroups.length - 1] = [
        ...finalGroups[finalGroups.length - 1],
        inputValue.trim(),
      ];
    }
    finalGroups = finalGroups.filter((g) => g.length > 0);
    return finalGroups.map((g) => g.join(" ")).join(", ");
  };

  const executeSearch = async ({
    query = buildBackendQuery(),
    page = 1,
    membership = searchMembership,
    faction = searchFaction,
    speaker = searchSpeaker,
    sortBy = searchSortBy,
    intervalValue = interval,
  } = {}) => {
    if (!query) return;

    setErrorMessage(null);
    setLoading(true);

    try {
      const offset = (page - 1) * searchPageSize;
      const [searchData, activityData, speakersData] = await Promise.all([
        fetchSearch({
          query,
          limit: searchPageSize,
          offset,
          membership,
          faction: faction || null,
          speaker: speaker || null,
          sortBy,
        }),
        fetchActivity({
          query,
          interval: intervalValue,
          membership,
          faction: faction || null,
          speaker: speaker || null,
        }),
        fetchSpeakers({
          query,
          limit: 20,
          membership,
          faction: faction || null,
          speaker: speaker || null,
        }),
      ]);

      setSpeeches(searchData.results || []);
      setTotalCount(searchData.total_count || 0);
      setSearchPage(page);
      setActivity(activityData.activity || []);
      setSpeakers(speakersData.speakers || []);

      if (inputValue.trim()) {
        const newGroups = [...groups];
        newGroups[newGroups.length - 1] = [...newGroups[newGroups.length - 1], inputValue.trim()];
        setGroups(newGroups);
        setInputValue("");
      }
    } catch (error) {
      console.error("Frontend request failed:", error);
      setSpeeches([]);
      setTotalCount(0);
      setActivity([]);
      setSpeakers([]);
      setErrorMessage(
        error.message ||
          "Otsingupäring ebaõnnestus. Kontrolli, kas API server töötab aadressil http://127.0.0.1:8000."
      );
    } finally {
      setLoading(false);
    }
  };

  // Synchronize state to URL query parameters
  useEffect(() => {
    if (isInitialMount.current) return;
    const finalQuery = groups.filter((g) => g.length > 0).map((g) => g.join(" ")).join(", ");
    syncUrl({
      view,
      query: finalQuery,
      membership: searchMembership,
      faction: searchFaction,
      speaker: searchSpeaker,
      sortBy: searchSortBy,
      interval,
      page: searchPage,
      attendanceTab,
      attendanceMembership,
      selectedFaction,
      activeOnly,
    });
  }, [
    view,
    groups,
    searchMembership,
    searchFaction,
    searchSpeaker,
    searchSortBy,
    interval,
    searchPage,
    attendanceTab,
    attendanceMembership,
    selectedFaction,
    activeOnly,
  ]);

  // Read initial query params on mount and listen to browser back/forward (popstate)
  useEffect(() => {
    const applyUrlParams = () => {
      const params = new URLSearchParams(window.location.search);
      const initialView = params.get("view");
      const queryParam = params.get("q");
      const membershipParam = params.get("membership");
      const factionParam = params.get("faction");
      const speakerParam = params.get("speaker");
      const sortParam = params.get("sort");
      const intervalParam = params.get("interval");
      const pageParam = parseInt(params.get("page"), 10);

      const attTabParam = params.get("att_tab");
      const attMembershipParam = params.get("att_membership");
      const attFactionParam = params.get("att_faction");
      const attActiveParam = params.get("att_active");

      if (initialView && ["dashboard", "speeches", "attendance"].includes(initialView)) {
        setView(initialView);
      }
      if (membershipParam && ["15", "14", "all"].includes(membershipParam)) {
        setSearchMembership(membershipParam);
      }
      if (factionParam !== null) {
        setSearchFaction(factionParam);
      }
      if (speakerParam !== null) {
        setSearchSpeaker(speakerParam);
      }
      if (sortParam && ["date_desc", "date_asc", "match_count_desc"].includes(sortParam)) {
        setSearchSortBy(sortParam);
      }
      if (intervalParam && ["daily", "weekly", "monthly"].includes(intervalParam)) {
        setSelectedInterval(intervalParam);
      }
      if (attTabParam && ["members", "factions"].includes(attTabParam)) {
        setAttendanceTab(attTabParam);
      }
      if (attMembershipParam && ["15", "14", "all"].includes(attMembershipParam)) {
        setAttendanceMembership(attMembershipParam);
      }
      if (attFactionParam !== null) {
        setSelectedFaction(attFactionParam);
      }
      if (attActiveParam === "1" || attActiveParam === "true") {
        setActiveOnly(true);
      }

      if (queryParam && queryParam.trim()) {
        const parsedGroups = parseQueryToGroups(queryParam);
        setGroups(parsedGroups);
        const targetPage = Number.isInteger(pageParam) && pageParam > 0 ? pageParam : 1;
        setSearchPage(targetPage);

        executeSearch({
          query: queryParam.trim(),
          page: targetPage,
          membership: membershipParam || "all",
          faction: factionParam || "",
          speaker: speakerParam || "",
          sortBy: sortParam || "date_desc",
          intervalValue: intervalParam || "monthly",
        });
      }
    };

    applyUrlParams();
    isInitialMount.current = false;

    window.addEventListener("popstate", applyUrlParams);
    return () => window.removeEventListener("popstate", applyUrlParams);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Pre-load factions list for search dropdown
  useEffect(() => {
    async function loadFactions() {
      try {
        const list = await fetchFactionsList("all");
        if (list && list.length > 0) {
          setFactionsList(list);
        }
      } catch {
        // silent fallback
      }
    }
    loadFactions();
  }, []);

  // Handle ESC key to close context modal
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === "Escape" && activeSpeechContext) {
        setActiveSpeechContext(null);
        setContextSearchTerm("");
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [activeSpeechContext]);

  // Auto-scroll to target speech when context modal opens
  useEffect(() => {
    if (activeSpeechContext && targetSpeechRef.current) {
      setTimeout(() => {
        targetSpeechRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      }, 120);
    }
  }, [activeSpeechContext]);

  const requestSort = (key) => {
    let direction = "descending";
    if (sortConfig.key === key && sortConfig.direction === "descending") {
      direction = "ascending";
    }
    setSortConfig({ key, direction });
  };

  const requestFactionSort = (key) => {
    let direction = "descending";
    if (factionSortConfig.key === key && factionSortConfig.direction === "descending") {
      direction = "ascending";
    }
    setFactionSortConfig({ key, direction });
  };

  useEffect(() => {
    if (view !== "attendance") return;

    let isMounted = true;

    async function fetchData() {
      setAttendanceLoading(true);
      setErrorMessage(null);
      try {
        const [membersData, factionsData, listData] = await Promise.all([
          fetchAttendance({
            membership: attendanceMembership,
            faction: selectedFaction || null,
            activeOnly,
          }),
          fetchFactionAttendance({
            membership: attendanceMembership,
            activeOnly,
          }),
          fetchFactionsList(attendanceMembership),
        ]);
        if (isMounted) {
          setAttendanceStats(membersData || []);
          setFactionStats(factionsData || []);
          setFactionsList(listData || []);
        }
      } catch (error) {
        console.error("Failed to fetch attendance data:", error);
        if (isMounted) {
          setErrorMessage(
            error.message || "Kohaloleku andmete laadimine ebaõnnestus. Kontrolli serveri ühendust."
          );
        }
      } finally {
        if (isMounted) {
          setAttendanceLoading(false);
        }
      }
    }

    fetchData();

    return () => {
      isMounted = false;
    };
  }, [view, attendanceMembership, selectedFaction, activeOnly]);

  const sortedStats = useMemo(() => {
    let sortableItems = [...attendanceStats];
    if (sortConfig.key) {
      sortableItems.sort((a, b) => {
        if (a[sortConfig.key] < b[sortConfig.key]) {
          return sortConfig.direction === "ascending" ? -1 : 1;
        }
        if (a[sortConfig.key] > b[sortConfig.key]) {
          return sortConfig.direction === "ascending" ? 1 : -1;
        }
        if (sortConfig.key !== "present_sessions") {
          return b.present_sessions - a.present_sessions;
        }
        return b.attendance_percentage - a.attendance_percentage;
      });
    }
    return sortableItems;
  }, [attendanceStats, sortConfig]);

  const sortedFactionStats = useMemo(() => {
    let sortableItems = [...factionStats];
    if (factionSortConfig.key) {
      sortableItems.sort((a, b) => {
        if (a[factionSortConfig.key] < b[factionSortConfig.key]) {
          return factionSortConfig.direction === "ascending" ? -1 : 1;
        }
        if (a[factionSortConfig.key] > b[factionSortConfig.key]) {
          return factionSortConfig.direction === "ascending" ? 1 : -1;
        }
        return 0;
      });
    }
    return sortableItems;
  }, [factionStats, factionSortConfig]);

  const handleOpenAttendance = () => {
    setErrorMessage(null);
    setView("attendance");
  };

  const handleSelectFactionDrilldown = (factionName) => {
    setSelectedFaction(factionName);
    setAttendanceTab("members");
  };

  const tooltipStyle = {
    contentStyle: {
      backgroundColor: "rgba(15, 23, 42, 0.9)",
      backdropFilter: "blur(8px)",
      color: "#f8fafc",
      border: "1px solid rgba(255, 255, 255, 0.1)",
      borderRadius: "12px",
      boxShadow: "0 10px 15px -3px rgba(0, 0, 0, 0.5)",
    },
    itemStyle: { color: "#8b5cf6", fontWeight: 600 },
    labelStyle: { color: "#cbd5e1", marginBottom: "4px" },
  };

  const handleAddAnd = () => {
    if (inputValue.trim()) {
      const newGroups = [...groups];
      newGroups[newGroups.length - 1] = [...newGroups[newGroups.length - 1], inputValue.trim()];
      setGroups(newGroups);
      setInputValue("");
    }
  };

  const handleAddOr = () => {
    const newGroups = [...groups];
    if (inputValue.trim()) {
      newGroups[newGroups.length - 1] = [...newGroups[newGroups.length - 1], inputValue.trim()];
    }
    if (newGroups[newGroups.length - 1].length > 0) {
      newGroups.push([]);
    }
    setGroups(newGroups);
    setInputValue("");
  };

  const removeWord = (gIndex, wIndex) => {
    const newGroups = [...groups];
    newGroups[gIndex] = [...newGroups[gIndex]];
    newGroups[gIndex].splice(wIndex, 1);

    if (newGroups[gIndex].length === 0 && newGroups.length > 1) {
      newGroups.splice(gIndex, 1);
    }
    setGroups(newGroups);
  };

  const handleSearch = (e) => {
    e.preventDefault();
    executeSearch({ page: 1 });
  };

  const handleSortChange = async (newSort) => {
    setSearchSortBy(newSort);
    const finalQuery = buildBackendQuery();
    if (!finalQuery) return;
    setLoading(true);
    try {
      const searchData = await fetchSearch({
        query: finalQuery,
        limit: searchPageSize,
        offset: 0,
        membership: searchMembership,
        faction: searchFaction || null,
        speaker: searchSpeaker || null,
        sortBy: newSort,
      });
      setSpeeches(searchData.results || []);
      setTotalCount(searchData.total_count || 0);
      setSearchPage(1);
    } catch (error) {
      console.error("Failed to re-sort results:", error);
      setErrorMessage(error.message || "Tulemuste sorteerimine ebaõnnestus.");
    } finally {
      setLoading(false);
    }
  };

  const handlePageChange = async (newPage) => {
    if (newPage < 1 || newPage > totalPages) return;
    setLoading(true);
    try {
      const offset = (newPage - 1) * searchPageSize;
      const finalQuery = buildBackendQuery();
      const searchData = await fetchSearch({
        query: finalQuery,
        limit: searchPageSize,
        offset,
        membership: searchMembership,
        faction: searchFaction || null,
        speaker: searchSpeaker || null,
        sortBy: searchSortBy,
      });
      setSpeeches(searchData.results || []);
      setTotalCount(searchData.total_count || 0);
      setSearchPage(newPage);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (error) {
      console.error("Failed to load page:", error);
      setErrorMessage(error.message || "Lehe laadimine ebaõnnestus.");
    } finally {
      setLoading(false);
    }
  };

  const handleOpenContext = async (speechId) => {
    setErrorMessage(null);
    try {
      const data = await fetchSpeechContext(speechId);
      setActiveSpeechContext(data);
    } catch (error) {
      console.error("Failed to load transcript context:", error);
      setErrorMessage(error.message || "Istungi stenogrammi laadimine ebaõnnestus.");
    }
  };

  const handleCloseContext = () => {
    setActiveSpeechContext(null);
    setContextSearchTerm("");
  };

  const handleIntervalChange = (newInterval) => {
    setSelectedInterval(newInterval);
    const query = buildBackendQuery();
    if (query && activity.length > 0) {
      fetchActivity({
        query,
        interval: newInterval,
        membership: searchMembership,
        faction: searchFaction || null,
        speaker: searchSpeaker || null,
      })
        .then((data) => setActivity(data.activity || []))
        .catch(() => {});
    }
  };

  const handleResetFilters = () => {
    setSearchMembership("all");
    setSearchFaction("");
    setSearchSpeaker("");
  };

  const hasActiveFilters =
    searchMembership !== "all" || searchFaction !== "" || searchSpeaker.trim() !== "";

  return (
    <div className="app-container">
      <div className="header">
        <h1>
          <svg
            width="28"
            height="28"
            viewBox="0 0 24 24"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              d="M12 2L2 7L12 12L22 7L12 2Z"
              stroke="url(#paint0_linear)"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              d="M2 17L12 22L22 17"
              stroke="url(#paint1_linear)"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              d="M2 12L12 17L22 12"
              stroke="url(#paint2_linear)"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <defs>
              <linearGradient
                id="paint0_linear"
                x1="2"
                y1="7"
                x2="22"
                y2="7"
                gradientUnits="userSpaceOnUse"
              >
                <stop stopColor="#3b82f6" />
                <stop offset="1" stopColor="#8b5cf6" />
              </linearGradient>
              <linearGradient
                id="paint1_linear"
                x1="2"
                y1="19.5"
                x2="22"
                y2="19.5"
                gradientUnits="userSpaceOnUse"
              >
                <stop stopColor="#3b82f6" />
                <stop offset="1" stopColor="#8b5cf6" />
              </linearGradient>
              <linearGradient
                id="paint2_linear"
                x1="2"
                y1="14.5"
                x2="22"
                y2="14.5"
                gradientUnits="userSpaceOnUse"
              >
                <stop stopColor="#3b82f6" />
                <stop offset="1" stopColor="#8b5cf6" />
              </linearGradient>
            </defs>
          </svg>
          Riigikogu Search
        </h1>
        <div className="nav-links">
          <button
            className={`nav-btn ${view !== "attendance" ? "active" : ""}`}
            onClick={() => setView("dashboard")}
          >
            Otsing
          </button>
          <button
            className={`nav-btn ${view === "attendance" ? "active" : ""}`}
            onClick={handleOpenAttendance}
          >
            Kohalolek
          </button>
        </div>
      </div>

      {errorMessage && (
        <div className="error-banner">
          <div className="error-content">
            <span className="error-icon">!</span>
            <span>{errorMessage}</span>
          </div>
          <button
            className="error-dismiss"
            onClick={() => setErrorMessage(null)}
            title="Sulge teade"
          >
            &times;
          </button>
        </div>
      )}

      {view !== "attendance" && (
        <form onSubmit={handleSearch} className="search-section">
          <div className="search-groups-container">
            {groups.map((group, gIndex) => (
              <React.Fragment key={gIndex}>
                {gIndex > 0 && <span className="or-divider">VÕI</span>}
                <div className="and-group-box">
                  {group.map((word, wIndex) => (
                    <span key={wIndex} className="token-pill">
                      {word}
                      <button
                        type="button"
                        onClick={() => removeWord(gIndex, wIndex)}
                        title="Eemalda sõna"
                      >
                        &times;
                      </button>
                    </span>
                  ))}
                  {gIndex === groups.length - 1 && (
                    <input
                      type="text"
                      className="search-input"
                      placeholder={
                        group.length === 0 && groups.length === 1
                          ? "Sisesta otsisõna (nt kliima, mets)..."
                          : "Lisa sõna..."
                      }
                      value={inputValue}
                      onChange={(e) => setInputValue(e.target.value)}
                    />
                  )}
                </div>
              </React.Fragment>
            ))}
          </div>

          <div className="search-controls">
            <div className="logic-buttons">
              <button
                type="button"
                className="logic-btn and-btn"
                onClick={handleAddAnd}
                title="Lisa sõna samasse gruppi (mõlemad peavad esinema)"
              >
                + JA
              </button>
              <button
                type="button"
                className="logic-btn or-btn"
                onClick={handleAddOr}
                title="Alusta uut gruppi (üks või teine peab esinema)"
              >
                + VÕI
              </button>
            </div>

            <select
              className="search-select"
              value={interval}
              onChange={(e) => handleIntervalChange(e.target.value)}
            >
              <option value="monthly">Kuu kaupa</option>
              <option value="weekly">Nädala kaupa</option>
              <option value="daily">Päeva kaupa</option>
            </select>

            <button type="submit" className="search-button" disabled={loading}>
              {loading ? "Otsin..." : "Otsi"}
            </button>
          </div>

          {/* Search Filters Row */}
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
                <option value="15">XV Riigikogu (2023–praegu)</option>
                <option value="14">XIV Riigikogu (2019–2023)</option>
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
                {factionsList.map((fac, idx) => (
                  <option key={idx} value={fac}>
                    {formatFactionName(fac)}
                  </option>
                ))}
              </select>
            </div>

            <div className="filter-group-item speaker-filter-item">
              <label htmlFor="filter-speaker" className="filter-label">
                Esineja:
              </label>
              <div className="filter-input-wrap">
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

            {hasActiveFilters && (
              <button
                type="button"
                className="reset-filters-btn"
                onClick={handleResetFilters}
                title="Lähtesta koosseisu, fraktsiooni ja esineja filtrid"
              >
                Lähtesta filtrid
              </button>
            )}
          </div>
        </form>
      )}

      {view === "dashboard" && activity.length === 0 && !loading && (
        <div className="glass-panel empty-state">
          <svg
            width="48"
            height="48"
            viewBox="0 0 24 24"
            fill="none"
            stroke="#64748b"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <p>Alustamiseks sisesta märksõna ja vajuta "Otsi"</p>
        </div>
      )}

      {view === "dashboard" && activity.length > 0 && (
        <>
          <div className="dashboard-grid">
            <div className="glass-panel">
              <div className="chart-header">
                <h2>Aktiivsus ajas</h2>
              </div>
              <div style={{ width: "100%", height: 350 }}>
                <ResponsiveContainer>
                  <AreaChart data={activity} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                    <defs>
                      <linearGradient id="colorCount" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.6} />
                        <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <XAxis
                      dataKey={
                        interval === "daily" ? "date" : interval === "weekly" ? "week" : "month"
                      }
                      stroke="#4b5563"
                      tick={{ fill: "#9ca3af", fontSize: 12 }}
                      tickLine={false}
                      axisLine={false}
                    />
                    <YAxis
                      stroke="#4b5563"
                      tick={{ fill: "#9ca3af", fontSize: 12 }}
                      tickLine={false}
                      axisLine={false}
                    />
                    <Tooltip
                      {...tooltipStyle}
                      cursor={{ stroke: "rgba(255,255,255,0.1)", strokeWidth: 2 }}
                    />
                    <Area
                      type="monotone"
                      dataKey="count"
                      name="Mainimisi"
                      stroke="#8b5cf6"
                      strokeWidth={3}
                      fillOpacity={1}
                      fill="url(#colorCount)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="glass-panel">
              <div className="chart-header">
                <h2>Top kõnelejad</h2>
              </div>
              <div className="speakers-list">
                {speakers.slice(0, 8).map((sp, idx) => (
                  <div key={idx} className="speaker-item">
                    <div className="speaker-info">
                      <span className="speaker-rank">{idx + 1}</span>
                      <div style={{ display: "flex", flexDirection: "column" }}>
                        <span className="speaker-name">{sp.speaker}</span>
                      </div>
                    </div>
                    <span className="speaker-count">{sp.count}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {totalCount > 0 && (
            <div style={{ display: "flex", justifyContent: "center", marginTop: "2.5rem" }}>
              <button
                className="search-button"
                style={{ padding: "1rem 3rem", fontSize: "1.1rem" }}
                onClick={() => setView("speeches")}
              >
                Vaata leitud stenogramme ({totalCount.toLocaleString("et-EE")}) &rarr;
              </button>
            </div>
          )}
        </>
      )}

      {view === "speeches" && (
        <div className="glass-panel" style={{ marginTop: "0.5rem" }}>
          <div className="chart-header speeches-header-bar">
            <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
              <button className="back-nav-btn" onClick={() => setView("dashboard")}>
                &larr; Tagasi töölauale
              </button>
              <h2 className="speeches-view-title">
                Leitud stenogrammid
                <span className="results-badge">{totalCount.toLocaleString("et-EE")} tk</span>
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
                  value={searchSortBy}
                  onChange={(e) => handleSortChange(e.target.value)}
                >
                  <option value="date_desc">Uuemad enne</option>
                  <option value="date_asc">Vanemad enne</option>
                  <option value="match_count_desc">Märksõnade sagedus</option>
                </select>
              </div>

              <div className="export-actions-wrap">
                <span className="export-label">Eksport:</span>
                <a
                  href={getExportUrl({
                    query: buildBackendQuery(),
                    format: "csv",
                    membership: searchMembership,
                    faction: searchFaction || null,
                    speaker: searchSpeaker || null,
                    sortBy: searchSortBy,
                  })}
                  className="export-btn-link"
                  download
                  title="Laadi otsingutulemused alla CSV failina"
                >
                  CSV
                </a>
                <a
                  href={getExportUrl({
                    query: buildBackendQuery(),
                    format: "json",
                    membership: searchMembership,
                    faction: searchFaction || null,
                    speaker: searchSpeaker || null,
                    sortBy: searchSortBy,
                  })}
                  className="export-btn-link"
                  download
                  title="Laadi otsingutulemused alla JSON failina"
                >
                  JSON
                </a>
              </div>
            </div>
          </div>

          {speeches.length === 0 ? (
            <div className="empty-state" style={{ padding: "3rem 1rem" }}>
              <p>Valitud filtritega kõnesid ei leitud.</p>
            </div>
          ) : (
            <>
              <div className="speeches-list">
                {speeches.map((speech) => (
                  <div key={speech.id} className="glass-panel speech-card">
                    <div className="speech-meta">
                      <div className="speaker-header-info">
                        <span className="speaker-name-highlight">{speech.speaker}</span>
                        {speech.speaker_role && (
                          <span className="speaker-role-tag">{speech.speaker_role}</span>
                        )}
                        {speech.speaker_faction && (
                          <span className="faction-badge">
                            {formatFactionName(speech.speaker_faction)}
                          </span>
                        )}
                      </div>
                      <span className="speech-datetime">
                        {formatDateTime(speech.date, speech.time)}
                      </span>
                    </div>

                    <p className="speech-text">
                      {highlightKeywords(speech.text.slice(0, 380), groups)}...
                    </p>

                    <div className="speech-card-actions">
                      <button
                        type="button"
                        className="context-btn"
                        onClick={() => handleOpenContext(speech.id)}
                        title="Ava terve istungi ajajoon ja vaata kõnet selle loomulikus kontekstis"
                      >
                        Vaata tervet istungit ({speech.count} mainimist)
                      </button>

                      <a
                        href={speech.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="speech-link"
                      >
                        Ava allikas
                        <svg
                          width="15"
                          height="15"
                          viewBox="0 0 24 24"
                          fill="none"
                          xmlns="http://www.w3.org/2000/svg"
                          style={{ marginLeft: "4px" }}
                        >
                          <path
                            d="M7 17L17 7M17 7H7M17 7V17"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      </a>
                    </div>
                  </div>
                ))}
              </div>

              {totalPages > 1 && (
                <div className="pagination-container">
                  <button
                    type="button"
                    className="pagination-btn"
                    disabled={searchPage <= 1 || loading}
                    onClick={() => handlePageChange(searchPage - 1)}
                  >
                    &larr; Eelmine
                  </button>
                  <span className="pagination-text">
                    Lehekülg {searchPage} / {totalPages}
                  </span>
                  <button
                    type="button"
                    className="pagination-btn"
                    disabled={searchPage >= totalPages || loading}
                    onClick={() => handlePageChange(searchPage + 1)}
                  >
                    Järgmine &rarr;
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Transcript Full Context Modal */}
      {activeSpeechContext && (
        <div className="modal-backdrop" onClick={handleCloseContext}>
          <div className="modal-content glass-panel" onClick={(e) => e.stopPropagation()}>
            <div className="modal-top-bar">
              <div>
                <h2 className="modal-heading">Istungi stenogramm</h2>
                <div className="modal-meta-row">
                  <span>{formatDateTime(activeSpeechContext.date, activeSpeechContext.time)}</span>
                  <span>•</span>
                  <span>{activeSpeechContext.total_speeches} kõnet/repliiki</span>
                  <span>•</span>
                  <a
                    href={activeSpeechContext.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="modal-external-link"
                  >
                    Ametlik stenogrammid.riigikogu.ee &rarr;
                  </a>
                </div>
              </div>
              <button
                type="button"
                className="modal-close-icon-btn"
                onClick={handleCloseContext}
                title="Sulge aken (ESC)"
              >
                &times;
              </button>
            </div>

            <div className="modal-filter-box">
              <input
                type="text"
                placeholder="Filtreeri kõnesid istungi sees..."
                value={contextSearchTerm}
                onChange={(e) => setContextSearchTerm(e.target.value)}
                className="modal-search-input"
              />
            </div>

            <div className="modal-speeches-scroll">
              {activeSpeechContext.speeches
                .filter((s) => {
                  if (!contextSearchTerm.trim()) return true;
                  const term = contextSearchTerm.toLowerCase();
                  return (
                    (s.speaker && s.speaker.toLowerCase().includes(term)) ||
                    (s.text && s.text.toLowerCase().includes(term))
                  );
                })
                .map((speech) => {
                  const isTarget = speech.id === activeSpeechContext.target_speech_id;
                  return (
                    <div
                      key={speech.id}
                      ref={isTarget ? targetSpeechRef : null}
                      className={`transcript-speech-row ${isTarget ? "target-speech-highlight" : ""}`}
                    >
                      <div className="transcript-row-header">
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "0.5rem",
                            flexWrap: "wrap",
                          }}
                        >
                          <span className="transcript-row-speaker">{speech.speaker}</span>
                          {speech.speaker_role && (
                            <span className="speaker-role-tag">{speech.speaker_role}</span>
                          )}
                          {speech.speaker_faction && (
                            <span className="faction-badge">
                              {formatFactionName(speech.speaker_faction)}
                            </span>
                          )}
                          {isTarget && <span className="target-speech-badge">Otsitud kõne</span>}
                        </div>
                      </div>
                      <div className="transcript-row-text">
                        {highlightKeywords(speech.text, groups, contextSearchTerm)}
                      </div>
                    </div>
                  );
                })}
            </div>
          </div>
        </div>
      )}

      {view === "attendance" && (
        <div className="glass-panel" style={{ marginTop: "0.5rem" }}>
          <div className="chart-header" style={{ marginBottom: "1.25rem" }}>
            <h2 style={{ margin: 0 }}>
              Kohaloleku statistika{" "}
              {attendanceMembership === "15"
                ? "(XV Riigikogu, 2023–praegu)"
                : attendanceMembership === "14"
                  ? "(XIV Riigikogu, 2019–2023)"
                  : "(2019–2026)"}
            </h2>
          </div>

          <div className="attendance-filter-bar">
            <div className="segmented-control">
              <button
                type="button"
                className={`segmented-btn ${attendanceTab === "members" ? "active" : ""}`}
                onClick={() => setAttendanceTab("members")}
              >
                Saadikute vaade
              </button>
              <button
                type="button"
                className={`segmented-btn ${attendanceTab === "factions" ? "active" : ""}`}
                onClick={() => setAttendanceTab("factions")}
              >
                Fraktsioonide koond
              </button>
            </div>

            <div className="attendance-controls-row">
              <div className="attendance-select-group">
                <label htmlFor="period-select" className="attendance-label">
                  Periood:
                </label>
                <select
                  id="period-select"
                  className="attendance-select"
                  value={attendanceMembership}
                  onChange={(e) => {
                    const newPeriod = e.target.value;
                    setAttendanceMembership(newPeriod);
                    if (newPeriod !== "15") {
                      setActiveOnly(false);
                    }
                  }}
                >
                  <option value="15">XV Riigikogu (2023–praegu)</option>
                  <option value="14">XIV Riigikogu (2019–2023)</option>
                  <option value="all">Kõik kokku (2019–2026)</option>
                </select>
              </div>

              {attendanceTab === "members" && (
                <div className="attendance-select-group">
                  <label htmlFor="faction-select" className="attendance-label">
                    Fraktsioon:
                  </label>
                  <select
                    id="faction-select"
                    className="attendance-select"
                    value={selectedFaction}
                    onChange={(e) => setSelectedFaction(e.target.value)}
                  >
                    <option value="">Kõik fraktsioonid</option>
                    {factionsList.map((fac, idx) => (
                      <option key={idx} value={fac}>
                        {formatFactionName(fac)}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {attendanceMembership === "15" && (
                <label className="attendance-checkbox-label">
                  <input
                    type="checkbox"
                    checked={activeOnly}
                    onChange={(e) => setActiveOnly(e.target.checked)}
                  />
                  <span>
                    {attendanceTab === "factions"
                      ? "Ainult praegused aktiivsed saadikud (101 liiget)"
                      : "Ainult praegu aktiivsed Riigikogu liikmed (101 liiget)"}
                  </span>
                </label>
              )}
            </div>
          </div>

          {attendanceLoading ? (
            <div className="empty-state" style={{ padding: "3rem 1rem" }}>
              <p>Laadin kohaloleku andmeid...</p>
            </div>
          ) : attendanceTab === "members" ? (
            <div className="attendance-list">
              <div className="attendance-header-row">
                <div className="att-col-rank">#</div>
                <div
                  className="att-col-name cursor-pointer"
                  onClick={() => requestSort("member_name")}
                >
                  Saadik{" "}
                  {sortConfig.key === "member_name"
                    ? sortConfig.direction === "ascending"
                      ? "↑"
                      : "↓"
                    : ""}
                </div>
                <div
                  className="att-col-faction cursor-pointer"
                  onClick={() => requestSort("faction")}
                >
                  Fraktsioon{" "}
                  {sortConfig.key === "faction"
                    ? sortConfig.direction === "ascending"
                      ? "↑"
                      : "↓"
                    : ""}
                </div>
                <div
                  className="att-col-total cursor-pointer"
                  onClick={() => requestSort("total_sessions")}
                >
                  Istungeid{" "}
                  {sortConfig.key === "total_sessions"
                    ? sortConfig.direction === "ascending"
                      ? "↑"
                      : "↓"
                    : ""}
                </div>
                <div
                  className="att-col-present cursor-pointer"
                  onClick={() => requestSort("present_sessions")}
                >
                  Kohal{" "}
                  {sortConfig.key === "present_sessions"
                    ? sortConfig.direction === "ascending"
                      ? "↑"
                      : "↓"
                    : ""}
                </div>
                <div
                  className="att-col-percent cursor-pointer"
                  onClick={() => requestSort("attendance_percentage")}
                >
                  %{" "}
                  {sortConfig.key === "attendance_percentage"
                    ? sortConfig.direction === "ascending"
                      ? "↑"
                      : "↓"
                    : ""}
                </div>
              </div>

              {sortedStats.length === 0 ? (
                <p style={{ textAlign: "center", padding: "2.5rem", color: "#64748b" }}>
                  Valitud filtritele vastavaid saadikuid ei leitud.
                </p>
              ) : (
                sortedStats.map((stat, idx) => (
                  <div key={idx} className="attendance-row">
                    <div className="att-col-rank">{idx + 1}</div>
                    <div className="att-col-name">{stat.member_name}</div>
                    <div className="att-col-faction">
                      <span className="faction-badge" title={stat.faction}>
                        {formatFactionName(stat.faction)}
                      </span>
                    </div>
                    <div className="att-col-total">{stat.total_sessions}</div>
                    <div className="att-col-present">{stat.present_sessions}</div>
                    <div className="att-col-percent">
                      <div className="percent-bar-bg">
                        <div
                          className="percent-bar-fill"
                          style={{
                            width: `${stat.attendance_percentage}%`,
                            backgroundColor: getPercentageColor(stat.attendance_percentage),
                          }}
                        ></div>
                      </div>
                      <span className="percent-text">{stat.attendance_percentage}%</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          ) : (
            <div className="attendance-list">
              <div className="attendance-header-row">
                <div className="att-col-rank">#</div>
                <div
                  className="att-col-name cursor-pointer"
                  onClick={() => requestFactionSort("faction")}
                >
                  Fraktsioon{" "}
                  {factionSortConfig.key === "faction"
                    ? factionSortConfig.direction === "ascending"
                      ? "↑"
                      : "↓"
                    : ""}
                </div>
                <div
                  className="att-col-count cursor-pointer"
                  onClick={() => requestFactionSort("member_count")}
                >
                  Saadikuid{" "}
                  {factionSortConfig.key === "member_count"
                    ? factionSortConfig.direction === "ascending"
                      ? "↑"
                      : "↓"
                    : ""}
                </div>
                <div
                  className="att-col-total cursor-pointer"
                  onClick={() => requestFactionSort("total_sessions")}
                >
                  Hääletusi kokku{" "}
                  {factionSortConfig.key === "total_sessions"
                    ? factionSortConfig.direction === "ascending"
                      ? "↑"
                      : "↓"
                    : ""}
                </div>
                <div
                  className="att-col-present cursor-pointer"
                  onClick={() => requestFactionSort("present_sessions")}
                >
                  Kohal oldud{" "}
                  {factionSortConfig.key === "present_sessions"
                    ? factionSortConfig.direction === "ascending"
                      ? "↑"
                      : "↓"
                    : ""}
                </div>
                <div
                  className="att-col-percent cursor-pointer"
                  onClick={() => requestFactionSort("attendance_percentage")}
                >
                  Keskmine kohalolek %{" "}
                  {factionSortConfig.key === "attendance_percentage"
                    ? factionSortConfig.direction === "ascending"
                      ? "↑"
                      : "↓"
                    : ""}
                </div>
              </div>

              {sortedFactionStats.length === 0 ? (
                <p style={{ textAlign: "center", padding: "2.5rem", color: "#64748b" }}>
                  Fraktsioonide andmeid ei leitud.
                </p>
              ) : (
                sortedFactionStats.map((stat, idx) => (
                  <div
                    key={idx}
                    className="attendance-row faction-row-interactive"
                    onClick={() => handleSelectFactionDrilldown(stat.faction)}
                    title={`Klõpsa, et vaadata ${stat.faction} saadikuid`}
                  >
                    <div className="att-col-rank">{idx + 1}</div>
                    <div className="att-col-name">
                      <span className="faction-title">{formatFactionName(stat.faction)}</span>
                      <span className="drilldown-hint">Vaata saadikuid &rarr;</span>
                    </div>
                    <div className="att-col-count">{stat.member_count}</div>
                    <div className="att-col-total">{stat.total_sessions}</div>
                    <div className="att-col-present">{stat.present_sessions}</div>
                    <div className="att-col-percent">
                      <div className="percent-bar-bg">
                        <div
                          className="percent-bar-fill"
                          style={{
                            width: `${stat.attendance_percentage}%`,
                            backgroundColor: getPercentageColor(stat.attendance_percentage),
                          }}
                        ></div>
                      </div>
                      <span className="percent-text">{stat.attendance_percentage}%</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default App;
