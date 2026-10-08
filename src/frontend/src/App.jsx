import React, { useState, useEffect, useRef, useMemo } from "react";
import {
  Activity,
  CalendarDays,
  Database,
  ExternalLink,
  Landmark,
  Menu,
  Moon,
  Search,
  Sun,
  Video,
} from "lucide-react";
import useSWR from "swr";
import { fetchDashboardOverview, fetchPlenarySession, fetchPlenarySessionDates } from "./api";
import DateRangeCalendar from "./DateRangeCalendar";
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

function normalizeSourceUrl(url) {
  if (!url) return url;
  return url.replace(
    /^https?:\/\/stenogrammid\.riigikogu\.ee\/(?!et\/|en\/|ru\/)(\d{12})(.*)$/,
    "https://stenogrammid.riigikogu.ee/et/$1$2"
  );
}

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

function highlightKeywords(text, groups, extraTerm = "", matchedWords = []) {
  if (!text) return "";
  const allTerms = groups ? groups.flat().map((w) => w.trim().toLowerCase()) : [];
  if (extraTerm && extraTerm.trim().length >= 2) {
    allTerms.push(extraTerm.trim().toLowerCase());
  }
  if (matchedWords && Array.isArray(matchedWords)) {
    matchedWords.forEach((w) => {
      if (w && w.trim().length >= 2) {
        allTerms.push(w.trim().toLowerCase());
      }
    });
  }
  const keywords = Array.from(new Set(allTerms.filter((w) => w.length >= 2)));
  if (keywords.length === 0) return text;
  keywords.sort((a, b) => b.length - a.length);

  const escaped = keywords.map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const regex = new RegExp(
    `(?<=[^\\p{L}\\p{N}]|^)(${escaped.join("|")})(?=[^\\p{L}\\p{N}]|$)`,
    "gui"
  );

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

function getSnippet(text, matchedWords = [], groups = [[]], maxLength = 380) {
  if (!text) return "";
  if (text.length <= maxLength) return text;

  const terms = [
    ...(Array.isArray(matchedWords) ? matchedWords : []),
    ...(Array.isArray(groups) ? groups.flat() : []),
  ]
    .map((w) => (typeof w === "string" ? w.trim().toLowerCase() : ""))
    .filter((w) => w.length >= 2);

  let firstIndex = -1;
  const lowerText = text.toLowerCase();
  for (const term of terms) {
    const idx = lowerText.indexOf(term);
    if (idx !== -1 && (firstIndex === -1 || idx < firstIndex)) {
      firstIndex = idx;
    }
  }

  if (firstIndex === -1 || firstIndex < 120) {
    return text.slice(0, maxLength).trim() + "...";
  }

  const start = Math.max(0, firstIndex - 100);
  const end = Math.min(text.length, start + maxLength);
  const prefix = start > 0 ? "..." : "";
  const suffix = end < text.length ? "..." : "";
  return prefix + text.slice(start, end).trim() + suffix;
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
  if (state.startDate) {
    params.set("start_date", state.startDate);
  }
  if (state.endDate) {
    params.set("end_date", state.endDate);
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
  const [theme, setTheme] = useState("light");
  const {
    data: dashboardOverview,
    error: overviewError,
    isLoading: overviewLoading,
  } = useSWR("dashboard-overview", fetchDashboardOverview, {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });
  const { data: plenaryDatesData } = useSWR("plenary-session-dates", fetchPlenarySessionDates, {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });
  const plenaryDates = plenaryDatesData?.dates || [];

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  // Search filters state
  const [searchMembership, setSearchMembership] = useState("all"); // "all" | "15" | "14"
  const [searchFaction, setSearchFaction] = useState("");
  const [searchSpeaker, setSearchSpeaker] = useState("");
  const [searchDateRange, setSearchDateRange] = useState({ startDate: "", endDate: "" });
  const [isSessionBrowseMode, setIsSessionBrowseMode] = useState(false);
  const [selectedSessionDate, setSelectedSessionDate] = useState("");
  const [searchSortBy, setSearchSortBy] = useState("date_desc"); // "date_desc" | "date_asc" | "match_count_desc"

  // Context Modal state
  const [activeSpeechContext, setActiveSpeechContext] = useState(null);
  const [contextSearchTerm, setContextSearchTerm] = useState("");
  const targetSpeechRef = useRef(null);
  const isInitialMount = useRef(true);
  const [lastExecutedSearch, setLastExecutedSearch] = useState(null);
  const searchAbortRef = useRef(null);
  const searchRequestIdRef = useRef(0);

  // Attendance state
  const [attendanceTab, setAttendanceTab] = useState("members"); // "members" | "factions"
  const [attendanceMembership, setAttendanceMembership] = useState("15"); // "15" | "14" | "all"
  const [selectedFaction, setSelectedFaction] = useState("");
  const [activeOnly, setActiveOnly] = useState(false);
  const [attendanceStats, setAttendanceStats] = useState([]);
  const [factionStats, setFactionStats] = useState([]);
  const [searchFactionsList, setSearchFactionsList] = useState([]);
  const [attendanceFactionsList, setAttendanceFactionsList] = useState([]);
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
    startDate = searchDateRange.startDate,
    endDate = searchDateRange.endDate,
  } = {}) => {
    if (!query) return;

    if (searchAbortRef.current) {
      searchAbortRef.current.abort();
    }
    const abortController = new AbortController();
    searchAbortRef.current = abortController;
    const currentRequestId = ++searchRequestIdRef.current;

    setErrorMessage(null);
    setIsSessionBrowseMode(false);
    setSelectedSessionDate("");
    setLoading(true);

    try {
      const offset = (page - 1) * searchPageSize;
      const [searchData, activityData, speakersData] = await Promise.all([
        fetchSearch(
          {
            query,
            limit: searchPageSize,
            offset,
            membership,
            faction: faction || null,
            speaker: speaker || null,
            startDate: startDate || null,
            endDate: endDate || null,
            sortBy,
          },
          abortController.signal
        ),
        fetchActivity(
          {
            query,
            interval: intervalValue,
            membership,
            faction: faction || null,
            speaker: speaker || null,
            startDate: startDate || null,
            endDate: endDate || null,
          },
          "monthly",
          abortController.signal
        ),
        fetchSpeakers(
          {
            query,
            limit: 20,
            membership,
            faction: faction || null,
            speaker: speaker || null,
            startDate: startDate || null,
            endDate: endDate || null,
          },
          20,
          abortController.signal
        ),
      ]);

      if (currentRequestId !== searchRequestIdRef.current) return;

      setSpeeches(searchData.results || []);
      setTotalCount(searchData.total_count || 0);
      setSearchPage(page);
      setActivity(activityData.activity || []);
      setSpeakers(speakersData.speakers || []);
      setLastExecutedSearch({
        query,
        membership,
        faction,
        speaker,
        sortBy,
        startDate,
        endDate,
      });

      if (inputValue.trim()) {
        const newGroups = [...groups];
        newGroups[newGroups.length - 1] = [...newGroups[newGroups.length - 1], inputValue.trim()];
        setGroups(newGroups);
        setInputValue("");
      }
    } catch (error) {
      if (error.name === "AbortError") return;
      if (currentRequestId !== searchRequestIdRef.current) return;
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
      if (currentRequestId === searchRequestIdRef.current) {
        setLoading(false);
      }
    }
  };

  const handlePlenaryDateSelect = async (date) => {
    setSearchDateRange({ startDate: date, endDate: date });
    setSelectedSessionDate(date);
    setIsSessionBrowseMode(true);
    setView("speeches");
    setErrorMessage(null);
    setLoading(true);
    try {
      const sessionData = await fetchPlenarySession(date);
      setSpeeches(sessionData.results || []);
      setTotalCount(sessionData.count || 0);
      setSearchPage(1);
      setActivity([]);
      setSpeakers([]);
    } catch (error) {
      setSpeeches([]);
      setTotalCount(0);
      setErrorMessage(error.message || "Istungi stenogrammi laadimine ebaõnnestus.");
    } finally {
      setLoading(false);
    }
  };

  // Synchronize state to URL query parameters
  useEffect(() => {
    if (isInitialMount.current) return;
    const finalQuery = groups
      .filter((g) => g.length > 0)
      .map((g) => g.join(" "))
      .join(", ");
    syncUrl({
      view,
      query: isSessionBrowseMode ? "" : finalQuery,
      membership: searchMembership,
      faction: searchFaction,
      speaker: searchSpeaker,
      startDate: searchDateRange.startDate,
      endDate: searchDateRange.endDate,
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
    searchDateRange,
    isSessionBrowseMode,
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
      const startDateParam = params.get("start_date");
      const endDateParam = params.get("end_date");
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
      if (startDateParam || endDateParam) {
        setSearchDateRange({ startDate: startDateParam || "", endDate: endDateParam || "" });
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
          startDate: startDateParam || "",
          endDate: endDateParam || "",
          sortBy: sortParam || "date_desc",
          intervalValue: intervalParam || "monthly",
        });
      } else if (initialView === "speeches" && startDateParam && startDateParam === endDateParam) {
        handlePlenaryDateSelect(startDateParam);
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
          setSearchFactionsList(list);
          setAttendanceFactionsList(list);
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
          setAttendanceFactionsList(listData || []);
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
      backgroundColor: theme === "dark" ? "#1e293b" : "#ffffff",
      color: theme === "dark" ? "#f1f5f9" : "#25364a",
      border: `1px solid ${theme === "dark" ? "#334155" : "#cbd3dc"}`,
      borderRadius: "4px",
      boxShadow: "0 2px 8px rgba(0, 0, 0, 0.2)",
    },
    itemStyle: { color: theme === "dark" ? "#60a5fa" : "#315b84", fontWeight: 600 },
    labelStyle: { color: theme === "dark" ? "#94a3b8" : "#536477", marginBottom: "4px" },
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
    const searchParams = lastExecutedSearch || {
      query: buildBackendQuery(),
      membership: searchMembership,
      faction: searchFaction,
      speaker: searchSpeaker,
      startDate: searchDateRange.startDate,
      endDate: searchDateRange.endDate,
    };
    if (!searchParams.query) return;

    if (searchAbortRef.current) {
      searchAbortRef.current.abort();
    }
    const abortController = new AbortController();
    searchAbortRef.current = abortController;
    const currentRequestId = ++searchRequestIdRef.current;

    setLoading(true);
    try {
      const searchData = await fetchSearch(
        {
          query: searchParams.query,
          limit: searchPageSize,
          offset: 0,
          membership: searchParams.membership,
          faction: searchParams.faction || null,
          speaker: searchParams.speaker || null,
          startDate: searchParams.startDate || null,
          endDate: searchParams.endDate || null,
          sortBy: newSort,
        },
        abortController.signal
      );
      if (currentRequestId !== searchRequestIdRef.current) return;
      setSpeeches(searchData.results || []);
      setTotalCount(searchData.total_count || 0);
      setSearchPage(1);
      setLastExecutedSearch((prev) => (prev ? { ...prev, sortBy: newSort } : null));
    } catch (error) {
      if (error.name === "AbortError") return;
      if (currentRequestId !== searchRequestIdRef.current) return;
      console.error("Failed to re-sort results:", error);
      setErrorMessage(error.message || "Tulemuste sorteerimine ebaõnnestus.");
    } finally {
      if (currentRequestId === searchRequestIdRef.current) {
        setLoading(false);
      }
    }
  };

  const handlePageChange = async (newPage) => {
    if (newPage < 1 || newPage > totalPages) return;
    const searchParams = lastExecutedSearch || {
      query: buildBackendQuery(),
      membership: searchMembership,
      faction: searchFaction,
      speaker: searchSpeaker,
      startDate: searchDateRange.startDate,
      endDate: searchDateRange.endDate,
      sortBy: searchSortBy,
    };
    if (!searchParams.query) return;

    if (searchAbortRef.current) {
      searchAbortRef.current.abort();
    }
    const abortController = new AbortController();
    searchAbortRef.current = abortController;
    const currentRequestId = ++searchRequestIdRef.current;

    setLoading(true);
    try {
      const offset = (newPage - 1) * searchPageSize;
      const searchData = await fetchSearch(
        {
          query: searchParams.query,
          limit: searchPageSize,
          offset,
          membership: searchParams.membership,
          faction: searchParams.faction || null,
          speaker: searchParams.speaker || null,
          startDate: searchParams.startDate || null,
          endDate: searchParams.endDate || null,
          sortBy: searchParams.sortBy,
        },
        abortController.signal
      );
      if (currentRequestId !== searchRequestIdRef.current) return;
      setSpeeches(searchData.results || []);
      setTotalCount(searchData.total_count || 0);
      setSearchPage(newPage);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (error) {
      if (error.name === "AbortError") return;
      if (currentRequestId !== searchRequestIdRef.current) return;
      console.error("Failed to load page:", error);
      setErrorMessage(error.message || "Lehe laadimine ebaõnnestus.");
    } finally {
      if (currentRequestId === searchRequestIdRef.current) {
        setLoading(false);
      }
    }
  };

  const handleOpenContext = async (speechId) => {
    setErrorMessage(null);
    try {
      const query = lastExecutedSearch ? lastExecutedSearch.query : buildBackendQuery();
      const data = await fetchSpeechContext(speechId, query || null);
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
        startDate: searchDateRange.startDate || null,
        endDate: searchDateRange.endDate || null,
      })
        .then((data) => setActivity(data.activity || []))
        .catch(() => {});
    }
  };

  const handleResetFilters = () => {
    setSearchMembership("all");
    setSearchFaction("");
    setSearchSpeaker("");
    setSearchDateRange({ startDate: "", endDate: "" });
    setIsSessionBrowseMode(false);
    setSelectedSessionDate("");
  };

  const hasActiveFilters =
    searchMembership !== "all" ||
    searchFaction !== "" ||
    searchSpeaker.trim() !== "" ||
    Boolean(searchDateRange.startDate || searchDateRange.endDate);
  const showingArchiveSpeakers = speakers.length === 0;
  const sidebarSpeakers = showingArchiveSpeakers
    ? dashboardOverview?.speakers || []
    : speakers.slice(0, 4);
  const recentSessions = dashboardOverview?.sessions || [];

  return (
    <div className="app-container">
      <header className="header">
        <a className="brand-lockup" href="/" aria-label="Riigikogu andmevaade">
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 32 32" fill="none">
              <path d="M5 11.5 16 5l11 6.5-11 6.3L5 11.5Z" />
              <path d="m5 16 11 6.4L27 16M5 20.5l11 6.4 11-6.4" />
            </svg>
          </span>
          <span className="brand-copy">
            <strong>Riigikogu</strong>
            <span>Kõned ja andmed</span>
          </span>
        </a>
        <nav className="nav-links" aria-label="Põhinavigatsioon">
          <button
            className={`nav-btn ${view !== "attendance" ? "active" : ""}`}
            onClick={() => setView("dashboard")}
            aria-current={view !== "attendance" ? "page" : undefined}
          >
            Kõneotsing
          </button>
          <button
            className={`nav-btn ${view === "attendance" ? "active" : ""}`}
            onClick={handleOpenAttendance}
            aria-current={view === "attendance" ? "page" : undefined}
          >
            Kohalolek
          </button>
        </nav>
        <details className="header-menu">
          <summary className="header-menu-trigger" aria-label="Ava andmevaate menüü">
            <Menu aria-hidden="true" />
            <span>Menüü</span>
          </summary>
          <div className="header-menu-panel">
            <div className="menu-section-label">Välimus</div>
            <button
              type="button"
              className="menu-action"
              aria-pressed={theme === "dark"}
              onClick={() => setTheme((current) => (current === "dark" ? "light" : "dark"))}
            >
              {theme === "dark" ? <Sun aria-hidden="true" /> : <Moon aria-hidden="true" />}
              <span>{theme === "dark" ? "Hele kujundus" : "Tume kujundus"}</span>
            </button>
            <div className="menu-divider" />
            <div className="menu-section-label">Andmed ja teenused</div>
            <div className="menu-status-row">
              <Database aria-hidden="true" />
              <span>Arhiiv</span>
              <span className={`menu-status ${overviewError ? "is-offline" : ""}`}>
                <i />
                {overviewError ? "Pole ühendust" : overviewLoading ? "Ühendun…" : "Valmis"}
              </span>
            </div>
            <div className="menu-status-row">
              <Activity aria-hidden="true" />
              <span>API olek</span>
              <span className={`menu-status ${overviewError ? "is-offline" : ""}`}>
                <i />
                {overviewError ? "Pole saadaval" : overviewLoading ? "Kontrollin…" : "Aktiivne"}
              </span>
            </div>
            <div className="menu-divider" />
            <a
              className="menu-link"
              href="https://www.riigikogu.ee/"
              target="_blank"
              rel="noreferrer"
            >
              <Landmark aria-hidden="true" />
              <span>Riigikogu ametlik arhiiv</span>
              <ExternalLink aria-hidden="true" />
            </a>
            <a
              className="menu-link"
              href="https://github.com/spaceminx/riigikogu-stenogram-search"
              target="_blank"
              rel="noreferrer"
            >
              <span className="github-mark" aria-hidden="true">
                GH
              </span>
              <span>Lähtekood GitHubis</span>
              <ExternalLink aria-hidden="true" />
            </a>
          </div>
        </details>
      </header>

      <div className="page-titlebar">
        <h1>
          {view === "attendance"
            ? "Kohaloleku andmed"
            : view === "speeches"
              ? "Otsingutulemused"
              : "Kõnede analüüs"}
        </h1>
        <span>Riigikogu stenogrammid · XV ja XIV koosseis</span>
      </div>

      {view === "dashboard" && (
        <div className="archive-stats-row" aria-label="Riigikogu arhiivi kokkuvõte">
          <span className="archive-stat">120 000+ kõnet</span>
          <span className="archive-stat-separator" aria-hidden="true">
            •
          </span>
          <span className="archive-stat">101 saadikut</span>
          <span className="archive-stat-separator" aria-hidden="true">
            •
          </span>
          <span className="archive-stat">XIV ja XV koosseis</span>
        </div>
      )}

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
          <div className="search-query-row">
            <div
              className="search-groups-container"
              onClick={(e) => {
                if (!e.target.closest("button") && !e.target.classList.contains("search-input")) {
                  const input = e.currentTarget.querySelector(".search-input");
                  if (input) input.focus();
                }
              }}
            >
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
                            ? "Sisesta otsisõna (nt kliima, mets, eelarve)..."
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
            <div className="logic-buttons" aria-label="Otsingutingimuste loogika">
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
          </div>

          <div className="search-controls">
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
                {searchFactionsList.map((fac, idx) => (
                  <option key={idx} value={fac}>
                    {formatFactionName(fac)}
                  </option>
                ))}
              </select>
            </div>

            <DateRangeCalendar
              dates={plenaryDates}
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

            {hasActiveFilters && (
              <button
                type="button"
                className="reset-filters-btn"
                onClick={handleResetFilters}
                title="Lähtesta kõik otsingufiltrid"
              >
                Lähtesta filtrid
              </button>
            )}
          </div>
        </form>
      )}

      {view === "dashboard" && (
        <>
          <section className="topic-suggestions" aria-label="Populaarsed otsinguteemad">
            <span className="topic-suggestions-label">Populaarsed teemad</span>
            {[
              "Kaitsekulud",
              "Riigieelarve",
              "Maksupoliitika",
              "Õpetajate palgad",
              "Energeetika",
            ].map((topic) => (
              <button
                className="topic-pill"
                key={topic}
                type="button"
                onClick={() => {
                  setGroups([[topic]]);
                  setInputValue("");
                  executeSearch({ query: topic, page: 1 });
                }}
              >
                {topic}
              </button>
            ))}
          </section>

          <div className="dashboard-grid">
            <section className="glass-panel timeline-panel" aria-labelledby="timeline-title">
              <div className="chart-header">
                <div>
                  <span className="section-kicker">TEEMA LÄBI AJA</span>
                  <h2 id="timeline-title">Kõnede ajajoon</h2>
                </div>
                <div className="timeline-header-controls">
                  {activity.length > 0 && (
                    <span className="chart-period">{activity.length} perioodi</span>
                  )}
                  <div className="interval-segmented" role="group" aria-label="Ajajoone ajavahemik">
                    {[
                      ["daily", "Päev"],
                      ["weekly", "Nädal"],
                      ["monthly", "Kuu"],
                    ].map(([value, label]) => (
                      <button
                        key={value}
                        type="button"
                        className={`interval-segment${interval === value ? " is-active" : ""}`}
                        aria-pressed={interval === value}
                        onClick={() => handleIntervalChange(value)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
              {activity.length > 0 ? (
                <div className="timeline-chart">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={activity} margin={{ top: 12, right: 8, left: -20, bottom: 0 }}>
                      <defs>
                        <linearGradient id="colorCount" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#315b84" stopOpacity={0.16} />
                          <stop offset="95%" stopColor="#315b84" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <XAxis
                        dataKey={
                          interval === "daily" ? "date" : interval === "weekly" ? "week" : "month"
                        }
                        stroke="#cbd3dc"
                        tick={{ fill: "#64748b", fontSize: 11 }}
                        tickLine={false}
                        axisLine={false}
                        minTickGap={24}
                      />
                      <YAxis
                        stroke="#cbd3dc"
                        tick={{ fill: "#64748b", fontSize: 11 }}
                        tickLine={false}
                        axisLine={false}
                      />
                      <Tooltip {...tooltipStyle} cursor={{ stroke: "#9eabb9", strokeWidth: 1 }} />
                      <Area
                        type="monotone"
                        dataKey="count"
                        name="Kõnesid"
                        stroke="#315b84"
                        strokeWidth={2}
                        fillOpacity={1}
                        fill="url(#colorCount)"
                        activeDot={{ r: 4, fill: "#315b84", stroke: "#ffffff", strokeWidth: 2 }}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              ) : loading ? (
                <div className="chart-empty-state" role="status">
                  Laen arutelude andmeid…
                </div>
              ) : (
                <div className="sample-preview">
                  <div className="sample-preview-header">
                    <div>
                      <span className="sample-preview-kicker">ARHIIVI NÄIDIS</span>
                      <strong>Teemade aktiivsus ajas</strong>
                    </div>
                    <span className="sample-badge">Illustratiivne</span>
                  </div>
                  <div
                    className="timeline-chart sample-chart"
                    aria-label="Illustratiivne kõnede ajajoon"
                  >
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart
                        data={[
                          { month: "jaan", count: 14 },
                          { month: "veebr", count: 22 },
                          { month: "märts", count: 18 },
                          { month: "apr", count: 34 },
                          { month: "mai", count: 27 },
                          { month: "juuni", count: 42 },
                          { month: "juuli", count: 31 },
                          { month: "aug", count: 48 },
                          { month: "sept", count: 39 },
                          { month: "okt", count: 58 },
                          { month: "nov", count: 46 },
                          { month: "dets", count: 63 },
                        ]}
                        margin={{ top: 8, right: 8, left: -20, bottom: 0 }}
                      >
                        <defs>
                          <linearGradient id="sampleArea" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#315b84" stopOpacity={0.14} />
                            <stop offset="95%" stopColor="#315b84" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <XAxis
                          dataKey="month"
                          stroke="#d4dce5"
                          tick={{ fill: "#738195", fontSize: 10 }}
                          tickLine={false}
                          axisLine={false}
                        />
                        <YAxis hide />
                        <Area
                          type="monotone"
                          dataKey="count"
                          stroke="#315b84"
                          strokeWidth={2}
                          fill="url(#sampleArea)"
                          dot={false}
                          isAnimationActive={false}
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                  <p>
                    Graafik kuvab näidisandmeid. Sisesta märksõna, et vaadata arhiivi tegelikke
                    tulemusi.
                  </p>
                </div>
              )}
              <div className="chart-footer">
                <span className="legend-dot" /> Kõnede arv valitud perioodis
              </div>
            </section>

            <aside className="dashboard-rail">
              <section className="glass-panel members-panel" aria-labelledby="members-title">
                <div className="chart-header">
                  <div>
                    <span className="section-kicker">ARUTELUDE PÕHJAL</span>
                    <h2 id="members-title">Aktiivseimad kõnelejad</h2>
                  </div>
                  <span className="member-total">{sidebarSpeakers.length || "—"}</span>
                </div>
                {sidebarSpeakers.length > 0 ? (
                  <div className="speakers-list">
                    {sidebarSpeakers.map((sp, idx) => {
                      const initials = (sp.speaker || "?")
                        .split(/\s+/)
                        .slice(0, 2)
                        .map((part) => part[0])
                        .join("")
                        .toUpperCase();
                      const maxCount = Math.max(
                        ...sidebarSpeakers.map((speaker) => Number(speaker.count || 0)),
                        1
                      );
                      return (
                        <article key={`${sp.speaker}-${idx}`} className="speaker-item profile-card">
                          <span className={`profile-avatar avatar-${idx % 5}`} aria-hidden="true">
                            {initials}
                          </span>
                          <div className="profile-details">
                            <strong className="speaker-name">{sp.speaker}</strong>
                            {sp.faction && (
                              <span className="faction-badge">{formatFactionName(sp.faction)}</span>
                            )}
                            <span className="speaker-count-caption">
                              {Number(sp.count || 0).toLocaleString("et-EE")}{" "}
                              {showingArchiveSpeakers ? "kõnet" : "teemakohast mainimist"}
                            </span>
                            <span className="profile-meter">
                              <i
                                style={{
                                  width: `${Math.max(8, (Number(sp.count || 0) / maxCount) * 100)}%`,
                                }}
                              />
                            </span>
                          </div>
                          <span className="profile-rank">{String(idx + 1).padStart(2, "0")}</span>
                        </article>
                      );
                    })}
                  </div>
                ) : (
                  <p className="sidebar-empty-state">
                    {overviewError
                      ? "Kõnelejate koondandmed pole praegu kättesaadavad."
                      : "Kõnelejate andmed laaditakse arhiivist."}
                  </p>
                )}
              </section>

              <section className="glass-panel sessions-card" aria-labelledby="sessions-title">
                <div className="chart-header">
                  <div>
                    <span className="section-kicker">ARHIIVI VÄRSKEIMAD</span>
                    <h2 id="sessions-title">Viimased istungid</h2>
                  </div>
                  <CalendarDays className="sessions-heading-icon" aria-hidden="true" />
                </div>
                {recentSessions.length > 0 ? (
                  <div className="sessions-list">
                    {recentSessions.slice(0, 3).map((session, idx) => (
                      <article className="session-item" key={`${session.date}-${idx}`}>
                        <span className="session-marker" aria-hidden="true" />
                        <div className="session-content">
                          <strong>{formatDateTime(session.date)}</strong>
                          <div className="session-topics">
                            {(session.topics || []).slice(0, 3).map((topic) => (
                              <span className="session-topic" key={topic}>
                                {topic}
                              </span>
                            ))}
                            {session.source_url && (
                              <a
                                className="session-source-link"
                                href={normalizeSourceUrl(session.source_url)}
                                target="_blank"
                                rel="noreferrer"
                                aria-label="Ava istungi allikas"
                              >
                                <ExternalLink aria-hidden="true" />
                              </a>
                            )}
                          </div>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <p className="sidebar-empty-state">
                    {overviewError
                      ? "Istungite andmed pole praegu kättesaadavad."
                      : "Värskeimad istungid laaditakse arhiivist."}
                  </p>
                )}
                <DateRangeCalendar
                  compact
                  dates={plenaryDates}
                  value={searchDateRange}
                  onChange={setSearchDateRange}
                  onSelectDate={handlePlenaryDateSelect}
                />
              </section>
            </aside>
          </div>

          {totalCount > 0 && (
            <div className="results-cta-wrap">
              <button className="search-button results-cta" onClick={() => setView("speeches")}>
                Vaata kõiki {totalCount.toLocaleString("et-EE")} stenogramme{" "}
                <span aria-hidden="true">→</span>
              </button>
            </div>
          )}
        </>
      )}

      {view === "speeches" && (
        <div className="glass-panel" style={{ marginTop: "0.5rem" }}>
          <div className="chart-header speeches-header-bar">
            <div className="speeches-header-heading">
              <button className="back-nav-btn" onClick={() => setView("dashboard")}>
                &larr; Tagasi töölauale
              </button>
              <h2 className="speeches-view-title">
                {isSessionBrowseMode
                  ? `Istungi kõned · ${formatDateTime(selectedSessionDate)}`
                  : "Leitud stenogrammid"}
                <span className="results-badge">{totalCount.toLocaleString("et-EE")} tk</span>
              </h2>
            </div>

            {!isSessionBrowseMode && (
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
                      ...(lastExecutedSearch || {
                        query: buildBackendQuery(),
                        membership: searchMembership,
                        faction: searchFaction || null,
                        speaker: searchSpeaker || null,
                        startDate: searchDateRange.startDate || null,
                        endDate: searchDateRange.endDate || null,
                        sortBy: searchSortBy,
                      }),
                      format: "csv",
                    })}
                    className="export-btn-link"
                    download
                    title={
                      totalCount > 2000
                        ? `Laadi esimesed 2000 tulemust alla CSV failina (kokku ${totalCount.toLocaleString("et-EE")})`
                        : "Laadi otsingutulemused alla CSV failina"
                    }
                  >
                    CSV
                  </a>
                  <a
                    href={getExportUrl({
                      ...(lastExecutedSearch || {
                        query: buildBackendQuery(),
                        membership: searchMembership,
                        faction: searchFaction || null,
                        speaker: searchSpeaker || null,
                        startDate: searchDateRange.startDate || null,
                        endDate: searchDateRange.endDate || null,
                        sortBy: searchSortBy,
                      }),
                      format: "json",
                    })}
                    className="export-btn-link"
                    download
                    title={
                      totalCount > 2000
                        ? `Laadi esimesed 2000 tulemust alla JSON failina (kokku ${totalCount.toLocaleString("et-EE")})`
                        : "Laadi otsingutulemused alla JSON failina"
                    }
                  >
                    JSON
                  </a>
                  {totalCount > 2000 && (
                    <span
                      className="export-limit-hint"
                      style={{ fontSize: "0.8rem", color: "var(--color-text-muted, #888)", marginLeft: "0.25rem" }}
                      title={`Kokku leiti ${totalCount.toLocaleString("et-EE")} tulemust, fail sisaldab esimesed 2000.`}
                    >
                      (max 2000)
                    </span>
                  )}
                </div>
              </div>
            )}
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

                    {speech.agenda_title && (
                      <div className="speech-agenda-tag" title={speech.agenda_title}>
                        <span className="agenda-kicker">Päevakord:</span>
                        <span className="agenda-title-text">{speech.agenda_title}</span>
                      </div>
                    )}

                    <p className="speech-text">
                      {highlightKeywords(
                        getSnippet(
                          speech.text,
                          speech.matched_words,
                          isSessionBrowseMode ? [[]] : groups
                        ),
                        isSessionBrowseMode ? [[]] : groups,
                        "",
                        speech.matched_words
                      )}
                    </p>

                    <div className="speech-card-actions">
                      <button
                        type="button"
                        className="context-btn"
                        onClick={() => handleOpenContext(speech.id)}
                        title="Ava terve istungi ajajoon ja vaata kõnet selle loomulikus kontekstis"
                      >
                        {isSessionBrowseMode
                          ? "Vaata kõne konteksti"
                          : `Vaata tervet istungit (${speech.count} mainimist)`}
                      </button>

                      <div className="speech-card-links">
                        {speech.video_url && (
                          <a
                            href={speech.video_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="speech-video-link"
                            title="Vaata kõnet YouTube'is alates kõne algusest"
                          >
                            <Video size={14} aria-hidden="true" />
                            <span>Vaata videot</span>
                          </a>
                        )}

                        <a
                          href={normalizeSourceUrl(speech.source_url)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="speech-link"
                        >
                          <span>Ava allikas</span>
                          <ExternalLink size={14} aria-hidden="true" />
                        </a>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {!isSessionBrowseMode && totalPages > 1 && (
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
          <div
            className="modal-content glass-panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="transcript-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-top-bar">
              <div>
                <h2 id="transcript-modal-title" className="modal-heading">
                  Istungi stenogramm
                </h2>
                <div className="modal-meta-row">
                  <span>{formatDateTime(activeSpeechContext.date, activeSpeechContext.time)}</span>
                  <span>•</span>
                  <span>{activeSpeechContext.total_speeches} kõnet/repliiki</span>
                  <span>•</span>
                  <a
                    href={normalizeSourceUrl(activeSpeechContext.source_url)}
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
                          {speech.agenda_title && (
                            <span className="transcript-agenda-badge" title={speech.agenda_title}>
                              {speech.agenda_title}
                            </span>
                          )}
                          {isTarget && <span className="target-speech-badge">Otsitud kõne</span>}
                        </div>

                        {speech.video_url && (
                          <a
                            href={speech.video_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="transcript-video-btn"
                            title="Vaata kõnet videost alates selle algusest"
                          >
                            <Video size={13} aria-hidden="true" />
                            <span>Video</span>
                          </a>
                        )}
                      </div>
                      <div className="transcript-row-text">
                        {highlightKeywords(
                          speech.text,
                          groups,
                          contextSearchTerm,
                          speech.matched_words
                        )}
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
                  : "(2019–praegu)"}
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
                  <option value="all">Kõik kokku (2019–praegu)</option>
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
                    {attendanceFactionsList.map((fac, idx) => (
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
                  role="button"
                  tabIndex={0}
                  className="att-col-name cursor-pointer"
                  onClick={() => requestSort("member_name")}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      requestSort("member_name");
                    }
                  }}
                >
                  Saadik{" "}
                  {sortConfig.key === "member_name"
                    ? sortConfig.direction === "ascending"
                      ? "↑"
                      : "↓"
                    : ""}
                </div>
                <div
                  role="button"
                  tabIndex={0}
                  className="att-col-faction cursor-pointer"
                  onClick={() => requestSort("faction")}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      requestSort("faction");
                    }
                  }}
                >
                  Fraktsioon{" "}
                  {sortConfig.key === "faction"
                    ? sortConfig.direction === "ascending"
                      ? "↑"
                      : "↓"
                    : ""}
                </div>
                <div
                  role="button"
                  tabIndex={0}
                  className="att-col-total cursor-pointer"
                  onClick={() => requestSort("total_sessions")}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      requestSort("total_sessions");
                    }
                  }}
                >
                  Kontrolle{" "}
                  {sortConfig.key === "total_sessions"
                    ? sortConfig.direction === "ascending"
                      ? "↑"
                      : "↓"
                    : ""}
                </div>
                <div
                  role="button"
                  tabIndex={0}
                  className="att-col-present cursor-pointer"
                  onClick={() => requestSort("present_sessions")}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      requestSort("present_sessions");
                    }
                  }}
                >
                  Kohal{" "}
                  {sortConfig.key === "present_sessions"
                    ? sortConfig.direction === "ascending"
                      ? "↑"
                      : "↓"
                    : ""}
                </div>
                <div
                  role="button"
                  tabIndex={0}
                  className="att-col-percent cursor-pointer"
                  onClick={() => requestSort("attendance_percentage")}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      requestSort("attendance_percentage");
                    }
                  }}
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
