import React, { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import useSWR from "swr";
import { fetchAttendance, fetchFactionAttendance, fetchFactionsList } from "../lib/api";
import { formatFactionName } from "../lib/formatters";
import AttendanceMembersTable from "../components/AttendanceMembersTable";
import AttendanceFactionsTable from "../components/AttendanceFactionsTable";

export function AttendanceView({
  memberships = [],
  membershipsLoading = false,
  onOpenMethodology,
}) {
  const [searchParams, setSearchParams] = useSearchParams();

  const attendanceTab = searchParams.get("att_tab") || "members";
  const latestMembership = memberships && memberships.length > 0 ? String(memberships[0].id) : null;
  const attParam = searchParams.get("att_membership");
  const attendanceMembership = attParam || latestMembership || "";
  const selectedFaction = searchParams.get("att_faction") || "";
  const activeOnly =
    searchParams.get("att_active") === "1" || searchParams.get("att_active") === "true";

  const updateParam = (key, value) => {
    const next = new URLSearchParams(searchParams);
    if (value === null || value === undefined || value === "" || value === false) {
      next.delete(key);
    } else if (value === true) {
      next.set(key, "1");
    } else {
      next.set(key, String(value));
    }
    setSearchParams(next, { replace: true });
  };

  const setAttendanceTab = (tab) => updateParam("att_tab", tab === "members" ? null : tab);
  const setSelectedFaction = (f) => updateParam("att_faction", f || null);
  const setActiveOnly = (a) => updateParam("att_active", a || null);

  const handlePeriodChange = (newPeriod) => {
    const next = new URLSearchParams(searchParams);
    if (latestMembership && String(newPeriod) === latestMembership) {
      next.delete("att_membership");
    } else {
      next.set("att_membership", String(newPeriod));
      next.delete("att_active");
    }
    next.delete("att_faction");
    setSearchParams(next, { replace: true });
  };

  const reqMembership = attParam || latestMembership || undefined;

  const {
    data: attendanceData,
    error,
    isLoading: loading,
  } = useSWR(
    ["attendance", reqMembership || "latest", selectedFaction, activeOnly],
    () =>
      Promise.all([
        fetchAttendance({
          membership: reqMembership,
          faction: selectedFaction || null,
          activeOnly,
        }),
        fetchFactionAttendance({
          membership: reqMembership,
          activeOnly,
        }),
        fetchFactionsList(reqMembership),
      ]),
    { revalidateOnFocus: false, shouldRetryOnError: false }
  );

  const attendanceStats = useMemo(() => attendanceData?.[0] || [], [attendanceData]);
  const factionStats = useMemo(() => attendanceData?.[1] || [], [attendanceData]);
  const attendanceFactionsList = attendanceData?.[2] || [];

  const [sortConfig, setSortConfig] = useState({
    key: "votes_voted_pct",
    direction: "descending",
  });
  const [factionSortConfig, setFactionSortConfig] = useState({
    key: "votes_voted_pct",
    direction: "descending",
  });

  const requestSort = (key) => {
    let direction = "ascending";
    if (sortConfig.key === key && sortConfig.direction === "ascending") {
      direction = "descending";
    }
    setSortConfig({ key, direction });
  };

  const requestFactionSort = (key) => {
    let direction = "ascending";
    if (factionSortConfig.key === key && factionSortConfig.direction === "ascending") {
      direction = "descending";
    }
    setFactionSortConfig({ key, direction });
  };

  const handleSelectFactionDrilldown = (factionName) => {
    const next = new URLSearchParams(searchParams);
    next.set("att_faction", factionName);
    next.delete("att_tab");
    setSearchParams(next, { replace: true });
  };

  const sortedStats = useMemo(() => {
    let sortableItems = [...attendanceStats];
    if (sortConfig.key) {
      sortableItems.sort((a, b) => {
        const valA = a[sortConfig.key];
        const valB = b[sortConfig.key];

        if (valA == null && valB == null) return 0;
        if (valA == null) return 1;
        if (valB == null) return -1;

        if (valA < valB) {
          return sortConfig.direction === "ascending" ? -1 : 1;
        }
        if (valA > valB) {
          return sortConfig.direction === "ascending" ? 1 : -1;
        }
        if (sortConfig.key === "votes_voted_pct") {
          return (b.votes_voted ?? 0) - (a.votes_voted ?? 0);
        }
        if (sortConfig.key === "registered_pct") {
          return (b.registered_checks ?? 0) - (a.registered_checks ?? 0);
        }
        return (b.present_sessions ?? 0) - (a.present_sessions ?? 0);
      });
    }
    return sortableItems;
  }, [attendanceStats, sortConfig]);

  const sortedFactionStats = useMemo(() => {
    let sortableItems = [...factionStats];
    if (factionSortConfig.key) {
      sortableItems.sort((a, b) => {
        const valA = a[factionSortConfig.key];
        const valB = b[factionSortConfig.key];

        if (valA == null && valB == null) return 0;
        if (valA == null) return 1;
        if (valB == null) return -1;

        if (valA < valB) {
          return factionSortConfig.direction === "ascending" ? -1 : 1;
        }
        if (valA > valB) {
          return factionSortConfig.direction === "ascending" ? 1 : -1;
        }
        if (factionSortConfig.key === "votes_voted_pct") {
          return (b.votes_voted ?? 0) - (a.votes_voted ?? 0);
        }
        if (factionSortConfig.key === "registered_pct") {
          return (b.registered_checks ?? 0) - (a.registered_checks ?? 0);
        }
        return 0;
      });
    }
    return sortableItems;
  }, [factionStats, factionSortConfig]);

  if (membershipsLoading && (!memberships || memberships.length === 0)) {
    return (
      <div className="glass-panel" style={{ marginTop: "0.5rem" }}>
        <p className="sidebar-empty-state">Laen koosseisude andmeid…</p>
      </div>
    );
  }

  return (
    <div className="glass-panel" style={{ marginTop: "0.5rem" }}>
      <div className="chart-header" style={{ marginBottom: "0.5rem" }}>
        <h2 style={{ margin: 0 }}>
          Kohaloleku statistika{" "}
          {(() => {
            const m = memberships.find((x) => String(x.id) === String(attendanceMembership));
            if (m) {
              const startYear = m.start_date ? m.start_date.slice(0, 4) : "";
              const endYear = m.is_current ? "praegu" : m.end_date ? m.end_date.slice(0, 4) : "";
              const years = startYear && endYear ? `, ${startYear}–${endYear}` : "";
              return `(${m.name}${years})`;
            }
            return attendanceMembership === "all" ? "(2019–praegu)" : "";
          })()}
        </h2>
      </div>

      <p className="attendance-page-intro">
        Kohalolekut näidatakse kahe eraldi mõõdikuna: registreerumine kohalolekukontrollides ning
        osalemine avalikel hääletustel.{" "}
        {onOpenMethodology && (
          <button type="button" className="attendance-intro-link" onClick={onOpenMethodology}>
            Loe metoodika kohta
          </button>
        )}
      </p>

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
              onChange={(e) => handlePeriodChange(e.target.value)}
            >
              {memberships.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name || `${m.id}. Riigikogu`}
                </option>
              ))}
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

          {Boolean(latestMembership && attendanceMembership === latestMembership) && (
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

      {error && (
        <div className="error-banner" style={{ margin: "1rem 0" }}>
          <div className="error-content">
            <span className="error-icon">!</span>
            <span>{error?.message || "Kohaloleku andmete laadimine ebaõnnestus."}</span>
          </div>
        </div>
      )}

      {loading ? (
        <div className="empty-state" style={{ padding: "3rem 1rem" }}>
          <p>Laadin kohaloleku andmeid...</p>
        </div>
      ) : attendanceTab === "members" ? (
        <AttendanceMembersTable
          sortedStats={sortedStats}
          sortConfig={sortConfig}
          requestSort={requestSort}
        />
      ) : (
        <AttendanceFactionsTable
          sortedFactionStats={sortedFactionStats}
          factionSortConfig={factionSortConfig}
          requestFactionSort={requestFactionSort}
          onSelectFaction={handleSelectFactionDrilldown}
        />
      )}
    </div>
  );
}

export default AttendanceView;
