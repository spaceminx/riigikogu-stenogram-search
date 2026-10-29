import React, { useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import useSWR from "swr";
import { ArrowLeft, Calendar, ExternalLink } from "lucide-react";
import { fetchDraft, fetchDraftSpeeches } from "../lib/api";
import { formatDate } from "../lib/calendarUtils";
import {
  formatStageLabel,
  getOtherVotings,
  getRiigikoguDraftUrl,
  groupVotingsByReading,
  sortReadingsByDate,
} from "../lib/draftUtils";
import VotingRow from "../components/VotingRow";
import SpeechCard from "../components/SpeechCard";
import { usePageMeta } from "../lib/usePageMeta";

function ReadingCard({ reading, draftUuid }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [speeches, setSpeeches] = useState([]);
  const [totalSpeeches, setTotalSpeeches] = useState(reading.speech_count || 0);
  const [isLoadingSpeeches, setIsLoadingSpeeches] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasLoaded, setHasLoaded] = useState(false);
  const [speechError, setSpeechError] = useState(null);

  const stageLabel = formatStageLabel(reading.stage, reading.decision_value);
  const decisionText =
    reading.decision_value && reading.decision_value !== stageLabel ? reading.decision_value : null;

  const speechCount = reading.speech_count ?? 0;

  const handleToggleSpeeches = async () => {
    if (isExpanded) {
      setIsExpanded(false);
      return;
    }

    setIsExpanded(true);

    if (!hasLoaded && reading.agenda_item_uuid) {
      setIsLoadingSpeeches(true);
      setSpeechError(null);
      try {
        const data = await fetchDraftSpeeches(draftUuid, {
          agendaItemUuid: reading.agenda_item_uuid,
          limit: 50,
          offset: 0,
        });
        setSpeeches(data.results || []);
        setTotalSpeeches(data.total ?? (data.results ? data.results.length : 0));
        setHasLoaded(true);
      } catch (err) {
        setSpeechError(err.message || "Sõnavõttude laadimine ebaõnnestus.");
      } finally {
        setIsLoadingSpeeches(false);
      }
    }
  };

  const handleLoadMore = async () => {
    if (isLoadingMore || !reading.agenda_item_uuid) return;
    setIsLoadingMore(true);
    setSpeechError(null);
    try {
      const data = await fetchDraftSpeeches(draftUuid, {
        agendaItemUuid: reading.agenda_item_uuid,
        limit: 50,
        offset: speeches.length,
      });
      const newResults = data.results || [];
      setSpeeches((prev) => [...prev, ...newResults]);
      if (data.total !== undefined) {
        setTotalSpeeches(data.total);
      }
    } catch (err) {
      setSpeechError(err.message || "Rohkemate sõnavõttude laadimine ebaõnnestus.");
    } finally {
      setIsLoadingMore(false);
    }
  };

  return (
    <article className="reading-card glass-panel">
      <header className="reading-card-header">
        <div className="reading-card-title-row">
          {reading.sitting_date && (
            <Link
              to={`/istung/${reading.sitting_date}`}
              className="reading-date-link"
              title="Ava istungi täisprotokoll"
            >
              <Calendar size={15} aria-hidden="true" />
              <span>{formatDate(reading.sitting_date)}</span>
            </Link>
          )}
          {stageLabel && <span className="reading-stage-badge">{stageLabel}</span>}
        </div>
        {decisionText && <div className="reading-decision-text">{decisionText}</div>}
      </header>

      {reading.votings && reading.votings.length > 0 && (
        <div className="reading-votings-block">
          <div className="reading-votings-list">
            {reading.votings.map((voting) => (
              <VotingRow key={voting.uuid} voting={voting} showDate={false} showDocument={false} />
            ))}
          </div>
        </div>
      )}

      <footer className="reading-card-footer">
        {speechCount > 0 ? (
          <button
            type="button"
            className="reading-speeches-toggle-btn"
            onClick={handleToggleSpeeches}
            aria-expanded={isExpanded}
          >
            {isExpanded ? `Peida sõnavõtud (${speechCount})` : `Sõnavõtud (${speechCount})`}
          </button>
        ) : (
          <button type="button" className="reading-speeches-toggle-btn disabled" disabled>
            Sõnavõtud (0)
          </button>
        )}

        {isExpanded && (
          <div className="reading-speeches-container">
            {isLoadingSpeeches && (
              <div className="reading-speeches-loading">
                <p>Laen sõnavõtte...</p>
              </div>
            )}

            {speechError && (
              <div className="reading-speeches-error">
                <p>{speechError}</p>
                <button
                  type="button"
                  className="retry-btn"
                  onClick={() => {
                    setHasLoaded(false);
                    handleToggleSpeeches();
                  }}
                >
                  Proovi uuesti
                </button>
              </div>
            )}

            {!isLoadingSpeeches && !speechError && speeches.length > 0 && (
              <div className="reading-speeches-list">
                {speeches.map((speech) => (
                  <SpeechCard key={speech.id} speech={speech} mode="session" />
                ))}
              </div>
            )}

            {!isLoadingSpeeches && !speechError && hasLoaded && speeches.length === 0 && (
              <div className="reading-speeches-empty">
                <p>Sõnavõtud puuduvad.</p>
              </div>
            )}

            {!isLoadingSpeeches && speeches.length < totalSpeeches && (
              <div className="reading-speeches-more-wrap">
                <button
                  type="button"
                  className="reading-speeches-more-btn"
                  onClick={handleLoadMore}
                  disabled={isLoadingMore}
                >
                  {isLoadingMore ? "Laen..." : "Näita rohkem"}
                </button>
              </div>
            )}
          </div>
        )}
      </footer>
    </article>
  );
}

