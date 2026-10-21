import React from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import useSWR from "swr";
import { ArrowLeft, Calendar, ExternalLink, ListOrdered, Video } from "lucide-react";
import { fetchSpeech } from "../lib/api";
import { formatDate } from "../lib/calendarUtils";
import {
  formatDateTime,
  formatDuration,
  formatFactionName,
  normalizeSourceUrl,
  SPEECH_TYPE_LABELS,
} from "../lib/formatters";
import { usePageMeta } from "../lib/usePageMeta";
import VideoEmbed from "../components/VideoEmbed";

export function SpeechView() {
  const { id } = useParams();
  const location = useLocation();
  const navigate = useNavigate();

  const {
    data: speech,
    error,
    isLoading: loading,
  } = useSWR(id ? `speech-${id}` : null, () => fetchSpeech(id), {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });

  const speakerName = speech?.speaker || "";
  const formattedDate = speech?.date ? formatDate(speech.date) : "";
  const pageTitle =
    speakerName && formattedDate
      ? `${speakerName}, ${formattedDate} — Riigivaade`
      : speakerName
        ? `${speakerName} — Riigivaade`
        : "Kõne — Riigivaade";
  const pageDesc =
    speakerName && formattedDate
      ? `Riigikogu saadiku ${speakerName} sõnavõtt ${formattedDate} toimunud istungil.`
      : "Riigikogu istungil peetud kõne stenogramm ja salvestis.";

  usePageMeta(pageTitle, pageDesc);

  const publicSpeechId = speech ? (speech.external_id ?? speech.speech_key) : null;

  const handleBack = () => {
    if (location.key === "default" || window.history.length <= 1) {
      if (speech?.date && publicSpeechId) {
        navigate(`/istung/${speech.date}#speech-${publicSpeechId}`);
      } else if (speech?.date) {
        navigate(`/istung/${speech.date}`);
      } else {
        navigate("/");
      }
    } else {
      navigate(-1);
    }
  };

  if (loading) {
    return (
      <div
        className="glass-panel"
        style={{ padding: "3rem", textAlign: "center", marginTop: "1rem" }}
      >
        <p style={{ color: "var(--color-text-muted, #64748b)" }}>Laen kõne andmeid...</p>
      </div>
    );
  }

  if (error || !speech) {
    return (
      <div
        className="glass-panel"
        style={{ padding: "3rem 1.5rem", textAlign: "center", marginTop: "1rem" }}
      >
        <h2 style={{ marginBottom: "0.5rem" }}>Kõnet ei leitud</h2>
        <p style={{ color: "var(--color-text-muted, #64748b)", marginBottom: "1.5rem" }}>
          {error?.message || "Kõnet sellise identifikaatoriga ei leitud."}
        </p>
        <Link
          to="/"
          className="search-button"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.5rem",
            textDecoration: "none",
          }}
        >
          <ArrowLeft size={16} />
          <span>Tagasi avalehele</span>
        </Link>
      </div>
    );
  }

  const speechTypeLabel = SPEECH_TYPE_LABELS[speech.speech_type];
  const durationText = formatDuration(speech.duration_seconds);

  return (
    <div style={{ marginTop: "1rem" }}>
      <div style={{ marginBottom: "1rem", display: "flex", alignItems: "center", gap: "1rem" }}>
        <button
          type="button"
          className="back-nav-btn"
          onClick={handleBack}
          title="Mine tagasi eelmisele lehele"
        >
          &larr; Tagasi
        </button>
        <nav
          aria-label="Leivapuru"
          style={{ fontSize: "0.85rem", color: "var(--color-text-muted, #64748b)" }}
        >
          <Link to="/" style={{ color: "inherit", textDecoration: "none" }}>
            Avaleht
          </Link>
          <span style={{ margin: "0 0.5rem" }}>/</span>
          <Link to={`/istung/${speech.date}`} style={{ color: "inherit", textDecoration: "none" }}>
            Istung {speech.date}
          </Link>
          <span style={{ margin: "0 0.5rem" }}>/</span>
          <span>Kõne #{publicSpeechId}</span>
        </nav>
      </div>

      <article className="glass-panel speech-card" style={{ padding: "2rem" }}>
        <header className="speech-meta" style={{ marginBottom: "1.5rem" }}>
          <div className="speaker-header-info">
            <h1 className="speaker-name-highlight" style={{ fontSize: "1.5rem", margin: 0 }}>
              {speech.speaker_uuid ? (
                <Link
                  to={`/saadik/${encodeURIComponent(speech.speaker_uuid)}`}
                  className="speaker-name-link"
                >
                  {speech.speaker}
                </Link>
              ) : (
                speech.speaker
              )}
            </h1>
            {speech.speaker_role && <span className="speaker-role-tag">{speech.speaker_role}</span>}
            {speechTypeLabel && (
              <span className="speaker-role-tag speech-type-badge">{speechTypeLabel}</span>
            )}
            {durationText && (
              <span className="speaker-role-tag speech-duration-badge">{durationText}</span>
            )}
            {speech.speaker_faction && (
              <span className="faction-badge">{formatFactionName(speech.speaker_faction)}</span>
            )}
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              color: "var(--color-text-muted, #64748b)",
            }}
          >
            <Calendar size={14} aria-hidden="true" />
            <span className="speech-datetime">{formatDateTime(speech.date, speech.time)}</span>
          </div>
        </header>

        {speech.agenda_title && (
          <div
            className="speech-agenda-tag"
            style={{ marginBottom: "1.5rem", fontSize: "0.95rem" }}
          >
            <span className="agenda-kicker">Päevakord:</span>
            {speech.draft_uuid && (
              <Link
                to={`/eelnou/${speech.draft_uuid}`}
                className="agenda-draft-link"
                title="Ava eelnõu leht"
              >
                Eelnõu
              </Link>
            )}
            <span className="agenda-title-text">{speech.agenda_title}</span>
          </div>
        )}

        {speech.video_url && (
          <div style={{ marginBottom: "1.5rem" }}>
            <VideoEmbed
              videoUrl={speech.video_url}
              durationSeconds={speech.duration_seconds}
              speaker={speech.speaker}
              date={speech.date ? formatDate(speech.date) : ""}
              showExternalLink={false}
            />
          </div>
        )}

        <div
          className="speech-text"
          style={{
            fontSize: "1.05rem",
            lineHeight: 1.75,
            whiteSpace: "pre-wrap",
            margin: "1.5rem 0 2rem 0",
          }}
        >
          {speech.text}
        </div>

        <footer
          className="speech-card-actions"
          style={{ borderTop: "1px solid var(--color-border-subtle, #e2e8f0)", paddingTop: "1rem" }}
        >
          <Link
            to={`/istung/${speech.date}${publicSpeechId ? `#speech-${publicSpeechId}` : ""}`}
            className="context-btn"
            title="Vaata kõnet terve istungi kontekstis"
          >
            <ListOrdered size={14} aria-hidden="true" style={{ marginRight: "0.4rem" }} />
            <span>Vaata istungi kontekstis</span>
          </Link>

          <div className="speech-card-links">
            {speech.video_url && (
              <a
                href={speech.video_url}
                target="_blank"
                rel="noopener noreferrer"
                className="speech-video-link"
                title="Vaata kõnet YouTube'is alates selle algusest"
              >
                <Video size={14} aria-hidden="true" />
                <span>Vaata videot</span>
              </a>
            )}

            <a
              href={normalizeSourceUrl(speech.source_url)}
              target="_blank"
              rel="noopener noreferrer"
              className="speech-link"
              title="Ava Riigikogu algne stenogramm"
            >
              <span>Ava allikas</span>
              <ExternalLink size={14} aria-hidden="true" />
            </a>
          </div>
        </footer>
      </article>
    </div>
  );
}

export default SpeechView;
