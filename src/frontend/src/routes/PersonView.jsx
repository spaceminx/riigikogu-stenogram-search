import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import useSWR from "swr";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  fetchPerson,
  fetchPersonAttendance,
  fetchPersonSpeeches,
  fetchPersonStats,
  fetchSpeechContext,
} from "../lib/api";
import { formatDate } from "../lib/calendarUtils";
import { SpeechCard } from "../components/SpeechCard";
import { Pagination } from "../components/Pagination";
import { ContextModal } from "../components/ContextModal";

const SPEECHES_PER_PAGE = 20;

const ROLE_LABELS = {
  mp: "Saadikuna",
  chair: "Esimehena / aseesimehena",
  minister: "Ministrina",
  candidate: "Kandidaadina",
  other: "Muu roll",
  director: "Juhatamisi",
};

const MEMBERSHIP_ROMAN = {
  15: "XV Riigikogu",
  14: "XIV Riigikogu",
  13: "XIII Riigikogu",
  12: "XII Riigikogu",
  11: "XI Riigikogu",
};

export function PersonView({ theme = "light" }) {
  const { uuid } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [imgError, setImgError] = useState(false);
  const [searchKeyword, setSearchKeyword] = useState("");
  const [activeSpeechContext, setActiveSpeechContext] = useState(null);

  // imgError and other states are reset on uuid change via key={uuid} on route element
  // Read role and page from URL parameters
  const currentRole = searchParams.get("roll") || "mp";
  const currentPage = parseInt(searchParams.get("leht") || "1", 10) || 1;
  const offset = (currentPage - 1) * SPEECHES_PER_PAGE;

  // 1. Fetch Person Details
  const {
    data: person,
    error: personError,
    isLoading: personLoading,
  } = useSWR(uuid ? `person-${uuid}` : null, () => fetchPerson(uuid), {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });

  // 2. Fetch Stats
  const {
    data: stats,
    error: statsError,
    isLoading: statsLoading,
  } = useSWR(uuid ? `person-stats-${uuid}` : null, () => fetchPersonStats(uuid), {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });

  // 3. Fetch Attendance
  const {
    data: attendance,
    error: attendanceError,
    isLoading: attendanceLoading,
  } = useSWR(uuid ? `person-attendance-${uuid}` : null, () => fetchPersonAttendance(uuid), {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });

  // 4. Fetch Speeches for selected role & page
  const {
    data: speechesData,
    error: speechesError,
    isLoading: speechesLoading,
  } = useSWR(
    uuid ? `person-speeches-${uuid}-${currentRole}-${currentPage}` : null,
    () =>
      fetchPersonSpeeches(uuid, {
        roleClass: currentRole,
        limit: SPEECHES_PER_PAGE,
        offset,
      }),
    {
      revalidateOnFocus: false,
      shouldRetryOnError: false,
    }
  );

  // Set document.title format: "{nimi} — Riigivaade" with cleanup
  useEffect(() => {
    const prevTitle = document.title;
    if (person?.full_name) {
      document.title = `${person.full_name} — Riigivaade`;
    }
    return () => {
      document.title = prevTitle;
    };
  }, [person?.full_name]);

  // Context modal handler
  const handleOpenContext = async (speechId) => {
    try {
      const data = await fetchSpeechContext(speechId);
      setActiveSpeechContext(data);
    } catch {
      // Ignored
    }
  };

  // Switch role tab
  const handleRoleChange = (newRole) => {
    const next = new URLSearchParams(searchParams);
    if (newRole === "mp") {
      next.delete("roll");
    } else {
      next.set("roll", newRole);
    }
    next.delete("leht");
    setSearchParams(next);
  };

  // Switch page
  const handlePageChange = (newPage) => {
    const next = new URLSearchParams(searchParams);
    if (newPage <= 1) {
      next.delete("leht");
    } else {
      next.set("leht", String(newPage));
    }
    setSearchParams(next);
    window.scrollTo({ top: 600, behavior: "smooth" });
  };

  // Search by speaker query submit
  const handleSearchSubmit = (e) => {
    e.preventDefault();
    if (!uuid) return;
    const q = searchKeyword.trim();
    if (!q) return;
    navigate(`/otsing?q=${encodeURIComponent(q)}&speaker_uuid=${encodeURIComponent(uuid)}`);
  };

  // Compute available role tabs based on counts > 0
  const availableRoleTabs = useMemo(() => {
    if (!stats) return [];
    const tabs = [];
    const roleOrder = ["mp", "chair", "minister", "candidate", "other"];
    for (const r of roleOrder) {
      const cnt = stats.totals?.[r]?.total || 0;
      if (cnt > 0) {
        tabs.push({ id: r, label: ROLE_LABELS[r], count: cnt });
      }
    }
    if ((stats.director || 0) > 0) {
      tabs.push({ id: "director", label: ROLE_LABELS.director, count: stats.director });
    }
    return tabs;
  }, [stats]);

  // Prepare stacked bar chart data (by_year sorted ascending)
  const chartData = useMemo(() => {
    if (!stats?.by_year) return [];
    return [...stats.by_year].reverse().map((item) => ({
      year: item.year,
      speeches: item.mp?.speeches || 0,
      questions: item.mp?.questions || 0,
      procedural: item.mp?.procedural || 0,
      unclassified: item.mp?.unclassified || 0,
      total: item.mp?.total || 0,
    }));
  }, [stats]);

  // Combine by_membership stats and attendance by membership
  const combinedMemberships = useMemo(() => {
    const memMap = new Map();
    if (stats?.by_membership) {
      for (const m of stats.by_membership) {
        memMap.set(m.membership, {
          membership: m.membership,
          stats: m,
          attendance: null,
        });
      }
    }
    if (attendance?.by_membership) {
      for (const att of attendance.by_membership) {
        if (!memMap.has(att.membership)) {
          memMap.set(att.membership, {
            membership: att.membership,
            stats: null,
            attendance: att,
          });
        } else {
          memMap.get(att.membership).attendance = att;
        }
      }
    }
    return Array.from(memMap.values()).sort(
      (a, b) => parseInt(b.membership, 10) - parseInt(a.membership, 10)
    );
  }, [stats, attendance]);

  // Handle 404 and error states for Person
  if (personLoading) {
    return (
      <div className="person-view-container" style={{ padding: "3rem 1rem", textAlign: "center" }}>
        <p className="sidebar-empty-state">Laen saadiku andmeid…</p>
      </div>
    );
  }

  if (personError) {
    const isNotFound =
      personError.message?.includes("404") || personError.message?.includes("Isikut ei leitud");

    return (
      <div className="person-view-container" style={{ padding: "3rem 1rem" }}>
        <div className="glass-panel person-not-found-card">
          <h2 className="person-not-found-title">
            {isNotFound ? "Saadikut ei leitud" : "Päringu viga"}
          </h2>
          <p className="person-not-found-desc">
            {isNotFound
              ? "Otsitud identifikaatoriga saadikut Riigikogu arhiivis ei eksisteeri."
              : personError.message}
          </p>
          <Link
            to="/"
            className="filter-search-btn"
            style={{ display: "inline-block", textDecoration: "none" }}
          >
            Tagasi avalehele
          </Link>
        </div>
      </div>
    );
  }

  if (!person) return null;

  const initials = (person.full_name || "?")
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();

  const totalSpeechesInCurrentTab =
    availableRoleTabs.find((t) => t.id === currentRole)?.count || speechesData?.total_count || 0;
  const totalPages = Math.max(1, Math.ceil(totalSpeechesInCurrentTab / SPEECHES_PER_PAGE));

  const hasUnclassified = (stats?.totals?.mp?.unclassified || 0) > 0;
  const hasDirector = (stats?.director || 0) > 0;

  // Theming for chart tooltip, axes and grid lines
  const axisStroke = theme === "dark" ? "#334155" : "#cbd3dc";
  const tickColor = theme === "dark" ? "#94a3b8" : "#64748b";
  const gridStroke = theme === "dark" ? "#334155" : "#e2e8f0";

  const chartTooltipStyle = {
    contentStyle: {
      backgroundColor: theme === "dark" ? "#1e293b" : "#ffffff",
      color: theme === "dark" ? "#f1f5f9" : "#25364a",
      border: `1px solid ${theme === "dark" ? "#334155" : "#cbd3dc"}`,
      borderRadius: "4px",
      boxShadow: "0 2px 8px rgba(0, 0, 0, 0.2)",
    },
    itemStyle: { fontWeight: 600 },
    labelStyle: { color: theme === "dark" ? "#94a3b8" : "#536477", marginBottom: "4px" },
  };

  // Helper for metrics when stats load or fail
  const getMetricValue = (val) => {
    if (statsLoading) return "…";
    if (!stats || statsError || val == null) return "—";
    return val;
  };

  let formattedDuration = "—";
  if (statsLoading) {
    formattedDuration = "…";
  } else if (stats && !statsError && stats.duration?.mp_seconds != null) {
    const mpDurationSec = stats.duration.mp_seconds;
    const mpHours = Math.floor(mpDurationSec / 3600);
    const mpMinutes = Math.floor((mpDurationSec % 3600) / 60);
    formattedDuration = `${mpHours} h ${mpMinutes} min`;
  }

  let formattedAttendance = "—";
  if (attendanceLoading) {
    formattedAttendance = "…";
  } else if (attendance && !attendanceError && attendance.total_sessions > 0) {
    formattedAttendance = `${attendance.attendance_percentage}%`;
  }

  const formatFactionPeriod = (start, end) => {
    const startStr = start ? formatDate(start) : "—";
    const endStr = !end || end === "2099-12-31" ? "praegu" : formatDate(end);
    return `${startStr} – ${endStr}`;
  };

  return (
    <div className="person-view-container">
      {/* 1. Profile Header */}
      <section className="glass-panel person-header-card" aria-label="Saadiku profiili päis">
        <div className="person-header-content">
          <div className="person-avatar-wrapper">
            {person.photo_url && !imgError ? (
              <img
                src={person.photo_url}
                alt={person.full_name}
                className="person-photo"
                onError={() => setImgError(true)}
              />
            ) : (
              <div className="person-photo-placeholder" aria-hidden="true">
                {initials}
              </div>
            )}
          </div>

          <div className="person-details">
            <div className="person-title-row">
              <h1>{person.full_name}</h1>
              <span className={`person-status-badge ${person.active ? "is-active" : "is-former"}`}>
                {person.active ? "Aktiivne liige" : "Endine liige"}
              </span>
            </div>

            {person.electoral_district && (
              <div className="person-district">
                Valimisringkond: <strong>{person.electoral_district}</strong>
              </div>
            )}

            {person.factions && person.factions.length > 0 && (
              <div className="person-factions-section">
                <span className="person-factions-label">Fraktsioonide ajalugu:</span>
                <div className="person-factions-list">
                  {person.factions.map((f, idx) => (
                    <div key={idx} className="person-faction-chip">
                      <span>{f.faction}</span>
                      <span className="person-faction-period">
                        ({formatFactionPeriod(f.start, f.end)})
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Quick search input for this speaker */}
            <form onSubmit={handleSearchSubmit} className="person-search-form">
              <input
                type="text"
                className="filter-text-input"
                placeholder="Otsi selle saadiku kõnesid…"
                value={searchKeyword}
                onChange={(e) => setSearchKeyword(e.target.value)}
              />
              <button
                type="submit"
                className="filter-search-btn"
                disabled={!searchKeyword.trim()}
                title="Ava otsing selle saadiku kõnedest"
              >
                Otsi
              </button>
            </form>
          </div>
        </div>
      </section>

      {/* 2. Key Metrics as MP (Totals.mp) */}
      <section className="glass-panel" aria-label="Põhinäitajad saadikuna">
        <div className="chart-header" style={{ marginBottom: "1.25rem" }}>
          <div>
            <span className="section-kicker">PÕHINÄITAJAD SAADIKUNA</span>
            <h2 style={{ margin: 0, fontSize: "1.25rem" }}>Aktiivsus ja osalus Riigikogus</h2>
          </div>
        </div>

        {statsError && (
          <div className="error-banner" style={{ marginBottom: "1rem" }}>
            <div className="error-content">
              <span className="error-icon">!</span>
              <span>Statistika laadimine ebaõnnestus: {statsError.message}</span>
            </div>
          </div>
        )}

        <div className="person-metrics-grid">
          <div className="summary-card glass-panel person-metric-card">
            <span className="summary-caption person-metric-label">Kõned saadikuna</span>
            <strong className="person-metric-value">
              {getMetricValue(stats?.totals?.mp?.speeches)}
            </strong>
            <span className="person-metric-desc">Põhiettekanded ja sõnavõtud</span>
          </div>

          <div className="summary-card glass-panel person-metric-card">
            <span className="summary-caption person-metric-label">Küsimused ja repliigid</span>
            <strong className="person-metric-value">
              {getMetricValue(stats?.totals?.mp?.questions)}
            </strong>
            <span className="person-metric-desc">Lühisõnavõtud ja küsimused</span>
          </div>

          <div className="summary-card glass-panel person-metric-card">
            <span className="summary-caption person-metric-label">Protseduurilised</span>
            <strong className="person-metric-value">
              {getMetricValue(stats?.totals?.mp?.procedural)}
            </strong>
            <span className="person-metric-desc">
              Protseduurilised küsimused ja ettepanekud istungi läbiviimise kohta
            </span>
          </div>

          <div className="summary-card glass-panel person-metric-card">
            <span className="summary-caption person-metric-label">Kokku saadikuna</span>
            <strong className="person-metric-value person-metric-value-primary">
              {getMetricValue(stats?.totals?.mp?.total)}
            </strong>
            <span className="person-metric-desc">
              Kõik sõnavõtud saadikuna
              {hasUnclassified ? ` (sh ${stats.totals.mp.unclassified} liigitamata)` : ""}
            </span>
          </div>

          <div className="summary-card glass-panel person-metric-card">
            <span className="summary-caption person-metric-label">Kõneaeg saadikuna</span>
            <strong className="person-metric-value">{formattedDuration}</strong>
            <span className="person-metric-desc">alates 14.09.2020</span>
          </div>

          <div className="summary-card glass-panel person-metric-card">
            <span className="summary-caption person-metric-label">
              Kohalolek kohalolekukontrollides
            </span>
            <strong className="person-metric-value">{formattedAttendance}</strong>
            <span className="person-metric-desc">
              {attendanceError
                ? "Kohaloleku andmed puuduvad"
                : attendance?.total_sessions > 0
                  ? `${attendance.present_sessions} / ${attendance.total_sessions} korda kohal`
                  : "Kohalolekukontrollid puuduvad"}
            </span>
          </div>
        </div>

        {/* Other Roles breakdown if present */}
        {stats && (
          <div className="person-other-roles">
            <span className="person-other-roles-title">Muud rollid arhiivis:</span>
            <div className="person-other-roles-list">
              {stats.totals?.chair?.total > 0 && (
                <div className="person-other-role-item">
                  Esimehena / aseesimehena: <strong>{stats.totals.chair.total}</strong>
                </div>
              )}
              {stats.totals?.minister?.total > 0 && (
                <div className="person-other-role-item">
                  Ministrina: <strong>{stats.totals.minister.total}</strong>
                </div>
              )}
              {stats.totals?.candidate?.total > 0 && (
                <div className="person-other-role-item">
                  Kandidaadina: <strong>{stats.totals.candidate.total}</strong>
                </div>
              )}
              {stats.totals?.other?.total > 0 && (
                <div className="person-other-role-item">
                  Muu roll: <strong>{stats.totals.other.total}</strong>
                </div>
              )}
            </div>
            <p className="person-other-roles-desc">
              Muudes rollides (ministrina, esimehena, kandidaadina) peetud kõned ei kuulu saadikuna
              peetud kõnede hulka.
            </p>

            {hasUnclassified && (
              <p className="person-other-roles-desc">
                Liigitamata sõnavõtud saadikuna: <strong>{stats.totals.mp.unclassified}</strong> —
                stenogrammis märgitud DIRECTOR-tüübina väljaspool istungi juhatamist.
              </p>
            )}

            {hasDirector && (
              <div className="person-director-note">
                Istungi juhatamisi: <strong>{stats.director}</strong> — stenogrammides tuvastatud
                juhatamise sõnavõtud esimehe või aseesimehe rollis.
              </div>
            )}
          </div>
        )}
      </section>

      {/* 3. By Year Stacked Chart & Accessible Table */}
      {chartData.length > 0 && (
        <section className="glass-panel" aria-label="Sõnavõtud aastate kaupa">
          <div className="chart-header" style={{ marginBottom: "1rem" }}>
            <div>
              <span className="section-kicker">AASTATE KAUPA</span>
              <h2 style={{ margin: 0, fontSize: "1.25rem" }}>Kõned saadikuna aastate lõikes</h2>
            </div>
          </div>

          <div className="person-chart-container">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} vertical={false} />
                <XAxis
                  dataKey="year"
                  stroke={axisStroke}
                  tick={{ fill: tickColor, fontSize: 12 }}
                />
                <YAxis
                  stroke={axisStroke}
                  tick={{ fill: tickColor, fontSize: 12 }}
                  allowDecimals={false}
                />
                <Tooltip {...chartTooltipStyle} />
                <Legend wrapperStyle={{ paddingTop: "10px" }} />
                <Bar dataKey="speeches" name="Kõned" stackId="mp" fill="#315b84" />
                <Bar
                  dataKey="questions"
                  name="Küsimused ja repliigid"
                  stackId="mp"
                  fill="#0ea5e9"
                />
                <Bar dataKey="procedural" name="Protseduurilised" stackId="mp" fill="#94a3b8" />
                {hasUnclassified && (
                  <Bar dataKey="unclassified" name="Liigitamata" stackId="mp" fill="#f59e0b" />
                )}
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="table-responsive-container">
            <table className="person-stats-table">
              <caption>Saadikuna peetud sõnavõttude jaotus aastate kaupa</caption>
              <thead>
                <tr>
                  <th scope="col" className="person-stats-col-text">
                    Aasta
                  </th>
                  <th scope="col" className="person-stats-col-num">
                    Kõned
                  </th>
                  <th scope="col" className="person-stats-col-num">
                    Küsimused
                  </th>
                  <th scope="col" className="person-stats-col-num">
                    Protseduurilised
                  </th>
                  {hasUnclassified && (
                    <th scope="col" className="person-stats-col-num">
                      Liigitamata
                    </th>
                  )}
                  <th scope="col" className="person-stats-col-num">
                    Kokku saadikuna
                  </th>
                  <th scope="col" className="person-stats-col-num">
                    Muud rollid
                  </th>
                  {hasDirector && (
                    <th scope="col" className="person-stats-col-num">
                      Juhatamisi
                    </th>
                  )}
                </tr>
              </thead>
              <tbody>
                {stats.by_year.map((row) => (
                  <tr key={row.year}>
                    <th scope="row" className="person-stats-col-text">
                      {row.year}
                    </th>
                    <td className="person-stats-col-num">{row.mp?.speeches ?? 0}</td>
                    <td className="person-stats-col-num">{row.mp?.questions ?? 0}</td>
                    <td className="person-stats-col-num">{row.mp?.procedural ?? 0}</td>
                    {hasUnclassified && (
                      <td className="person-stats-col-num">{row.mp?.unclassified ?? 0}</td>
                    )}
                    <td className="person-stats-col-num" style={{ fontWeight: 700 }}>
                      {row.mp?.total ?? 0}
                    </td>
                    <td className="person-stats-col-num">{row.other_roles_total ?? 0}</td>
                    {hasDirector && <td className="person-stats-col-num">{row.director ?? 0}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* 4. By Membership Combined Table (Speeches + Attendance) */}
      {combinedMemberships.length > 0 && (
        <section className="glass-panel" aria-label="Koosseisude kaupa ülevaade">
          <div className="chart-header" style={{ marginBottom: "1rem" }}>
            <div>
              <span className="section-kicker">KOOSSEISUDE KAUPA</span>
              <h2 style={{ margin: 0, fontSize: "1.25rem" }}>Aktiivsus ja kohalolek koosseisuti</h2>
            </div>
          </div>

          <div className="table-responsive-container">
            <table className="person-stats-table">
              <caption>Kõned ja kohalolek Riigikogu koosseisude kaupa</caption>
              <thead>
                <tr>
                  <th scope="col" className="person-stats-col-text">
                    Koosseis
                  </th>
                  <th scope="col" className="person-stats-col-num">
                    Kõned
                  </th>
                  <th scope="col" className="person-stats-col-num">
                    Küsimused
                  </th>
                  <th scope="col" className="person-stats-col-num">
                    Protseduurilised
                  </th>
                  {hasUnclassified && (
                    <th scope="col" className="person-stats-col-num">
                      Liigitamata
                    </th>
                  )}
                  <th scope="col" className="person-stats-col-num">
                    Kokku saadikuna
                  </th>
                  <th scope="col" className="person-stats-col-num">
                    Muud rollid
                  </th>
                  {hasDirector && (
                    <th scope="col" className="person-stats-col-num">
                      Juhatamisi
                    </th>
                  )}
                  <th scope="col" className="person-stats-col-num">
                    Kohalolek
                  </th>
                </tr>
              </thead>
              <tbody>
                {combinedMemberships.map(({ membership, stats: memStats, attendance: memAtt }) => (
                  <tr key={membership}>
                    <th scope="row" className="person-stats-col-text">
                      {MEMBERSHIP_ROMAN[membership] || `${membership}. koosseis`}
                    </th>
                    <td className="person-stats-col-num">{memStats?.mp?.speeches ?? 0}</td>
                    <td className="person-stats-col-num">{memStats?.mp?.questions ?? 0}</td>
                    <td className="person-stats-col-num">{memStats?.mp?.procedural ?? 0}</td>
                    {hasUnclassified && (
                      <td className="person-stats-col-num">{memStats?.mp?.unclassified ?? 0}</td>
                    )}
                    <td className="person-stats-col-num" style={{ fontWeight: 700 }}>
                      {memStats?.mp?.total ?? 0}
                    </td>
                    <td className="person-stats-col-num">{memStats?.other_roles_total ?? 0}</td>
                    {hasDirector && (
                      <td className="person-stats-col-num">{memStats?.director ?? 0}</td>
                    )}
                    <td className="person-stats-col-num">
                      {memAtt && memAtt.total_sessions > 0
                        ? `${memAtt.attendance_percentage}% (${memAtt.present_sessions}/${memAtt.total_sessions})`
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* 5. Speeches List with Role Tabs & Pagination */}
      <section className="glass-panel" aria-label="Saadiku kõnede loend">
        <div className="chart-header" style={{ marginBottom: "1rem" }}>
          <div>
            <span className="section-kicker">KÕNEDE NIMEKIRI</span>
            <h2 style={{ margin: 0, fontSize: "1.25rem" }}>Stenogrammide loend</h2>
          </div>
        </div>

        {/* Role Tabs: Simple buttons with aria-pressed */}
        {availableRoleTabs.length > 0 && (
          <div
            className="segmented-control"
            role="group"
            aria-label="Kõnede rollid"
            style={{ marginBottom: "1.5rem", flexWrap: "wrap" }}
          >
            {availableRoleTabs.map((tab) => {
              const isActive = currentRole === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  aria-pressed={isActive}
                  className={`segmented-btn ${isActive ? "active" : ""}`}
                  onClick={() => handleRoleChange(tab.id)}
                >
                  <span>{tab.label}</span>
                  <span className="person-tab-count">{tab.count}</span>
                </button>
              );
            })}
          </div>
        )}

        {/* Speeches Cards */}
        {speechesLoading ? (
          <div style={{ padding: "3rem 1rem", textAlign: "center" }}>
            <p className="sidebar-empty-state">Laen kõnesid…</p>
          </div>
        ) : speechesError ? (
          <div style={{ padding: "2rem 1rem", textAlign: "center" }}>
            <p style={{ color: "#ef4444" }}>
              Kõnede laadimine ebaõnnestus: {speechesError.message}
            </p>
          </div>
        ) : !speechesData?.results || speechesData.results.length === 0 ? (
          <div style={{ padding: "3rem 1rem", textAlign: "center" }}>
            <p className="sidebar-empty-state">Selles rollis kõnesid ei leitud.</p>
          </div>
        ) : (
          <>
            <div className="person-speeches-list">
              {speechesData.results.map((speech) => (
                <SpeechCard
                  key={speech.id}
                  speech={speech}
                  mode="search"
                  onOpenContext={handleOpenContext}
                />
              ))}
            </div>

            <Pagination
              currentPage={currentPage}
              totalPages={totalPages}
              onPageChange={handlePageChange}
              loading={speechesLoading}
            />
          </>
        )}
      </section>

      {/* Context Modal */}
      {activeSpeechContext && (
        <ContextModal
          activeSpeechContext={activeSpeechContext}
          onClose={() => setActiveSpeechContext(null)}
        />
      )}
    </div>
  );
}

export default PersonView;
