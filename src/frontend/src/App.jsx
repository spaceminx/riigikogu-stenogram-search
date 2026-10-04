import React, { useState, useEffect } from "react";
import { XAxis, YAxis, Tooltip, ResponsiveContainer, AreaChart, Area } from "recharts";
import {
  fetchSearch,
  fetchActivity,
  fetchSpeakers,
  fetchAttendance,
  fetchFactionAttendance,
  fetchFactionsList,
} from "./api";
import "./App.css";

function formatDateTime(dateStr, timeStr) {
  if (!dateStr) return "";
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
  let formattedDate = dateStr;
  try {
    const parts = dateStr.split("-");
    if (parts.length === 3) {
      const year = parts[0];
      const month = parseInt(parts[1], 10) - 1;
      const day = parseInt(parts[2], 10);
      formattedDate = `${day}. ${months[month]} ${year}`;
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
  return `${formattedDate}${formattedTime}`;
}

function App() {
  const [groups, setGroups] = useState([[]]); // Array of arrays of strings
  const [inputValue, setInputValue] = useState("");
  const [interval, setSelectedInterval] = useState("monthly");
  const [speeches, setSpeeches] = useState([]);
  const [activity, setActivity] = useState([]);
  const [speakers, setSpeakers] = useState([]);
  const [view, setView] = useState("dashboard");
  const [errorMessage, setErrorMessage] = useState(null);
  const [loading, setLoading] = useState(false);

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
    key: "attendance_percentage",
    direction: "descending",
  });
  const [factionSortConfig, setFactionSortConfig] = useState({
    key: "attendance_percentage",
    direction: "descending",
  });

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

  const sortedStats = React.useMemo(() => {
    let sortableItems = [...attendanceStats];
    if (sortConfig.key) {
      sortableItems.sort((a, b) => {
        if (a[sortConfig.key] < b[sortConfig.key]) {
          return sortConfig.direction === "ascending" ? -1 : 1;
        }
        if (a[sortConfig.key] > b[sortConfig.key]) {
          return sortConfig.direction === "ascending" ? 1 : -1;
        }
        return 0;
      });
    }
    return sortableItems;
  }, [attendanceStats, sortConfig]);

  const sortedFactionStats = React.useMemo(() => {
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

  async function handleSearch(e) {
    e.preventDefault();
    const finalQuery = buildBackendQuery();
    if (!finalQuery) return;

    setErrorMessage(null);
    setLoading(true);

    try {
      const searchData = await fetchSearch(finalQuery);
      const activityData = await fetchActivity(finalQuery, interval);
      const speakersData = await fetchSpeakers(finalQuery);

      setSpeeches(searchData.results || []);
      setActivity(activityData.activity || []);
      setSpeakers(speakersData.speakers || []);
      setView("dashboard");

      if (inputValue.trim()) {
        const newGroups = [...groups];
        newGroups[newGroups.length - 1] = [...newGroups[newGroups.length - 1], inputValue.trim()];
        setGroups(newGroups);
        setInputValue("");
      }
    } catch (error) {
      console.error("Frontend request failed:", error);
      setErrorMessage(
        error.message ||
          "Otsingupäring ebaõnnestus. Kontrolli, kas API server töötab aadressil http://127.0.0.1:8000."
      );
    } finally {
      setLoading(false);
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === "Enter") {
      // Let form submit naturally
    }
  };

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
                          ? "Sisesta otsisõna (nt mets)..."
                          : "Lisa sõna..."
                      }
                      value={inputValue}
                      onChange={(e) => setInputValue(e.target.value)}
                      onKeyDown={handleKeyDown}
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
              onChange={(e) => setSelectedInterval(e.target.value)}
            >
              <option value="monthly">Kuu kaupa</option>
              <option value="weekly">Nädala kaupa</option>
              <option value="daily">Päeva kaupa</option>
            </select>

            <button type="submit" className="search-button" disabled={loading}>
              {loading ? "Otsin..." : "Otsi"}
            </button>
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

          {speeches.length > 0 && (
            <div style={{ display: "flex", justifyContent: "center", marginTop: "2.5rem" }}>
              <button
                className="search-button"
                style={{ padding: "1rem 3rem", fontSize: "1.1rem" }}
                onClick={() => setView("speeches")}
              >
                Vaata leitud stenogramme ({speeches.length}) &rarr;
              </button>
            </div>
          )}
        </>
      )}

      {view === "speeches" && speeches.length > 0 && (
        <div className="glass-panel" style={{ marginTop: "0.5rem" }}>
          <div className="chart-header" style={{ marginBottom: "1.5rem" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
              <button
                onClick={() => setView("dashboard")}
                style={{
                  background: "transparent",
                  border: "none",
                  color: "#8b5cf6",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.5rem",
                  fontSize: "1rem",
                  fontWeight: 600,
                  padding: 0,
                }}
              >
                &larr; Tagasi töölauale
              </button>
              <h2
                style={{
                  margin: 0,
                  paddingLeft: "1rem",
                  borderLeft: "1px solid rgba(255,255,255,0.1)",
                }}
              >
                Leitud stenogrammid
              </h2>
            </div>
          </div>
          <div className="speeches-list">
            {speeches.map((speech, index) => (
              <div key={index} className="glass-panel speech-card">
                <div className="speech-meta">
                  <span style={{ color: "#f8fafc", fontWeight: 500 }}>{speech.speaker}</span>
                  <span>•</span>
                  <span style={{ color: "#94a3b8" }}>
                    {formatDateTime(speech.date, speech.time)}
                  </span>
                </div>
                <p className="speech-text">{speech.text.slice(0, 350)}...</p>
                <a
                  href={speech.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="speech-link"
                >
                  Ava stenogramm
                  <svg
                    width="16"
                    height="16"
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
            ))}
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
                Saadikud
              </button>
              <button
                type="button"
                className={`segmented-btn ${attendanceTab === "factions" ? "active" : ""}`}
                onClick={() => setAttendanceTab("factions")}
              >
                Fraktsioonid
              </button>
            </div>

            <div className="attendance-controls-row">
              <div className="filter-group">
                <label className="filter-label">Koosseis:</label>
                <select
                  className="attendance-select"
                  value={attendanceMembership}
                  onChange={(e) => {
                    setAttendanceMembership(e.target.value);
                    setSelectedFaction("");
                    setActiveOnly(false);
                  }}
                >
                  <option value="15">XV Riigikogu (2023–praegu)</option>
                  <option value="14">XIV Riigikogu (2019–2023)</option>
                  <option value="all">Kõik kokku (2019–praegu)</option>
                </select>
              </div>

              {attendanceTab === "members" && (
                <div className="filter-group">
                  <label className="filter-label">Fraktsioon:</label>
                  <select
                    className="attendance-select"
                    value={selectedFaction}
                    onChange={(e) => setSelectedFaction(e.target.value)}
                  >
                    <option value="">Kõik fraktsioonid</option>
                    {factionsList.map((fac, idx) => (
                      <option key={idx} value={fac}>
                        {fac}
                      </option>
                    ))}
                  </select>
                  {selectedFaction && (
                    <button
                      type="button"
                      className="clear-filter-btn"
                      onClick={() => setSelectedFaction("")}
                      title="Eemalda fraktsiooni filter"
                    >
                      &times;
                    </button>
                  )}
                </div>
              )}

              <label className="attendance-checkbox-label">
                <input
                  type="checkbox"
                  checked={activeOnly}
                  onChange={(e) => setActiveOnly(e.target.checked)}
                />
                <span>
                  {attendanceMembership === "14"
                    ? "Ainult saadikud, kes on ametis ka täna"
                    : "Ainult tänased ametisolevad saadikud (101)"}
                </span>
              </label>
            </div>
          </div>

          {attendanceLoading ? (
            <p style={{ textAlign: "center", padding: "3rem", color: "#94a3b8" }}>
              Laen kohaloleku andmeid...
            </p>
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
                        {stat.faction}
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
                            backgroundColor:
                              stat.attendance_percentage >= 90
                                ? "#10b981"
                                : stat.attendance_percentage >= 70
                                  ? "#f59e0b"
                                  : "#ef4444",
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
                      <span className="faction-title">{stat.faction}</span>
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
                            backgroundColor:
                              stat.attendance_percentage >= 90
                                ? "#10b981"
                                : stat.attendance_percentage >= 70
                                  ? "#f59e0b"
                                  : "#ef4444",
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
