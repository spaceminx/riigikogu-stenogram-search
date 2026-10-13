import React, { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import useSWR from "swr";
import { fetchAttendance, fetchFactionAttendance, fetchFactionsList } from "../lib/api";
import { formatFactionName } from "../lib/formatters";
import AttendanceMembersTable from "../components/AttendanceMembersTable";
import AttendanceFactionsTable from "../components/AttendanceFactionsTable";

export function AttendanceView({ memberships = [] }) {
  const [searchParams, setSearchParams] = useSearchParams();

  const attendanceTab = searchParams.get("att_tab") || "members";
  const attendanceMembership = searchParams.get("att_membership") || "15";
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
    if (newPeriod === "15") {
      next.delete("att_membership");
    } else {
      next.set("att_membership", String(newPeriod));
      next.delete("att_active");
    }
    next.delete("att_faction");
    setSearchParams(next, { replace: true });
  };

  const {
    data: attendanceData,
    error,
    isLoading: loading,
  } = useSWR(
    ["attendance", attendanceMembership, selectedFaction, activeOnly],
    () =>
      Promise.all([
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
      ]),
    { revalidateOnFocus: false, shouldRetryOnError: false }
  );

  const attendanceStats = useMemo(() => attendanceData?.[0] || [], [attendanceData]);
  const factionStats = useMemo(() => attendanceData?.[1] || [], [attendanceData]);
  const attendanceFactionsList = attendanceData?.[2] || [];

  const [sortConfig, setSortConfig] = useState({
    key: "present_sessions",
    direction: "descending",
  });
  const [factionSortConfig, setFactionSortConfig] = useState({
    key: "attendance_percentage",
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

  return (
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
