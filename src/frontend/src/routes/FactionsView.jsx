import React, { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import useSWR from "swr";
import { fetchFactions } from "../lib/api";
import { formatDate } from "../lib/calendarUtils";
import { formatFactionName } from "../lib/formatters";
import {
  ROLE_LABELS,
  filterFactionsByRole,
  formatPeriods,
  getSeatCounts,
  getSeatSegments,
  isFullTerm,
  splitMembers,
} from "../lib/factionsUtils";
import VoteBar from "../components/VoteBar";
import { usePageMeta } from "../lib/usePageMeta";

function memberCountText(count) {
  return `${count} ${count === 1 ? "saadik" : "saadikut"}`;
}

function MemberItem({ member, showPeriods }) {
  return (
    <li className="faction-member">
      <Link to={`/saadik/${encodeURIComponent(member.uuid)}`} className="faction-member-name">
        {member.full_name}
      </Link>
      {member.electoral_district && (
        <span className="faction-member-meta">{member.electoral_district}</span>
      )}
      {showPeriods && member.periods?.length > 0 && (
        <span className="faction-member-meta">{formatPeriods(member.periods)}</span>
      )}
    </li>
  );
}

function FactionCard({ faction, isCurrentMembership, membershipInfo, attendanceLink }) {
  const { current, former } = splitMembers(faction);
  const listed = isCurrentMembership ? current : faction.members;
  const shortName = formatFactionName(faction.faction);
  const headingId = `faction-${faction.faction.replace(/\s+/g, "-").toLowerCase()}`;
  const showsPeriods = (member) =>
    !isFullTerm(member, membershipInfo?.start_date, membershipInfo?.end_date);

  return (
    <section className="faction-card" aria-labelledby={headingId}>
      <header className="faction-card-header">
        <div className="faction-card-titles">
          <h3 id={headingId} className="faction-card-title">
            {shortName}
          </h3>
          {shortName !== faction.faction && (
            <span className="faction-card-fullname">{faction.faction}</span>
          )}
        </div>
        <div className="faction-card-facts">
          {isCurrentMembership && ROLE_LABELS[faction.role] && (
            <span className="faction-badge">{ROLE_LABELS[faction.role]}</span>
          )}
          <span className="faction-card-count">
            {isCurrentMembership
              ? memberCountText(current.length)
              : `${faction.members.length} liiget koosseisu jooksul`}
          </span>
        </div>
      </header>

      {listed.length > 0 ? (
        <ul className="faction-member-list">
          {listed.map((member) => (
            <MemberItem key={member.uuid} member={member} showPeriods={showsPeriods(member)} />
          ))}
        </ul>
      ) : (
        <p className="faction-card-empty">Praegu pole selles fraktsioonis ühtegi saadikut.</p>
      )}

      {isCurrentMembership && former.length > 0 && (
        <details className="faction-former">
          <summary>Varem selles fraktsioonis ({former.length})</summary>
          <ul className="faction-member-list">
            {former.map((member) => (
              <MemberItem key={member.uuid} member={member} showPeriods />
            ))}
          </ul>
        </details>
      )}

      <Link to={attendanceLink} className="faction-card-link">
        {shortName} kohalolek &rarr;
      </Link>
    </section>
  );
}

function GovernmentSummary({ data, seatCounts }) {
  const government = data.government;
  if (!government) return null;
  const sources = Array.isArray(government.source) ? government.source : [government.source];
  const total = seatCounts.coalition + seatCounts.opposition + seatCounts.none;

  return (
    <div className="factions-government">
      <p className="factions-government-line">
        {data.is_current_membership
          ? "Valitsus: "
          : `Valitsus koosseisu viimasel päeval (${formatDate(data.date)}): `}
        <strong>{government.name}</strong>
        {data.is_current_membership && ` (alates ${formatDate(government.from)})`}
        {" · "}
        {sources.map((url, index) => (
          <React.Fragment key={url}>
            {index > 0 && ", "}
            <a href={url} target="_blank" rel="noreferrer">
              allikas{sources.length > 1 ? ` ${index + 1}` : ""}
            </a>
          </React.Fragment>
        ))}
      </p>
      {data.is_current_membership && total > 0 && (
        <div className="factions-seats">
          <p className="factions-seats-line">
            Koalitsioonis {seatCounts.coalition}, opositsioonis {seatCounts.opposition}
            {seatCounts.none > 0 && `, fraktsiooni mittekuuluvaid ${seatCounts.none}`} · kokku{" "}
            {memberCountText(total)}
          </p>
          <VoteBar segments={getSeatSegments(seatCounts)} />
          <div className="att-bar-legend" aria-hidden="true">
            <span className="att-bar-legend-item">
              <span className="att-bar-legend-swatch vote-bar-coalition" />
              Koalitsioon
            </span>
            <span className="att-bar-legend-item">
              <span className="att-bar-legend-swatch vote-bar-opposition" />
              Opositsioon
            </span>
            {seatCounts.none > 0 && (
              <span className="att-bar-legend-item">
                <span className="att-bar-legend-swatch vote-bar-nonaligned" />
                Fraktsiooni mittekuuluvad
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function FactionsView({ memberships = [], membershipsLoading = false }) {
  usePageMeta(
    "Fraktsioonid — Riigivaade",
    "Riigikogu fraktsioonid ja nende liikmed koosseisude kaupa, koos valitsuskoalitsiooni jaotusega."
  );

  const [searchParams, setSearchParams] = useSearchParams();

  const todayStr = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const defaultMembership = useMemo(() => {
    if (!memberships || memberships.length === 0) return null;
    const started = memberships.find((m) => m.start_date && m.start_date <= todayStr);
    return started ? String(started.id) : String(memberships[0].id);
  }, [memberships, todayStr]);
  const membershipParam = searchParams.get("fr_membership");
  const membership = membershipParam || defaultMembership || "";
  const membershipInfo = memberships.find((m) => String(m.id) === String(membership));
  const isCurrentMembership = Boolean(defaultMembership && membership === defaultMembership);
  // On by default for the current membership; fr_active=0 in the URL turns it off
  const activeOnly = isCurrentMembership && searchParams.get("fr_active") !== "0";
  // A past membership had several governments, so one role per faction would mislead
  const role = isCurrentMembership ? searchParams.get("role") || "" : "";

  const updateParam = (key, value) => {
    const next = new URLSearchParams(searchParams);
    if (value) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    setSearchParams(next, { replace: true });
  };

  const handlePeriodChange = (newPeriod) => {
    const next = new URLSearchParams(searchParams);
    if (defaultMembership && String(newPeriod) === defaultMembership) {
      next.delete("fr_membership");
    } else {
      next.set("fr_membership", String(newPeriod));
      next.delete("fr_active");
      next.delete("role");
    }
    setSearchParams(next, { replace: true });
  };

  const reqMembership =
    membershipParam || (membershipsLoading ? undefined : defaultMembership || undefined);

  const { data, error, isLoading } = useSWR(
    reqMembership ? ["factions", reqMembership, activeOnly ? "1" : "0"] : null,
    () => fetchFactions({ membership: reqMembership, activeOnly }),
    { revalidateOnFocus: false, shouldRetryOnError: false }
  );

  const factions = useMemo(() => data?.factions ?? [], [data]);
  const visibleFactions = useMemo(() => filterFactionsByRole(factions, role), [factions, role]);
  const seatCounts = useMemo(() => getSeatCounts(factions), [factions]);

  const attendanceLinkFor = (factionName) => {
    const params = new URLSearchParams({ att_faction: factionName });
    if (!isCurrentMembership) params.set("att_membership", membership);
    return `/kohalolek?${params.toString()}`;
  };

  if (membershipsLoading && (!memberships || memberships.length === 0)) {
    return (
      <div className="glass-panel" style={{ marginTop: "0.5rem" }}>
        <p className="sidebar-empty-state">Laen koosseisude andmeid…</p>
      </div>
    );
  }

  return (
    <div className="glass-panel factions-view" style={{ marginTop: "0.5rem" }}>
      <div className="chart-header" style={{ marginBottom: "0.5rem" }}>
        <h2 style={{ margin: 0 }}>
          Fraktsioonid{" "}
          {membershipInfo &&
            (() => {
              const startYear = membershipInfo.start_date?.slice(0, 4) ?? "";
              const endYear = membershipInfo.is_current
                ? "praegu"
                : (membershipInfo.end_date?.slice(0, 4) ?? "");
              const years = startYear && endYear ? `, ${startYear}–${endYear}` : "";
              return `(${membershipInfo.name}${years})`;
            })()}
        </h2>
      </div>

      <p className="attendance-page-intro">
        Riigikogu liikmed fraktsioonide kaupa Riigikogu avaandmete põhjal. Andmed näitavad
        fraktsiooni, mitte erakonna liikmesust. Uus või naasev liige on mõne päeva fraktsiooni
        mittekuuluv, kuni fraktsioon ta vastu võtab; neid lühikesi perioode siin ei näidata.
      </p>

      <div className="attendance-filter-bar">
        <div className="attendance-controls-row">
          <div className="attendance-select-group">
            <label htmlFor="factions-period-select" className="attendance-label">
              Periood:
            </label>
            <select
              id="factions-period-select"
              className="attendance-select"
              value={membership}
              onChange={(e) => handlePeriodChange(e.target.value)}
            >
              {memberships.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name || `${m.id}. Riigikogu`}
                </option>
              ))}
            </select>
          </div>

          {isCurrentMembership && (
            <div className="attendance-select-group">
              <label htmlFor="factions-role-select" className="attendance-label">
                Roll:
              </label>
              <select
                id="factions-role-select"
                className="attendance-select"
                value={role}
                onChange={(e) => updateParam("role", e.target.value)}
              >
                <option value="">Kõik</option>
                <option value="coalition">Koalitsioonis</option>
                <option value="opposition">Opositsioonis</option>
              </select>
            </div>
          )}

          {isCurrentMembership && (
            <label className="attendance-checkbox-label">
              <input
                type="checkbox"
                checked={activeOnly}
                onChange={(e) => updateParam("fr_active", e.target.checked ? null : "0")}
              />
              <span>Ainult praegu aktiivsed saadikud</span>
            </label>
          )}
        </div>
      </div>

      {error && (
        <div className="error-banner" style={{ margin: "1rem 0" }}>
          <div className="error-content">
            <span className="error-icon">!</span>
            <span>{error?.message || "Fraktsioonide andmete laadimine ebaõnnestus."}</span>
          </div>
        </div>
      )}

      {isLoading || (!data && !error) ? (
        <div className="empty-state" style={{ padding: "3rem 1rem" }}>
          <p>Laadin fraktsioonide andmeid...</p>
        </div>
      ) : data ? (
        <>
          <GovernmentSummary data={data} seatCounts={seatCounts} />
          {visibleFactions.length === 0 ? (
            <p className="empty-state">Fraktsioonide andmeid ei leitud.</p>
          ) : (
            <div className="factions-list">
              {visibleFactions.map((faction) => (
                <FactionCard
                  key={faction.faction}
                  faction={faction}
                  isCurrentMembership={data.is_current_membership}
                  membershipInfo={membershipInfo}
                  attendanceLink={attendanceLinkFor(faction.faction)}
                />
              ))}
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}

export default FactionsView;