export function DraftView() {
  const { uuid } = useParams();
  const location = useLocation();
  const navigate = useNavigate();

  const {
    data: draft,
    error,
    isLoading,
  } = useSWR(uuid ? `draft-${uuid}` : null, () => fetchDraft(uuid), {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });

  const draftTitle = draft?.title ? `${draft.title} — Riigivaade` : "Eelnõu — Riigivaade";
  const draftDesc = draft?.title
    ? `Riigikogu eelnõu ${draft.mark ? `${draft.mark} ` : ""}„${draft.title}“ lugemised, arutelud ja seotud hääletused.`
    : "Riigikogu eelnõu käik, lugemised ja seotud hääletused.";
  usePageMeta(draftTitle, draftDesc);

  const handleBack = () => {
    if (location.key === "default" || window.history.length <= 1) {
      navigate("/haaletused");
    } else {
      navigate(-1);
    }
  };

  const sortedReadings = useMemo(() => {
    if (!draft?.readings) return [];
    const sorted = sortReadingsByDate(draft.readings);
    return groupVotingsByReading(sorted, draft.votings || []);
  }, [draft]);

  const otherVotings = useMemo(() => {
    if (!draft) return [];
    return getOtherVotings(draft.readings || [], draft.votings || []);
  }, [draft]);

  if (isLoading) {
    return (
      <div
        className="glass-panel"
        style={{ padding: "3rem", textAlign: "center", marginTop: "1rem" }}
      >
        <p style={{ color: "var(--text-secondary)" }}>Laen eelnõu andmeid...</p>
      </div>
    );
  }

  if (error || !draft) {
    const is404 =
      error?.status === 404 ||
      error?.message?.includes("404") ||
      error?.message?.includes("Eelnõud ei leitud") ||
      (!error && !draft);

    return (
      <div
        className="glass-panel"
        style={{ padding: "3rem 1.5rem", textAlign: "center", marginTop: "1rem" }}
      >
        <h1 className="detail-error-title">
          {is404 ? "Eelnõud ei leitud" : "Eelnõu laadimine ebaõnnestus."}
        </h1>
        <p style={{ color: "var(--text-secondary)", marginBottom: "1.5rem" }}>
          {error?.message ||
            (is404
              ? "Eelnõud sellise identifikaatoriga ei leitud."
              : "Eelnõu andmete laadimine ebaõnnestus.")}
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

  const externalUrl = getRiigikoguDraftUrl(draft.uuid);

  return (
    <div className="draft-detail-container">
      <div className="draft-detail-header glass-panel">
        <div className="draft-header-top">
          <button type="button" className="back-nav-btn" onClick={handleBack}>
            &larr; Tagasi
          </button>
          {draft.mark && <span className="draft-mark-badge">{draft.mark}</span>}
        </div>

        <h1 className="draft-detail-title">{draft.title}</h1>

        <div className="draft-meta-row">
          {externalUrl && (
            <a
              href={externalUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="draft-external-link"
            >
              <span>Eelnõu Riigikogu lehel</span>
              <ExternalLink size={14} aria-hidden="true" />
            </a>
          )}
        </div>
      </div>

      <section className="draft-readings-section">
        <h2 className="draft-section-title">Lugemised ja arutelud</h2>
        {sortedReadings.length > 0 ? (
          <div className="draft-readings-list">
            {sortedReadings.map((reading, index) => (
              <ReadingCard
                key={reading.agenda_item_uuid || `reading-${index}`}
                reading={reading}
                draftUuid={draft.uuid}
              />
            ))}
          </div>
        ) : (
          <div className="glass-panel" style={{ padding: "1.5rem", textAlign: "center" }}>
            <p style={{ color: "var(--text-secondary)", margin: 0 }}>
              Selle eelnõu lugemisi ega arutelusid ei leitud.
            </p>
          </div>
        )}
      </section>

      {otherVotings.length > 0 && (
        <section className="draft-other-votings-section">
          <h2 className="draft-section-title">Muud hääletused</h2>
          <div className="votings-list">
            {otherVotings.map((voting) => (
              <VotingRow key={voting.uuid} voting={voting} showDate={true} showDocument={false} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

export default DraftView;
