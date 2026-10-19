import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import useSWR from "swr";
import { ArrowLeft, FileText, Info, Search, X } from "lucide-react";
import { fetchVoting } from "../lib/api";
import { formatDate } from "../lib/calendarUtils";
import {
  computeNotVoted,
  formatDecision,
  formatMajorityPosition,
  formatOvernightTime,
} from "../lib/votingUtils";

const DECISION_FILTER_OPTIONS = [
  { value: "ALL", label: "Kõik" },
  { value: "POOLT", label: "Poolt" },
  { value: "VASTU", label: "Vastu" },
  { value: "ERAPOOLETU", label: "Erapooletu" },
  { value: "EI_HAALETANUD", label: "Ei hääletanud" },
  { value: "PUUDUB", label: "Puudus" },
];

export function VotingView() {
  const { uuid } = useParams();
  const navigate = useNavigate();

  const [memberSearch, setMemberSearch] = useState("");
  const [decisionFilter, setDecisionFilter] = useState("ALL");
  const [sortField, setSortField] = useState("name");
  const [sortDir, setSortDir] = useState("asc");

  const {
    data: voting,
    error,
    isLoading,
  } = useSWR(uuid ? `voting-${uuid}` : null, () => fetchVoting(uuid), {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });

  useEffect(() => {
    const prevTitle = document.title;
    if (voting?.description) {
      document.title = `${voting.description} — Riigivaade`;
    }
    return () => {
      document.title = prevTitle;
    };
  }, [voting?.description]);

  const handleBack = () => {
    if (window.history.length > 1) {
      navigate(-1);
    } else {
      navigate("/haaletused");
    }
  };

  const handleSort = (field) => {
    if (sortField === field) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir("asc");
    }
  };

  const getSortIndicator = (field) => {
    if (sortField !== field) return "";
    return sortDir === "asc" ? " ↑" : " ↓";
  };

  const getAriaSort = (field) => {
    if (sortField !== field) return "none";
    return sortDir === "asc" ? "ascending" : "descending";
  };

  const votes = voting?.votes;

  const filteredVotes = useMemo(() => {
    if (!votes) return [];
    let list = [...votes];

    if (memberSearch.trim()) {
      const q = memberSearch.trim().toLowerCase();
      list = list.filter((v) => (v.member_name || "").toLowerCase().includes(q));
    }

    if (decisionFilter && decisionFilter !== "ALL") {
      list = list.filter((v) => v.decision === decisionFilter);
    }

    list.sort((a, b) => {
      let cmp = 0;
      if (sortField === "name") {
        cmp = (a.member_name || "").localeCompare(b.member_name || "", "et");
      } else if (sortField === "faction") {
        cmp = (a.faction || "").localeCompare(b.faction || "", "et");
      } else if (sortField === "decision") {
        const order = { POOLT: 1, VASTU: 2, ERAPOOLETU: 3, EI_HAALETANUD: 4, PUUDUB: 5 };
        cmp = (order[a.decision] || 99) - (order[b.decision] || 99);
      }
      if (cmp === 0) {
        cmp = (a.member_name || "").localeCompare(b.member_name || "", "et");
      }
      return sortDir === "asc" ? cmp : -cmp;
    });

    return list;
  }, [votes, memberSearch, decisionFilter, sortField, sortDir]);

  if (isLoading) {
    return (
      <div
        className="glass-panel"
        style={{ padding: "3rem", textAlign: "center", marginTop: "1rem" }}
      >
        <p style={{ color: "var(--text-secondary)" }}>Laen hääletuse andmeid...</p>
      </div>
    );
  }

  if (error || !voting) {
    const is404 =
      error?.status === 404 ||
      error?.message?.includes("kood 404") ||
      error?.message?.includes("Hääletust ei leitud") ||
      (!error && !voting);

    return (
      <div
        className="glass-panel"
        style={{ padding: "3rem 1.5rem", textAlign: "center", marginTop: "1rem" }}
      >
        <h2 style={{ marginBottom: "0.5rem" }}>
          {is404 ? "Hääletust ei leitud" : "Hääletuse laadimine ebaõnnestus."}
        </h2>
        <p style={{ color: "var(--text-secondary)", marginBottom: "1.5rem" }}>
          {error?.message ||
            (is404
              ? "Hääletust sellise identifikaatoriga ei leitud."
              : "Hääletuse andmete laadimine ebaõnnestus.")}
        </p>
        <Link
          to="/haaletused"
          className="search-button"
          style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}
        >
          <ArrowLeft size={16} aria-hidden="true" />
          Tagasi hääletuste nimekirja
        </Link>
      </div>
    );
  }

  const timeDisplay = formatOvernightTime(voting.start_time, voting.sitting_date, voting.date);
  const isSecret = voting.type === "SALAJANE";
  const notVotedCount = computeNotVoted(voting.totals);

  return (
    <div className="voting-detail-container">
      <div className="voting-detail-header glass-panel">
        <div className="voting-header-top">
          <button type="button" className="back-nav-btn" onClick={handleBack}>
            &larr; Tagasi
          </button>
          <div className="voting-badges">
            {isSecret && <span className="voting-badge voting-badge-secret">Salajane</span>}
            {voting.is_technical && (
              <span className="voting-badge voting-badge-technical">Tehniline</span>
            )}
          </div>
        </div>

        <h1 className="voting-detail-title">{voting.description}</h1>

        {voting.related_document && (
          <div className="voting-related-doc">
            <FileText size={16} className="voting-doc-icon" aria-hidden="true" />
            {voting.related_document.type === "DRAFT" && voting.related_document.uuid ? (
              <Link to={`/eelnou/${voting.related_document.uuid}`} className="voting-doc-link">
                {voting.related_document.reference ? `${voting.related_document.reference} · ` : ""}
                {voting.related_document.title}
              </Link>
            ) : (
              <span className="voting-doc-text">
                {voting.related_document.reference ? `${voting.related_document.reference} · ` : ""}
                {voting.related_document.title}
              </span>
            )}
          </div>
        )}

        <div className="voting-meta-row">
          {voting.sitting_date && (
            <Link to={`/istung/${voting.sitting_date}`} className="voting-sitting-link">
              Istung {formatDate(voting.sitting_date)}
            </Link>
          )}
          {timeDisplay && <span className="voting-meta-item">Kell {timeDisplay}</span>}
          {voting.chairman_name && (
            <span className="voting-meta-item">Juhataja: {voting.chairman_name}</span>
          )}
        </div>

        {voting.is_technical && voting.note && (
          <div className="voting-technical-callout">
            <Info size={16} aria-hidden="true" />
            <span>{voting.note}</span>
          </div>
        )}
      </div>

      <section className="voting-totals-section" aria-label="Hääletuse koondtulemused">
        <div className="voting-totals-grid">
          <div className="voting-total-card poolt">
            <span className="voting-total-count">{voting.totals?.in_favor ?? 0}</span>
            <span className="voting-total-label">Poolt</span>
          </div>
          <div className="voting-total-card vastu">
            <span className="voting-total-count">{voting.totals?.against ?? 0}</span>
            <span className="voting-total-label">Vastu</span>
          </div>
          <div className="voting-total-card erapooletu">
            <span className="voting-total-count">{voting.totals?.neutral ?? 0}</span>
            <span className="voting-total-label">Erapooletu</span>
          </div>
          <div className="voting-total-card ei_haaletanud">
            <span className="voting-total-count">{notVotedCount}</span>
            <span className="voting-total-label">Ei hääletanud</span>
          </div>
          <div className="voting-total-card puudus">
            <span className="voting-total-count">{voting.totals?.absent ?? 0}</span>
            <span className="voting-total-label">Puudus</span>
          </div>
        </div>
      </section>

      {isSecret ? (
        <div className="voting-secret-callout glass-panel">
          <p>Salajane hääletus – nimelisi hääli ei avaldata.</p>
        </div>
      ) : (
        <>
          {Array.isArray(voting.by_faction) && voting.by_faction.length > 0 && (
            <section
              className="voting-factions-section glass-panel"
              aria-labelledby="factions-heading"
            >
              <h2 id="factions-heading" className="voting-section-heading">
                Fraktsioonide tulemused
              </h2>
              <div className="voting-table-scroll">
                <table className="voting-factions-table">
                  <thead>
                    <tr>
                      <th scope="col" className="col-faction">
                        Fraktsioon
                      </th>
                      <th scope="col" className="col-num">
                        Poolt
                      </th>
                      <th scope="col" className="col-num">
                        Vastu
                      </th>
                      <th scope="col" className="col-num">
                        Erapooletu
                      </th>
                      <th scope="col" className="col-num">
                        Ei hääletanud
                      </th>
                      <th scope="col" className="col-num">
                        Puudus
                      </th>
                      <th scope="col" className="col-majority">
                        Enamuse seisukoht
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {voting.by_faction.map((fac) => (
                      <tr key={fac.faction}>
                        <td className="col-faction-name">{fac.faction}</td>
                        <td className="col-num">{fac.in_favor}</td>
                        <td className="col-num">{fac.against}</td>
                        <td className="col-num">{fac.neutral}</td>
                        <td className="col-num">{fac.not_voted}</td>
                        <td className="col-num">{fac.absent}</td>
                        <td className="col-majority-val">
                          {fac.majority_position ? (
                            <span
                              className={`voting-decision-badge ${fac.majority_position.toLowerCase()}`}
                            >
                              {formatMajorityPosition(fac.majority_position)}
                            </span>
                          ) : (
                            "—"
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          <section className="voting-members-section glass-panel" aria-labelledby="members-heading">
            <div className="voting-members-header">
              <h2 id="members-heading" className="voting-section-heading">
                Saadikute hääled
                <span className="results-badge">
                  {filteredVotes.length} / {voting.votes?.length || 0}
                </span>
              </h2>

              <div className="voting-members-controls">
                <div className="filter-input-wrap voting-member-search-wrap">
                  <Search className="filter-search-icon" aria-hidden="true" />
                  <input
                    type="text"
                    className="filter-text-input"
                    placeholder="Otsi saadiku nime järgi"
                    value={memberSearch}
                    onChange={(e) => setMemberSearch(e.target.value)}
                  />
                  {memberSearch && (
                    <button
                      type="button"
                      className="filter-clear-icon-btn"
                      onClick={() => setMemberSearch("")}
                      title="Tühjenda otsing"
                    >
                      <X size={14} aria-hidden="true" />
                    </button>
                  )}
                </div>

                <div className="voting-decision-tabs" role="group" aria-label="Otsuse filter">
                  {DECISION_FILTER_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      type="button"
                      aria-pressed={decisionFilter === opt.value}
                      className={`decision-tab-btn ${decisionFilter === opt.value ? "active" : ""}`}
                      onClick={() => setDecisionFilter(opt.value)}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {filteredVotes.length === 0 ? (
              <p
                style={{
                  color: "var(--text-secondary)",
                  margin: "1.5rem 0",
                  textAlign: "center",
                }}
              >
                Saadikuid ei leitud.
              </p>
            ) : (
              <div className="voting-table-scroll">
                <table className="voting-members-table">
                  <thead>
                    <tr>
                      <th scope="col" aria-sort={getAriaSort("name")}>
                        <button
                          type="button"
                          className="voting-sort-th-btn"
                          onClick={() => handleSort("name")}
                        >
                          Saadik{getSortIndicator("name")}
                        </button>
                      </th>
                      <th scope="col" aria-sort={getAriaSort("faction")}>
                        <button
                          type="button"
                          className="voting-sort-th-btn"
                          onClick={() => handleSort("faction")}
                        >
                          Fraktsioon{getSortIndicator("faction")}
                        </button>
                      </th>
                      <th scope="col" aria-sort={getAriaSort("decision")}>
                        <button
                          type="button"
                          className="voting-sort-th-btn"
                          onClick={() => handleSort("decision")}
                        >
                          Otsus{getSortIndicator("decision")}
                        </button>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredVotes.map((v) => (
                      <tr key={v.member_uuid || v.member_name}>
                        <td className="col-member-name">
                          {v.member_uuid ? (
                            <Link to={`/saadik/${v.member_uuid}`} className="voting-member-link">
                              {v.member_name || "Tundmatu saadik"}
                            </Link>
                          ) : (
                            v.member_name || "Tundmatu saadik"
                          )}
                        </td>
                        <td className="col-member-faction">{v.faction || "Fraktsioonita"}</td>
                        <td className="col-member-decision">
                          <span className={`voting-decision-badge ${v.decision?.toLowerCase()}`}>
                            {formatDecision(v.decision)}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}

export default VotingView;
