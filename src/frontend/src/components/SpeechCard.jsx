import React from "react";
import { Link } from "react-router-dom";
import { ExternalLink, Video, FileText } from "lucide-react";
import {
  formatDateTime,
  formatDuration,
  formatFactionName,
  getSnippet,
  highlightKeywords,
  normalizeSourceUrl,
  SPEECH_TYPE_LABELS,
} from "../lib/formatters";

export function SpeechCard({
  speech,
  mode = "search", // "search" | "session"
  groups = [[]],
  searchTerm = "",
  isTarget = false,
  onOpenContext,
  cardRef,
}) {
  const speechTypeLabel = SPEECH_TYPE_LABELS[speech.speech_type];
  const durationText = formatDuration(speech.duration_seconds);
  const publicSpeechId = speech.external_id ?? speech.speech_key;

  return (
    <div
      id={publicSpeechId ? `speech-${publicSpeechId}` : undefined}
      ref={cardRef}
      className={`glass-panel speech-card ${isTarget ? "target-speech-highlight" : ""}`}
    >
      <div className="speech-meta">
        <div className="speaker-header-info">
          {speech.speaker_uuid ? (
            <Link
              to={`/saadik/${encodeURIComponent(speech.speaker_uuid)}`}
              className="speaker-name-highlight speaker-name-link"
            >
              {speech.speaker}
            </Link>
          ) : (
            <span className="speaker-name-highlight">{speech.speaker}</span>
          )}
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
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <span className="speech-datetime">{formatDateTime(speech.date, speech.time)}</span>
          {mode === "session" && publicSpeechId && (
            <a
              href={`#speech-${publicSpeechId}`}
              className="speech-anchor-link"
              title="Kopeeri kõne otselink"
            >
              #
            </a>
          )}
        </div>
      </div>

      {speech.agenda_title && (
        <div className="speech-agenda-tag" title={speech.agenda_title}>
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

      <p className="speech-text">
        {mode === "search"
          ? highlightKeywords(
              getSnippet(speech.text, speech.matched_words || [], groups),
              groups,
              searchTerm,
              speech.matched_words || []
            )
          : highlightKeywords(speech.text, groups, searchTerm, speech.matched_words || [])}
      </p>

      <div className="speech-card-actions">
        {mode === "search" && onOpenContext ? (
          <button
            type="button"
            className="context-btn"
            onClick={() => onOpenContext(speech.id)}
            title="Ava terve istungi ajajoon ja vaata kõnet selle loomulikus kontekstis"
          >
            {speech.count !== undefined && speech.count !== null
              ? `Vaata tervet istungit (${speech.count} mainimist)`
              : "Vaata kõne konteksti"}
          </button>
        ) : (
          <Link
            to={`/istung/${speech.date}${publicSpeechId ? `#speech-${publicSpeechId}` : ""}`}
            className="context-btn"
            title="Vaata selle istungi täisprotokolli"
          >
            Terve istung
          </Link>
        )}

        <div className="speech-card-links">
          {publicSpeechId && (
            <Link
              to={`/kone/${publicSpeechId}`}
              className="speech-link"
              title="Ava kõne eraldi lehel"
            >
              <FileText size={14} aria-hidden="true" />
              <span>Kõne leht</span>
            </Link>
          )}

          {speech.video_url && (
            <a
              href={speech.video_url}
              target="_blank"
              rel="noopener noreferrer"
              className="speech-video-link"
              title="Vaata kõnet YouTube'is alates kõne algusest"
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
      </div>
    </div>
  );
}

export default SpeechCard;
