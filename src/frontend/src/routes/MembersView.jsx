import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import useSWR from "swr";
import { Search, X } from "lucide-react";
import { fetchFactions } from "../lib/api";
import { formatFactionName } from "../lib/formatters";
import { buildMemberRows, filterMemberRows, memberCountText } from "../lib/membersUtils";
import { usePageMeta } from "../lib/usePageMeta";

const URL_SYNC_MS = 250;

// "(XV Riigikogu, 2023–praegu)", as on the factions page
function membershipLabel(info) {
  if (!info) return "";
  const startYear = info.start_date?.slice(0, 4) ?? "";
  const endYear = info.is_current ? "praegu" : (info.end_date?.slice(0, 4) ?? "");
  const years = startYear && endYear ? `, ${startYear}–${endYear}` : "";
  return `(${info.name}${years})`;
}

// No photos here: api.riigikogu.ee answers about one request per second per IP and the rest of a
// hundred thumbnails got 429 (shown as broken images). The person page loads just the one.
function MemberRow({ row }) {
  return (
    <tr>
      <td className="members-col-name">
        <span className="members-name-text">
          <Link to={`/saadik/${encodeURIComponent(row.uuid)}`} className="members-name-link">
            {row.fullName}
          </Link>
          {/* On narrow screens the faction and district columns fold under the name */}
          <span className="members-name-meta">
            {formatFactionName(row.faction)}
            {row.district && ` · ${row.district}`}
          </span>
        </span>
      </td>
      <td className="members-col-faction">
        {formatFactionName(row.faction)}
        {row.formerFactions.length > 0 && (
          <span className="members-former">
            varem: {row.formerFactions.map(formatFactionName).join(", ")}
          </span>
        )}
      </td>
      <td className="members-col-district">{row.district}</td>
    </tr>
  );
}

