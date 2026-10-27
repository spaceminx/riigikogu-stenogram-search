import React, { useMemo, useState } from "react";
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
  fetchFactionAlignment,
  fetchFactionAlignmentDifferences,
  fetchPerson,
  fetchPersonAttendance,
  fetchPersonSpeeches,
  fetchPersonStats,
  fetchSpeechContext,
} from "../lib/api";
import { formatDate } from "../lib/calendarUtils";
import { formatMetricRatio, formatPercent, formatVoteSplit, toRoman } from "../lib/formatters";
import { SpeechCard } from "../components/SpeechCard";
import { Pagination } from "../components/Pagination";
import { ContextModal } from "../components/ContextModal";
import { usePageMeta } from "../lib/usePageMeta";
import { chartColors } from "../lib/chartColors";
import { Rss } from "lucide-react";

const SPEECHES_PER_PAGE = 20;

const DECISION_LABELS = {
  POOLT: "poolt",
  VASTU: "vastu",
  ERAPOOLETU: "erapooletu",
  EI_HAALETANUD: "ei hääletanud",
  PUUDUB: "puudub",
};

const formatDecision = (dec) => DECISION_LABELS[dec] || dec?.toLowerCase() || "—";

const ROLE_LABELS = {
  mp: "Saadikuna",
  chair: "Esimehena / aseesimehena",
  minister: "Ministrina",
  candidate: "Kandidaadina",
  other: "Muu roll",
  director: "Juhatamisi",
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
  const noInfotund = searchParams.get("no_infotund") === "1";
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
  } = useSWR(
    uuid ? `person-attendance-${uuid}-${noInfotund ? "no_infotund" : "all"}` : null,
    () => fetchPersonAttendance(uuid, { excludeInfotund: noInfotund }),
    {
      revalidateOnFocus: false,
      shouldRetryOnError: false,
    }
  );

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

  // 5. Fetch Faction Alignment
  const [alignmentMembership, setAlignmentMembership] = useState("all");
  const [extraDifferences, setExtraDifferences] = useState([]);
  const [diffsLoadingMore, setDiffsLoadingMore] = useState(false);

  const { data: factionAlignment } = useSWR(
    uuid ? `person-faction-alignment-${uuid}-${alignmentMembership}` : null,
    () => fetchFactionAlignment(uuid, alignmentMembership),
    {
      revalidateOnFocus: false,
      shouldRetryOnError: false,
      // Keep the panel and its membership switch on screen while another membership loads
      keepPreviousData: true,
    }
  );

  // A membership can have no comparable votes (e.g. only as a non-affiliated member); the panel
  // still has to show so the switch stays usable
  const alignmentComparable = factionAlignment
    ? factionAlignment.same + factionAlignment.different
    : 0;
  const showAlignmentPanel =
    alignmentComparable > 0 ||
    Boolean(factionAlignment?.by_membership?.some((m) => m.same + m.different > 0));

  const { data: initialDifferences, isLoading: diffsInitialLoading } = useSWR(
    uuid ? `person-faction-diffs-${uuid}-${alignmentMembership}` : null,
    () =>
      fetchFactionAlignmentDifferences(uuid, {
        membership: alignmentMembership,
        limit: 10,
        offset: 0,
      }),
    {
      revalidateOnFocus: false,
      shouldRetryOnError: false,
    }
  );

  const totalDifferences = initialDifferences?.total ?? 0;

  const differences = useMemo(
    () => [...(initialDifferences?.results || []), ...extraDifferences],
    [initialDifferences, extraDifferences]
  );

  const diffLoading = diffsInitialLoading || diffsLoadingMore;

  const hasMoreDiffs = useMemo(() => {
    if (!initialDifferences) return false;
    return differences.length < (initialDifferences.total ?? 0);
  }, [initialDifferences, differences]);

  const handleAlignmentMembershipChange = (m) => {
    setAlignmentMembership(m);
    setExtraDifferences([]);
  };

  const handleLoadMoreDifferences = async () => {
    if (diffLoading || !uuid) return;
    setDiffsLoadingMore(true);
    try {
      const res = await fetchFactionAlignmentDifferences(uuid, {
        membership: alignmentMembership,
        limit: 10,
        offset: differences.length,
      });
      const nextItems = res?.results || [];
      if (nextItems.length > 0) {
        setExtraDifferences((prev) => [...prev, ...nextItems]);
      }
    } catch {
      // Ignored
    } finally {
      setDiffsLoadingMore(false);
    }
  };

  // Set document.title format: "{nimi} — Riigivaade" and description
  const personTitle = person?.full_name
    ? `${person.full_name} — Riigivaade`
    : "Saadik — Riigivaade";
  const personDesc = person?.full_name
    ? `Riigikogu saadiku ${person.full_name} kõned, hääletused, kohalolek ja fraktsiooniline kuuluvus.`
    : "Riigikogu saadiku profiil, kõned, hääletused ja kohalolek.";

  const rssUrl = uuid ? `https://www.riigivaade.me/rss/saadik/${uuid}` : null;

  usePageMeta(
    personTitle,
    personDesc,
    rssUrl
      ? {
          rss: {
            href: rssUrl,
            title: `Riigivaade: ${person?.full_name || "saadiku"} kõned`,
          },
        }
      : {}
  );

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

  const handleNoInfotundChange = (checked) => {
    const next = new URLSearchParams(searchParams);
    if (checked) {
      next.set("no_infotund", "1");
    } else {
      next.delete("no_infotund");
    }
    setSearchParams(next, { replace: true });
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

  const roleBreakdownRows = useMemo(() => {
    if (!attendance?.role_breakdown) return [];
    const rows = [];
    const { coalition, opposition } = attendance.role_breakdown;

    if (coalition && (coalition.total_sessions > 0 || coalition.votes?.total > 0)) {
      rows.push({
        role: "Koalitsioonis",
        key: "coalition",
        ...coalition,
      });
    }

    if (opposition && (opposition.total_sessions > 0 || opposition.votes?.total > 0)) {
      rows.push({
        role: "Opositsioonis",
        key: "opposition",
        ...opposition,
      });
    }

    return rows;
  }, [attendance]);

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
  const colors = chartColors(theme);
  const axisStroke = colors.border;
  const tickColor = colors.muted;
  const gridStroke = colors.border;

  const chartTooltipStyle = {
    contentStyle: {
      backgroundColor: colors.surface,
      color: colors.text,
      border: `1px solid ${colors.border}`,
      borderRadius: "4px",
      boxShadow: "0 2px 8px rgba(0, 0, 0, 0.2)",
    },
    itemStyle: { fontWeight: 600 },
    labelStyle: { color: colors.muted, marginBottom: "4px" },
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
    formattedAttendance = formatPercent(attendance.attendance_percentage);
  }

  let formattedVotes = "—";
  if (attendanceLoading) {
    formattedVotes = "…";
  } else if (
    attendance &&
    !attendanceError &&
    attendance.votes?.total > 0 &&
    attendance.votes.voted_pct != null
  ) {
    formattedVotes = formatPercent(attendance.votes.voted_pct);
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
              <>
                <img
                  src={person.photo_url}
                  alt={person.full_name}
                  className="person-photo"
                  onError={() => setImgError(true)}
                />
                <div className="person-photo-caption">Foto: Riigikogu</div>
              </>
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
            <div className="person-actions-row">
              <form onSubmit={handleSearchSubmit} className="person-search-form">
                <input
                  type="text"
                  className="filter-text-input"
                  aria-label="Otsi selle saadiku kõnesid"
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

              {uuid && (
                <a
                  href={`/rss/saadik/${uuid}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rss-feed-link"
                  title="Telli selle saadiku kõnede RSS-voog"
                >
                  <Rss size={13} aria-hidden="true" />
                  <span>Telli RSS-voog</span>
                </a>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* 2. Key Metrics as MP (Totals.mp) */}
      <section className="glass-panel" aria-label="Põhinäitajad saadikuna">
        <div
          className="chart-header"
          style={{
            marginBottom: "1.25rem",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-end",
            flexWrap: "wrap",
            gap: "0.75rem",
          }}
        >
          <div>
            <span className="section-kicker">PÕHINÄITAJAD SAADIKUNA</span>
            <h2 style={{ margin: 0, fontSize: "1.25rem" }}>Aktiivsus ja osalus Riigikogus</h2>
          </div>
          <label className="attendance-checkbox-label" style={{ margin: 0 }}>
            <input
              type="checkbox"
              checked={noInfotund}
              onChange={(e) => handleNoInfotundChange(e.target.checked)}
            />
            <span>Jäta infotunnid välja</span>
          </label>
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
          <div className="glass-panel person-metric-card">
            <span className="person-metric-label">Kõned saadikuna</span>
            <strong className="person-metric-value">
              {getMetricValue(stats?.totals?.mp?.speeches)}
            </strong>
            <span className="person-metric-desc">Põhiettekanded ja sõnavõtud</span>
          </div>

          <div className="glass-panel person-metric-card">
            <span className="person-metric-label">Küsimused ja repliigid</span>
            <strong className="person-metric-value">
              {getMetricValue(stats?.totals?.mp?.questions)}
            </strong>
            <span className="person-metric-desc">Lühisõnavõtud ja küsimused</span>
          </div>

          <div className="glass-panel person-metric-card">
            <span className="person-metric-label">Protseduurilised</span>
            <strong className="person-metric-value">
              {getMetricValue(stats?.totals?.mp?.procedural)}
            </strong>
            <span className="person-metric-desc">
              Protseduurilised küsimused ja ettepanekud istungi läbiviimise kohta
            </span>
          </div>

          <div className="glass-panel person-metric-card">
            <span className="person-metric-label">Kokku saadikuna</span>
            <strong className="person-metric-value person-metric-value-primary">
              {getMetricValue(stats?.totals?.mp?.total)}
            </strong>
            <span className="person-metric-desc">
              Kõik sõnavõtud saadikuna
              {hasUnclassified ? ` (sh ${stats.totals.mp.unclassified} liigitamata)` : ""}
            </span>
          </div>

          <div className="glass-panel person-metric-card">
            <span className="person-metric-label">Kõneaeg saadikuna</span>
            <strong className="person-metric-value">{formattedDuration}</strong>
            <span className="person-metric-desc">alates 14.09.2020</span>
          </div>

          <div className="glass-panel person-metric-card">
            <span className="person-metric-label">Registreerus kohalolekukontrollis</span>
            <strong className="person-metric-value">{formattedAttendance}</strong>
            <span className="person-metric-desc">
              {attendanceError
                ? "Kohaloleku andmed puuduvad"
                : attendance?.total_sessions > 0
                  ? `${attendance.present_sessions} / ${attendance.total_sessions} kontrollist`
                  : "Kohalolekukontrollid puuduvad"}
            </span>
          </div>

          <div className="glass-panel person-metric-card">
            <span className="person-metric-label">Osales hääletustel</span>
            <strong className="person-metric-value">{formattedVotes}</strong>
            <span className="person-metric-desc">
              {attendanceError ? (
                "Hääletuste andmed puuduvad"
              ) : attendance?.votes?.total > 0 ? (
                <>
                  <span>{`${attendance.votes.voted} / ${attendance.votes.total} hääletusest`}</span>
                  <span className="person-metric-subline">
                    {formatVoteSplit(
                      attendance.votes.not_voted,
                      attendance.votes.absent,
                      attendance.votes.total,
                      { decimals: 1 }
                    )}
                  </span>
                </>
              ) : (
                "Hääletused puuduvad"
              )}
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
                stenogrammis märgitud DIRECTOR-tüübina väljaspool istungi juhatamist. Kui juhataja
                juhatamise sõnavõtul pole stenogrammis rolli märgitud, loetakse see samuti
                liigitamata sõnavõtuks (neid on vähe, alla 0,1% juhatajate sõnavõttudest).
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

      {/* Role Breakdown Table (Koalitsioonis / Opositsioonis) */}
      {roleBreakdownRows.length > 0 && (
        <section className="glass-panel" aria-label="Koalitsioonis ja opositsioonis">
          <div className="chart-header" style={{ marginBottom: "0.75rem" }}>
            <div>
              <span className="section-kicker">VALITSUSE ROLL</span>
              <h2 style={{ margin: 0, fontSize: "1.25rem" }}>Koalitsioonis ja opositsioonis</h2>
            </div>
          </div>

          <div className="table-responsive-container">
            <table className="person-stats-table">
              <caption>Kohalolek ja hääletamine valitsuse koalitsioonis ja opositsioonis</caption>
              <thead>
                <tr>
                  <th scope="col" className="person-stats-col-text">
                    Roll
                  </th>
                  <th scope="col" className="person-stats-col-num">
                    Registreerus kontrollides
                  </th>
                  <th scope="col" className="person-stats-col-num">
                    Osales hääletustel
                  </th>
                  <th scope="col" className="person-stats-col-num">
                    Ei hääletanud
                  </th>
                  <th scope="col" className="person-stats-col-num">
                    Puudus
                  </th>
                </tr>
              </thead>
              <tbody>
                {roleBreakdownRows.map((row) => {
                  const checksTotal = row.total_sessions ?? 0;
                  const isChecksSmall = checksTotal < 50;
                  const votesTotal = row.votes?.total ?? 0;
                  const isVotesSmall = votesTotal < 50;
                  const notVotedCount = row.votes?.not_voted ?? 0;
                  const absentCount = row.votes?.absent ?? 0;
                  const notVotedPct = votesTotal > 0 ? (notVotedCount / votesTotal) * 100 : null;
                  const absentPct = votesTotal > 0 ? (absentCount / votesTotal) * 100 : null;

                  return (
                    <tr key={row.key}>
                      <th scope="row" className="person-stats-col-text" style={{ fontWeight: 600 }}>
                        {row.role}
                      </th>
                      <td className="person-stats-col-num">
                        {checksTotal > 0 ? (
                          <>
                            {formatMetricRatio(
                              row.attendance_percentage,
                              row.present_sessions,
                              checksTotal
                            )}
                            {isChecksSmall && <span className="att-sample-note">vähe andmeid</span>}
                          </>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="person-stats-col-num">
                        {votesTotal > 0 ? (
                          <>
                            {formatMetricRatio(row.votes?.voted_pct, row.votes?.voted, votesTotal)}
                            {isVotesSmall && <span className="att-sample-note">vähe andmeid</span>}
                          </>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="person-stats-col-num">
                        {votesTotal > 0 ? `${formatPercent(notVotedPct)} (${notVotedCount})` : "—"}
                      </td>
                      <td className="person-stats-col-num">
                        {votesTotal > 0 ? `${formatPercent(absentPct)} (${absentCount})` : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}

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
                <Legend
                  wrapperStyle={{ paddingTop: "10px" }}
                  formatter={(value) => <span style={{ color: colors.text }}>{value}</span>}
                />
                <Bar dataKey="speeches" name="Kõned" stackId="mp" fill={colors.series[0]} />
                <Bar
                  dataKey="questions"
                  name="Küsimused ja repliigid"
                  stackId="mp"
                  fill={colors.series[1]}
                />
                <Bar
                  dataKey="procedural"
                  name="Protseduurilised"
                  stackId="mp"
                  fill={colors.series[2]}
                />
                {hasUnclassified && (
                  <Bar
                    dataKey="unclassified"
                    name="Liigitamata"
                    stackId="mp"
                    fill={colors.series[3]}
                  />
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
                      {toRoman(membership)
                        ? `${toRoman(membership)} Riigikogu`
                        : `${membership}. koosseis`}
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
                        ? `${formatPercent(memAtt.attendance_percentage)} (${memAtt.present_sessions}/${memAtt.total_sessions})`
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* 5. Faction Majority Alignment Panel */}
      {showAlignmentPanel && (
        <section className="glass-panel" aria-label="Hääletamine fraktsiooni enamusega">
          <div className="chart-header" style={{ marginBottom: "1rem" }}>
            <div>
              <span className="section-kicker">HÄÄLETAMINE FRAKTSIOONIGA</span>
              <h2 style={{ margin: 0, fontSize: "1.25rem" }}>Hääletamine fraktsiooni enamusega</h2>
            </div>
          </div>

          {/* Koosseis switch */}
          {factionAlignment.by_membership && factionAlignment.by_membership.length > 0 && (
            <div
              className="segmented-control"
              role="group"
              aria-label="Fraktsiooni hääletuste koosseis"
              style={{ marginBottom: "1.25rem", flexWrap: "wrap" }}
            >
              <button
                type="button"
                aria-pressed={alignmentMembership === "all"}
                className={`segmented-btn ${alignmentMembership === "all" ? "active" : ""}`}
                onClick={() => handleAlignmentMembershipChange("all")}
              >
                <span>Kõik koosseisud</span>
              </button>
              {factionAlignment.by_membership.map((m) => (
                <button
                  key={m.membership}
                  type="button"
                  aria-pressed={alignmentMembership === String(m.membership)}
                  className={`segmented-btn ${alignmentMembership === String(m.membership) ? "active" : ""}`}
                  onClick={() => handleAlignmentMembershipChange(String(m.membership))}
                >
                  <span>
                    {toRoman(m.membership)
                      ? `${toRoman(m.membership)} Riigikogu`
                      : `${m.membership}. koosseis`}
                  </span>
                </button>
              ))}
            </div>
          )}

          {/* Main number */}
          <div className="alignment-main-stat">
            {alignmentComparable > 0 ? (
              <span className="alignment-main-text">
                Hääletas samamoodi kui fraktsiooni enamus:{" "}
                <strong className="person-metric-value-primary">
                  {formatPercent(factionAlignment.share_same)}
                </strong>{" "}
                ({factionAlignment.same} / {alignmentComparable} hääletust)
              </span>
            ) : (
              <span className="alignment-main-text">
                Selles koosseisus pole hääletusi, mida saaks fraktsiooni enamusega võrrelda.
              </span>
            )}
          </div>

          {/* Small line with excluded counts */}
          <p className="person-metric-desc" style={{ marginTop: "0.4rem", marginBottom: "1.5rem" }}>
            Välja arvatud: {factionAlignment.excluded?.absent ?? 0} puudumist,{" "}
            {factionAlignment.excluded?.split ?? 0} viigiseisu,{" "}
            {factionAlignment.excluded?.too_few ?? 0} alla 3 liikmega hääletust,{" "}
            {factionAlignment.excluded?.no_faction ?? 0} fraktsioonita.
          </p>

          {/* Differences list */}
          {alignmentComparable > 0 && (
            <div className="alignment-diffs-container">
              <h3
                style={{
                  fontSize: "1rem",
                  margin: "0 0 0.75rem 0",
                  color: "var(--text-secondary)",
                }}
              >
                Erinevad hääletused {totalDifferences > 0 ? `(${totalDifferences})` : ""}
              </h3>

              {differences.length === 0 ? (
                <p className="sidebar-empty-state">
                  {diffLoading ? "Laen erinevaid hääletusi…" : "Erinevaid hääletusi ei leitud."}
                </p>
              ) : (
                <div className="alignment-diffs-list">
                  {differences.map((diff) => (
                    <div key={diff.voting_uuid} className="alignment-diff-card">
                      <div className="alignment-diff-header">
                        <span className="alignment-diff-date">
                          {diff.sitting_date ? formatDate(diff.sitting_date) : "—"}
                        </span>
                        <div className="alignment-diff-links">
                          {diff.voting_uuid && (
                            <Link
                              to={`/haaletus/${diff.voting_uuid}`}
                              className="alignment-session-link"
                              title="Ava selle hääletuse detailvaade"
                            >
                              Vaata hääletust
                            </Link>
                          )}
                          {diff.sitting_date && (
                            <Link
                              to={`/istung/${diff.sitting_date}`}
                              className="alignment-session-link"
                              title="Ava selle päeva istungi stenogramm"
                            >
                              Vaata istungit
                            </Link>
                          )}
                        </div>
                      </div>
                      <div className="alignment-diff-desc">{diff.description || "Hääletus"}</div>
                      {diff.related_document_title && (
                        <div className="alignment-diff-doc">{diff.related_document_title}</div>
                      )}
                      <div className="alignment-diff-comparison">
                        <span className="alignment-diff-item">
                          Saadiku otsus:{" "}
                          <strong
                            className={`alignment-decision ${diff.member_decision?.toLowerCase()}`}
                          >
                            {formatDecision(diff.member_decision)}
                          </strong>
                        </span>
                        <span className="alignment-diff-separator">•</span>
                        <span className="alignment-diff-item">
                          Fraktsiooni enamus{diff.faction ? ` (${diff.faction})` : ""}:{" "}
                          <strong
                            className={`alignment-decision ${diff.faction_position?.toLowerCase()}`}
                          >
                            {formatDecision(diff.faction_position)}
                          </strong>
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {hasMoreDiffs && (
                <div className="alignment-load-more">
                  <button
                    type="button"
                    className="filter-search-btn"
                    onClick={handleLoadMoreDifferences}
                    disabled={diffLoading}
                  >
                    {diffLoading ? "Laen…" : "Näita rohkem"}
                  </button>
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {/* 6. Speeches List with Role Tabs & Pagination */}
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
            <p style={{ color: "var(--vote-against)" }}>
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
