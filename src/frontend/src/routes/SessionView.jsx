import React, { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import useSWR from "swr";
import { ExternalLink } from "lucide-react";
import { fetchPlenarySession, fetchVotings } from "../lib/api";
import { formatDateTime, normalizeSourceUrl } from "../lib/formatters";
import SpeechCard from "../components/SpeechCard";
import VotingRow from "../components/VotingRow";

export function SessionView() {
  const { date } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const targetElementRef = useRef(null);
  const [showAllVotings, setShowAllVotings] = useState(false);

  const {
    data: sessionData,
    error,
    isLoading: loading,
  } = useSWR(date ? `session-${date}` : null, () => fetchPlenarySession(date), {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });

  const { data: votingsData } = useSWR(
    date ? `session-votings-${date}` : null,
    () => fetchVotings({ sittingDate: date, limit: 100 }),
    {
      revalidateOnFocus: false,
      shouldRetryOnError: false,
    }
  );
  const votings = votingsData?.results || [];
  const displayedVotings = votings.length > 5 && !showAllVotings ? votings.slice(0, 5) : votings;

  // Handle anchor scrolling on load and when hash changes
  useEffect(() => {
    if (!loading && sessionData && location.hash) {
      const targetId = location.hash.replace("#", "");
      const el = document.getElementById(targetId);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }
  }, [loading, sessionData, location.hash]);

  const handleBack = () => {
    if (location.key === "default" || window.history.length <= 1) {
      navigate("/");
    } else {
      navigate(-1);
    }
  };

  const targetSpeechAnchor = location.hash.startsWith("#speech-")
    ? location.hash.replace("#speech-", "")
    : null;

  const speeches = sessionData?.results || [];

  return (
    <div style={{ marginTop: "0.5rem" }}>
      <div className="glass-panel" style={{ marginBottom: "1rem" }}>
        <div className="chart-header speeches-header-bar">
          <div className="speeches-header-heading">
            <button className="back-nav-btn" onClick={handleBack}>
              &larr; Tagasi
            </button>
            <h2 className="speeches-view-title">
              Istungi kõned · {formatDateTime(date)}
              {sessionData && (
                <span className="results-badge">
                  {(sessionData.count || speeches.length).toLocaleString("et-EE")} tk
                </span>
              )}
            </h2>
          </div>

          {sessionData?.source_url && (
            <div className="export-actions-wrap">
              <a
                href={normalizeSourceUrl(sessionData.source_url)}
                target="_blank"
                rel="noreferrer"
                className="export-btn-link"
                title="Ava Riigikogu algne stenogramm"
              >
                <span>Riigikogu allikas</span>
                <ExternalLink size={13} style={{ marginLeft: "4px" }} aria-hidden="true" />
              </a>
            </div>
          )}
        </div>
      </div>

      {votings.length > 0 && (
        <section
          className="session-votings-section glass-panel"
          style={{ marginBottom: "1.5rem", padding: "1.5rem" }}
          aria-labelledby="session-votings-title"
        >
          <div className="session-votings-header" style={{ marginBottom: "1rem" }}>
            <h3
              id="session-votings-title"
              style={{ margin: 0, fontSize: "1.25rem", fontWeight: 600 }}
            >
              Hääletused ({votings.length})
            </h3>
          </div>
          <div className="votings-list">
            {displayedVotings.map((voting) => (
              <VotingRow key={voting.uuid} voting={voting} showDate={false} />
            ))}
          </div>
          {votings.length > 5 && !showAllVotings && (
            <div style={{ marginTop: "1rem", textAlign: "center" }}>
              <button
                type="button"
                className="filter-search-btn"
                onClick={() => setShowAllVotings(true)}
              >
                Näita kõiki hääletusi ({votings.length})
              </button>
            </div>
          )}
        </section>
      )}

      {loading && (
        <div className="glass-panel" style={{ padding: "3rem", textAlign: "center" }}>
          <p style={{ color: "var(--text-secondary)" }}>Laen istungi stenogrammi...</p>
        </div>
      )}

      {error && (
        <div className="error-banner">
          <div className="error-content">
            <span className="error-icon">!</span>
            <span>{error?.message || "Istungi stenogrammi laadimine ebaõnnestus."}</span>
          </div>
          <Link to="/" className="back-nav-btn" style={{ marginLeft: "auto" }}>
            Tagasi töölauale
          </Link>
        </div>
      )}

      {!loading && !error && speeches.length === 0 && (
        <div className="glass-panel" style={{ padding: "3rem", textAlign: "center" }}>
          <p style={{ color: "var(--text-secondary)" }}>Sellel kuupäeval stenogramme ei leitud.</p>
        </div>
      )}

      {!loading && !error && speeches.length > 0 && (
        <div className="speeches-list">
          {speeches.map((speech) => {
            const publicSpeechId =
              speech.external_id != null
                ? String(speech.external_id)
                : speech.speech_key
                  ? String(speech.speech_key)
                  : null;
            const isTarget = Boolean(
              targetSpeechAnchor && publicSpeechId && publicSpeechId === targetSpeechAnchor
            );
            return (
              <SpeechCard
                key={speech.id}
                speech={speech}
                mode="session"
                isTarget={isTarget}
                cardRef={isTarget ? targetElementRef : null}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

export default SessionView;