export function MembersView({ memberships = [], membershipsLoading = false }) {
  usePageMeta(
    "Saadikud — Riigivaade",
    "Riigikogu liikmed koosseisude kaupa: otsi saadikut nime järgi ja ava tema kõned, hääletused ja kohalolek."
  );

  const [searchParams, setSearchParams] = useSearchParams();

  const todayStr = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const defaultMembership = useMemo(() => {
    if (!memberships || memberships.length === 0) return null;
    const started = memberships.find((m) => m.start_date && m.start_date <= todayStr);
    return started ? String(started.id) : String(memberships[0].id);
  }, [memberships, todayStr]);
  const membershipParam = searchParams.get("sd_membership");
  const membership = membershipParam || defaultMembership || "";
  const isCurrentMembership = Boolean(defaultMembership && membership === defaultMembership);
  const membershipInfo = memberships.find((m) => String(m.id) === String(membership));

  // The filters live in local state and reach the URL a moment later: the router updates the
  // URL asynchronously, so inputs bound to it straight away dropped typed letters
  const [query, setQuery] = useState(() => searchParams.get("sd_q") || "");
  const [faction, setFaction] = useState(() => searchParams.get("sd_faction") || "");
  const [showAll, setShowAll] = useState(() => searchParams.get("sd_all") === "1");
  // Former members only make sense to hide in the current membership
  const currentOnly = isCurrentMembership && !showAll;

  // setSearchParams changes identity with every URL change; as an effect dependency it rewrote
  // the URL every URL_SYNC_MS and kept the page re-rendering. Read the latest values from refs.
  const urlRef = useRef({ searchParams, setSearchParams });
  useEffect(() => {
    urlRef.current = { searchParams, setSearchParams };
  });

  useEffect(() => {
    const wanted = { sd_q: query.trim(), sd_faction: faction, sd_all: showAll ? "1" : "" };
    const timer = setTimeout(() => {
      const { searchParams: prev, setSearchParams: set } = urlRef.current;
      const next = new URLSearchParams(prev);
      for (const [key, value] of Object.entries(wanted)) {
        if (value) next.set(key, value);
        else next.delete(key);
      }
      if (next.toString() !== prev.toString()) set(next, { replace: true });
    }, URL_SYNC_MS);
    return () => clearTimeout(timer);
  }, [query, faction, showAll]);

  const handleMembershipChange = (value) => {
    setFaction("");
    setShowAll(false);
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (defaultMembership && value === defaultMembership) next.delete("sd_membership");
        else next.set("sd_membership", value);
        return next;
      },
      { replace: true }
    );
  };

  const reqMembership =
    membershipParam || (membershipsLoading ? undefined : defaultMembership || undefined);

  const { data, error, isLoading } = useSWR(
    reqMembership ? ["factions", reqMembership] : null,
    () => fetchFactions({ membership: reqMembership }),
    { revalidateOnFocus: false, shouldRetryOnError: false }
  );

  const rows = useMemo(() => buildMemberRows(data?.factions ?? []), [data]);
  const factionNames = useMemo(() => (data?.factions ?? []).map((f) => f.faction), [data]);
  const scoped = useMemo(() => filterMemberRows(rows, { currentOnly }), [rows, currentOnly]);
  const visible = useMemo(
    () => filterMemberRows(rows, { query, faction, currentOnly }),
    [rows, query, faction, currentOnly]
  );
  const filtered = Boolean(query || faction);

  if (membershipsLoading && (!memberships || memberships.length === 0)) {
    return (
      <div className="glass-panel" style={{ marginTop: "0.5rem" }}>
        <p className="sidebar-empty-state">Laen koosseisude andmeid…</p>
      </div>
    );
  }

  return (
    <div className="glass-panel members-view" style={{ marginTop: "0.5rem" }}>
      <div className="chart-header" style={{ marginBottom: "0.5rem" }}>
        <h2 style={{ margin: 0 }}>Saadikud {membershipLabel(membershipInfo)}</h2>
      </div>

      <p className="attendance-page-intro">
        Riigikogu liikmed koosseisu kaupa. Ava saadik, et näha tema kõnesid, hääletusi ja
        kohalolekut. Fraktsioon on see, kuhu saadik kuulub praegu (lõppenud koosseisus viimati).
      </p>

      <div className="attendance-filter-bar">
        <div className="attendance-controls-row members-controls">
          <div className="filter-input-wrap members-search-wrap">
            <Search className="filter-search-icon" aria-hidden="true" />
            <input
              type="search"
              className="filter-text-input"
              aria-label="Otsi saadikut nime järgi"
              placeholder="Otsi saadikut nime järgi"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            {query && (
              <button
                type="button"
                className="filter-clear-icon-btn"
                onClick={() => setQuery("")}
                aria-label="Tühjenda otsing"
              >
                <X aria-hidden="true" />
              </button>
            )}
          </div>

          <div className="attendance-select-group">
            <label htmlFor="members-period-select" className="attendance-label">
              Koosseis:
            </label>
            <select
              id="members-period-select"
              className="attendance-select"
              value={membership}
              onChange={(e) => handleMembershipChange(e.target.value)}
            >
              {memberships.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name || `${m.id}. Riigikogu`}
                </option>
              ))}
            </select>
          </div>

          <div className="attendance-select-group">
            <label htmlFor="members-faction-select" className="attendance-label">
              Fraktsioon:
            </label>
            <select
              id="members-faction-select"
              className="attendance-select"
              value={faction}
              onChange={(e) => setFaction(e.target.value)}
            >
              <option value="">Kõik</option>
              {factionNames.map((name) => (
                <option key={name} value={name}>
                  {formatFactionName(name)}
                </option>
              ))}
            </select>
          </div>

          {isCurrentMembership && (
            <label className="members-checkbox">
              <input
                type="checkbox"
                checked={currentOnly}
                onChange={(e) => setShowAll(!e.target.checked)}
              />
              Ainult praegused saadikud
            </label>
          )}
        </div>
      </div>

      {error && (
        <div className="error-banner" style={{ margin: "1rem 0" }}>
          <div className="error-content">
            <span className="error-icon">!</span>
            <span>{error?.message || "Saadikute andmete laadimine ebaõnnestus."}</span>
          </div>
        </div>
      )}

      {isLoading || (!data && !error) ? (
        <div className="empty-state" style={{ padding: "3rem 1rem" }}>
          <p>Laadin saadikute andmeid...</p>
        </div>
      ) : data ? (
        <>
          <p className="members-count" aria-live="polite">
            {filtered
              ? `Leitud ${visible.length} / ${memberCountText(scoped.length)}`
              : memberCountText(visible.length)}
          </p>
          {visible.length === 0 ? (
            <p className="empty-state">Sellise nimega saadikut ei leitud.</p>
          ) : (
            <div className="members-list" role="region" aria-label="Saadikute nimekiri">
              <table className="members-table">
                <caption className="attendance-table-caption">Riigikogu liikmed</caption>
                <thead>
                  <tr>
                    <th scope="col" className="members-col-name">
                      Nimi
                    </th>
                    <th scope="col" className="members-col-faction">
                      Fraktsioon
                    </th>
                    <th scope="col" className="members-col-district">
                      Ringkond
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((row) => (
                    <MemberRow key={row.uuid} row={row} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}

export default MembersView;
