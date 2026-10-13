import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import useSWR from "swr";
import {
  Bar,
  BarChart,
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
import { formatFactionName } from "../lib/formatters";
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
  director: "Juhatamisi (DIRECTOR)",
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

  // Set document.title to person name
  useEffect(() => {
    if (person?.full_name) {
      document.title = person.full_name;
    }
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
    return [...stats.by_year]
      .reverse()
      .map((item) => ({
        year: item.year,
        speeches: item.mp?.speeches || 0,
        questions: item.mp?.questions || 0,
        procedural: item.mp?.procedural || 0,
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
      personError.message?.includes("404") ||
      personError.message?.includes("Isikut ei leitud");

    return (
      <div className="person-view-container" style={{ padding: "3rem 1rem" }}>
        <div className="glass-panel" style={{ maxWidth: "600px", margin: "2rem auto", textAlign: "center", padding: "2.5rem" }}>
          <h2 style={{ fontSize: "1.5rem", marginBottom: "1rem" }}>
            {isNotFound ? "Saadikut ei leitud" : "Päringu viga"}
          </h2>
          <p style={{ color: "var(--color-text-muted, #64748b)", marginBottom: "1.5rem" }}>
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

  const mpDurationSec = stats?.duration?.mp_seconds || 0;
  const mpHours = Math.floor(mpDurationSec / 3600);
  const mpMinutes = Math.floor((mpDurationSec % 3600) / 60);

  const totalSpeechesInCurrentTab =
    availableRoleTabs.find((t) => t.id === currentRole)?.count ||
    speechesData?.total_count ||
    0;
  const totalPages = Math.max(1, Math.ceil(totalSpeechesInCurrentTab / SPEECHES_PER_PAGE));

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

  return (
    <div className="person-view-container" style={{ display: "flex", flexDirection: "column", gap: "2rem" }}>
      {/* 1. Profile Header */}
      <section className="glass-panel person-header-card" aria-label="Saadiku profiili päis">
        <div className="person-header-content" style={{ display: "flex", flexWrap: "wrap", gap: "2rem", alignItems: "flex-start" }}>
          <div className="person-avatar-wrapper" style={{ flexShrink: 0 }}>
            {person.photo_url && !imgError ? (
              <img
                src={person.photo_url}
                alt={person.full_name}
                className="person-photo"
                onError={() => setImgError(true)}
                style={{
                  width: "120px",
                  height: "150px",
                  objectFit: "cover",
                  borderRadius: "12px",
                  border: "1px solid var(--panel-border)",
                  boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
                }}
              />
            ) : (
              <div
                className="person-photo-placeholder"
                style={{
                  width: "120px",
                  height: "150px",
                  display: "grid",
                  placeItems: "center",
                  borderRadius: "12px",
                  background: "var(--panel-bg, #f1f5f9)",
                  border: "1px solid var(--panel-border)",
                  fontSize: "2rem",
                  fontWeight: 700,
                  color: "var(--color-primary, #315b84)",
                }}
                aria-hidden="true"
              >
                {initials}
              </div>
            )}
          </div>

          <div className="person-details" style={{ flex: "1 1 300px", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.75rem" }}>
              <h1 style={{ margin: 0, fontSize: "1.85rem", fontWeight: 700 }}>{person.full_name}</h1>
              <span
                className="status-badge"
                style={{
                  fontSize: "0.8rem",
                  padding: "0.25rem 0.65rem",
                  borderRadius: "9999px",
                  background: person.active ? "rgba(34, 197, 94, 0.15)" : "rgba(148, 163, 184, 0.15)",
                  color: person.active ? "#15803d" : "#64748b",
                  border: `1px solid ${person.active ? "rgba(34, 197, 94, 0.3)" : "rgba(148, 163, 184, 0.3)"}`,
                  fontWeight: 600,
                }}
              >
                {person.active ? "Aktiivne liige" : "Endine liige"}
              </span>
            </div>

            {person.electoral_district && (
              <div style={{ color: "var(--color-text-muted, #64748b)", fontSize: "0.95rem" }}>
                Valimisringkond: <strong>{person.electoral_district}</strong>
              </div>
            )}

            {person.factions && person.factions.length > 0 && (
              <div style={{ marginTop: "0.25rem" }}>
                <span style={{ fontSize: "0.85rem", color: "var(--color-text-muted, #64748b)", display: "block", marginBottom: "0.35rem" }}>
                  Fraktsioonide ajalugu:
                </span>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                  {person.factions.map((f, idx) => (
                    <div
                      key={idx}
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "0.4rem",
                        padding: "0.2rem 0.6rem",
                        background: "rgba(255, 255, 255, 0.05)",
                        border: "1px solid var(--panel-border)",
                        borderRadius: "6px",
                        fontSize: "0.85rem",
                      }}
                    >
                      <span className="faction-badge" style={{ margin: 0 }}>
                        {formatFactionName(f.faction)}
                      </span>
                      <span style={{ color: "var(--color-text-muted, #64748b)", fontSize: "0.8rem" }}>
                        ({f.start_date || "—"} kuni {f.end_date || "praegu"})
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Quick search input for this speaker */}
            <form onSubmit={handleSearchSubmit} style={{ marginTop: "0.75rem", display: "flex", gap: "0.5rem", maxWidth: "500px" }}>
              <input
                type="text"
                className="filter-text-input"
                placeholder="Otsi selle saadiku kõnesid…"
                value={searchKeyword}
                onChange={(e) => setSearchKeyword(e.target.value)}
                style={{ flex: 1 }}
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

        <div className="person-metrics-grid" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "1rem" }}>
          <div className="summary-card glass-panel" style={{ padding: "1.25rem" }}>
            <span className="summary-caption" style={{ color: "var(--color-text-muted, #64748b)", fontSize: "0.85rem" }}>
              Kõned saadikuna
            </span>
            <strong style={{ fontSize: "1.75rem", display: "block", margin: "0.25rem 0" }}>
              {stats?.totals?.mp?.speeches ?? (statsLoading ? "…" : "0")}
            </strong>
            <span style={{ fontSize: "0.8rem", color: "var(--color-text-muted, #64748b)" }}>
              Põhiettekanded ja sõnavõtud
            </span>
          </div>

          <div className="summary-card glass-panel" style={{ padding: "1.25rem" }}>
            <span className="summary-caption" style={{ color: "var(--color-text-muted, #64748b)", fontSize: "0.85rem" }}>
              Küsimused ja repliigid
            </span>
            <strong style={{ fontSize: "1.75rem", display: "block", margin: "0.25rem 0" }}>
              {stats?.totals?.mp?.questions ?? (statsLoading ? "…" : "0")}
            </strong>
            <span style={{ fontSize: "0.8rem", color: "var(--color-text-muted, #64748b)" }}>
              Lühisõnavõtud ja küsimused
            </span>
          </div>

          <div className="summary-card glass-panel" style={{ padding: "1.25rem" }}>
            <span className="summary-caption" style={{ color: "var(--color-text-muted, #64748b)", fontSize: "0.85rem" }}>
              Protseduurilised
            </span>
            <strong style={{ fontSize: "1.75rem", display: "block", margin: "0.25rem 0" }}>
              {stats?.totals?.mp?.procedural ?? (statsLoading ? "…" : "0")}
            </strong>
            <span style={{ fontSize: "0.8rem", color: "var(--color-text-muted, #64748b)" }}>
              Päevakorraküsimused jm
            </span>
          </div>

          <div className="summary-card glass-panel" style={{ padding: "1.25rem" }}>
            <span className="summary-caption" style={{ color: "var(--color-text-muted, #64748b)", fontSize: "0.85rem" }}>
              Kokku saadikuna
            </span>
            <strong style={{ fontSize: "1.75rem", display: "block", margin: "0.25rem 0", color: "var(--color-primary, #315b84)" }}>
              {stats?.totals?.mp?.total ?? (statsLoading ? "…" : "0")}
            </strong>
            <span style={{ fontSize: "0.8rem", color: "var(--color-text-muted, #64748b)" }}>
              Kõik sõnavõtud saadikuna
            </span>
          </div>

          <div className="summary-card glass-panel" style={{ padding: "1.25rem" }}>
            <span className="summary-caption" style={{ color: "var(--color-text-muted, #64748b)", fontSize: "0.85rem" }}>
              Kõneaeg saadikuna
            </span>
            <strong style={{ fontSize: "1.75rem", display: "block", margin: "0.25rem 0" }}>
              {statsLoading ? "…" : `${mpHours} h ${mpMinutes} min`}
            </strong>
            <span style={{ fontSize: "0.8rem", color: "var(--color-text-muted, #64748b)" }}>
              alates 14.09.2020
            </span>
          </div>

          <div className="summary-card glass-panel" style={{ padding: "1.25rem" }}>
            <span className="summary-caption" style={{ color: "var(--color-text-muted, #64748b)", fontSize: "0.85rem" }}>
              Kohalolek istungitel
            </span>
            <strong style={{ fontSize: "1.75rem", display: "block", margin: "0.25rem 0" }}>
              {attendanceLoading
                ? "…"
                : attendance?.total_sessions > 0
                ? `${attendance.attendance_percentage}%`
                : "—"}
            </strong>
            <span style={{ fontSize: "0.8rem", color: "var(--color-text-muted, #64748b)" }}>
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
          <div style={{ marginTop: "1.5rem", borderTop: "1px solid var(--panel-border)", paddingTop: "1.25rem" }}>
            <span style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--color-text-muted, #64748b)", display: "block", marginBottom: "0.5rem" }}>
              Muud rollid arhiivis:
            </span>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "1rem", alignItems: "center" }}>
              {stats.totals?.chair?.total > 0 && (
                <div style={{ fontSize: "0.9rem" }}>
                  Esimehena / aseesimehena: <strong>{stats.totals.chair.total}</strong>
                </div>
              )}
              {stats.totals?.minister?.total > 0 && (
                <div style={{ fontSize: "0.9rem" }}>
                  Ministrina: <strong>{stats.totals.minister.total}</strong>
                </div>
              )}
              {stats.totals?.candidate?.total > 0 && (
                <div style={{ fontSize: "0.9rem" }}>
                  Kandidaadina: <strong>{stats.totals.candidate.total}</strong>
                </div>
              )}
              {stats.totals?.other?.total > 0 && (
                <div style={{ fontSize: "0.9rem" }}>
                  Muu roll: <strong>{stats.totals.other.total}</strong>
                </div>
              )}
            </div>
            <p style={{ margin: "0.5rem 0 0", fontSize: "0.8rem", color: "var(--color-text-muted, #64748b)" }}>
              Muudes rollides (ministrina, esimehena, kandidaadina) peetud kõned ei kuulu saadikuna peetud kõnede hulka.
            </p>

            {(stats.director || 0) > 0 && (
              <div style={{ marginTop: "0.75rem", fontSize: "0.85rem", color: "var(--color-text-muted, #64748b)" }}>
                Istungi juhatamisi (DIRECTOR): <strong>{stats.director}</strong> — stenogrammides loetakse need juhatamise sõnavõttudeks; neid ei loeta sisuliste kõnede hulka.
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

          <div style={{ width: "100%", height: "280px", marginBottom: "1.5rem" }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <XAxis dataKey="year" stroke="#cbd3dc" tick={{ fill: "#64748b", fontSize: 12 }} />
                <YAxis stroke="#cbd3dc" tick={{ fill: "#64748b", fontSize: 12 }} />
                <Tooltip {...chartTooltipStyle} />
                <Legend wrapperStyle={{ paddingTop: "10px" }} />
                <Bar dataKey="speeches" name="Kõned" stackId="mp" fill="#315b84" />
                <Bar dataKey="questions" name="Küsimused ja repliigid" stackId="mp" fill="#0ea5e9" />
                <Bar dataKey="procedural" name="Protseduurilised" stackId="mp" fill="#94a3b8" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="table-responsive-container" style={{ overflowX: "auto" }}>
            <table className="person-stats-table" style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.9rem" }}>
              <caption style={{ textAlign: "left", paddingBottom: "0.5rem", color: "var(--color-text-muted, #64748b)", fontWeight: 600 }}>
                Saadikuna peetud sõnavõttude jaotus aastate kaupa
              </caption>
              <thead>
                <tr style={{ borderBottom: "2px solid var(--panel-border)" }}>
                  <th scope="col" style={{ textAlign: "left", padding: "0.5rem" }}>Aasta</th>
                  <th scope="col" style={{ textAlign: "right", padding: "0.5rem" }}>Kõned</th>
                  <th scope="col" style={{ textAlign: "right", padding: "0.5rem" }}>Küsimused</th>
                  <th scope="col" style={{ textAlign: "right", padding: "0.5rem" }}>Protseduurilised</th>
                  <th scope="col" style={{ textAlign: "right", padding: "0.5rem" }}>Kokku saadikuna</th>
                  <th scope="col" style={{ textAlign: "right", padding: "0.5rem" }}>Muud rollid</th>
                  <th scope="col" style={{ textAlign: "right", padding: "0.5rem" }}>Juhatamisi</th>
                </tr>
              </thead>
              <tbody>
                {stats.by_year.map((row) => (
                  <tr key={row.year} style={{ borderBottom: "1px solid var(--panel-border)" }}>
                    <th scope="row" style={{ textAlign: "left", padding: "0.5rem", fontWeight: 600 }}>
                      {row.year}
                    </th>
                    <td style={{ textAlign: "right", padding: "0.5rem" }}>{row.mp?.speeches ?? 0}</td>
                    <td style={{ textAlign: "right", padding: "0.5rem" }}>{row.mp?.questions ?? 0}</td>
                    <td style={{ textAlign: "right", padding: "0.5rem" }}>{row.mp?.procedural ?? 0}</td>
                    <td style={{ textAlign: "right", padding: "0.5rem", fontWeight: 700 }}>
                      {row.mp?.total ?? 0}
                    </td>
                    <td style={{ textAlign: "right", padding: "0.5rem" }}>{row.other_roles_total ?? 0}</td>
                    <td style={{ textAlign: "right", padding: "0.5rem" }}>{row.director ?? 0}</td>
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

          <div className="table-responsive-container" style={{ overflowX: "auto" }}>
            <table className="person-stats-table" style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.9rem" }}>
              <caption style={{ textAlign: "left", paddingBottom: "0.5rem", color: "var(--color-text-muted, #64748b)", fontWeight: 600 }}>
                Kõned ja kohalolek Riigikogu koosseisude kaupa
              </caption>
              <thead>
                <tr style={{ borderBottom: "2px solid var(--panel-border)" }}>
                  <th scope="col" style={{ textAlign: "left", padding: "0.5rem" }}>Koosseis</th>
                  <th scope="col" style={{ textAlign: "right", padding: "0.5rem" }}>Kõned</th>
                  <th scope="col" style={{ textAlign: "right", padding: "0.5rem" }}>Küsimused</th>
                  <th scope="col" style={{ textAlign: "right", padding: "0.5rem" }}>Protseduurilised</th>
                  <th scope="col" style={{ textAlign: "right", padding: "0.5rem" }}>Kokku saadikuna</th>
                  <th scope="col" style={{ textAlign: "right", padding: "0.5rem" }}>Muud rollid</th>
                  <th scope="col" style={{ textAlign: "right", padding: "0.5rem" }}>Juhatamisi</th>
                  <th scope="col" style={{ textAlign: "right", padding: "0.5rem" }}>Kohalolek</th>
                </tr>
              </thead>
              <tbody>
                {combinedMemberships.map(({ membership, stats: memStats, attendance: memAtt }) => (
                  <tr key={membership} style={{ borderBottom: "1px solid var(--panel-border)" }}>
                    <th scope="row" style={{ textAlign: "left", padding: "0.5rem", fontWeight: 600 }}>
                      {MEMBERSHIP_ROMAN[membership] || `${membership}. koosseis`}
                    </th>
                    <td style={{ textAlign: "right", padding: "0.5rem" }}>{memStats?.mp?.speeches ?? 0}</td>
                    <td style={{ textAlign: "right", padding: "0.5rem" }}>{memStats?.mp?.questions ?? 0}</td>
                    <td style={{ textAlign: "right", padding: "0.5rem" }}>{memStats?.mp?.procedural ?? 0}</td>
                    <td style={{ textAlign: "right", padding: "0.5rem", fontWeight: 700 }}>
                      {memStats?.mp?.total ?? 0}
                    </td>
                    <td style={{ textAlign: "right", padding: "0.5rem" }}>
                      {memStats?.other_roles_total ?? 0}
                    </td>
                    <td style={{ textAlign: "right", padding: "0.5rem" }}>{memStats?.director ?? 0}</td>
                    <td style={{ textAlign: "right", padding: "0.5rem" }}>
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

        {/* Role Tabs: only roles with count > 0 */}
        {availableRoleTabs.length > 0 && (
          <div
            className="segmented-control"
            role="tablist"
            aria-label="Kõnede rollid"
            style={{ marginBottom: "1.5rem", flexWrap: "wrap" }}
          >
            {availableRoleTabs.map((tab) => {
              const isActive = currentRole === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  className={`segmented-btn ${isActive ? "active" : ""}`}
                  onClick={() => handleRoleChange(tab.id)}
                  style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}
                >
                  <span>{tab.label}</span>
                  <span
                    style={{
                      background: isActive ? "var(--color-primary, #315b84)" : "rgba(148, 163, 184, 0.2)",
                      color: isActive ? "#ffffff" : "inherit",
                      padding: "0.1rem 0.45rem",
                      borderRadius: "9999px",
                      fontSize: "0.75rem",
                      fontWeight: 600,
                    }}
                  >
                    {tab.count}
                  </span>
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
            <p style={{ color: "#ef4444" }}>Kõnede laadimine ebaõnnestus: {speechesError.message}</p>
          </div>
        ) : !speechesData?.results || speechesData.results.length === 0 ? (
          <div style={{ padding: "3rem 1rem", textAlign: "center" }}>
            <p className="sidebar-empty-state">Selles rollis kõnesid ei leitud.</p>
          </div>
        ) : (
          <>
            <div className="speeches-list" style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
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
