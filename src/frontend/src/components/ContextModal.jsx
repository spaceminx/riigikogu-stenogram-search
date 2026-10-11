import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ExternalLink, Video, FileText } from "lucide-react";
import {
  formatDateTime,
  formatDuration,
  formatFactionName,
  highlightKeywords,
  normalizeSourceUrl,
  SPEECH_TYPE_LABELS,
} from "../lib/formatters";

export function ContextModal({ activeSpeechContext, onClose, groups = [[]] }) {
  const [contextSearchTerm, setContextSearchTerm] = useState("");
  const targetSpeechRef = useRef(null);

  useEffect(() => {
    if (!activeSpeechContext) return;
    const handleKeyDown = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [activeSpeechContext, onClose]);

  useEffect(() => {
    if (activeSpeechContext && targetSpeechRef.current) {
      targetSpeechRef.current.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }
  }, [activeSpeechContext]);

  if (!activeSpeechContext) return null;

  const speeches = activeSpeechContext.speeches || [];
  const filteredSpeeches = speeches.filter((s) => {
    if (!contextSearchTerm.trim()) return true;
    const term = contextSearchTerm.toLowerCase();
    return (
      (s.speaker && s.speaker.toLowerCase().includes(term)) ||
      (s.text && s.text.toLowerCase().includes(term))
    );
  });

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal-content glass-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="context-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-top-bar">
          <div>
            <h2 id="context-modal-title" className="modal-heading">
              Istungi ajajoon ja kontekst
            </h2>
            <div className="modal-meta-row">
              <span>{formatDateTime(activeSpeechContext.date, activeSpeechContext.time)}</span>
              <span>•</span>
              <span>{activeSpeechContext.total_speeches} kõnet/repliiki</span>
              {activeSpeechContext.source_url && (
                <>
                  <span>•</span>
                  <a
                    href={normalizeSourceUrl(activeSpeechContext.source_url)}
                    target="_blank"
                    rel="noreferrer"
                    className="modal-source-link"
                  >
                    <span>Algallikas</span>
                    <ExternalLink size={12} aria-hidden="true" />
                  </a>
                </>
              )}
            </div>
          </div>
          <button
            type="button"
            className="modal-close-icon-btn"
            onClick={onClose}
            title="Sulge aken (ESC)"
          >
            &times;
          </button>
        </div>

        <div className="modal-filter-wrap">
          <input
            type="text"
            className="modal-search-input"
            placeholder="Otsi sellest istungist (esineja või märksõna)..."
            value={contextSearchTerm}
            onChange={(e) => setContextSearchTerm(e.target.value)}
          />
        </div>

        <div className="modal-speeches-scroll">
          {filteredSpeeches.map((speech) => {
            const isTarget = speech.id === activeSpeechContext.target_speech_id;
            return (
              <div
                key={speech.id}
                ref={isTarget ? targetSpeechRef : null}
                className={`transcript-speech-row ${isTarget ? "target-speech-highlight" : ""}`}
              >
                <div className="transcript-row-header">
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.5rem",
                      flexWrap: "wrap",
                    }}
                  >
                    <span className="transcript-row-speaker">{speech.speaker}</span>
                    {speech.speaker_role && (
                      <span className="speaker-role-tag">{speech.speaker_role}</span>
                    )}
                    {SPEECH_TYPE_LABELS[speech.speech_type] && (
                      <span className="speaker-role-tag speech-type-badge">
                        {SPEECH_TYPE_LABELS[speech.speech_type]}
                      </span>
                    )}
                    {formatDuration(speech.duration_seconds) && (
                      <span className="speaker-role-tag speech-duration-badge">
                        {formatDuration(speech.duration_seconds)}
                      </span>
                    )}
                    {speech.speaker_faction && (
                      <span className="faction-badge">
                        {formatFactionName(speech.speaker_faction)}
                      </span>
                    )}
                    {speech.agenda_title && (
                      <span className="transcript-agenda-badge" title={speech.agenda_title}>
                        {speech.agenda_title}
                      </span>
                    )}
                    {isTarget && <span className="target-speech-badge">Otsitud kõne</span>}
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    {(speech.external_id ?? speech.speech_key) && (
                      <Link
                        to={`/kone/${speech.external_id ?? speech.speech_key}`}
                        className="transcript-video-btn"
                        title="Ava eraldi kõne lehel"
                        onClick={onClose}
                      >
                        <FileText size={13} aria-hidden="true" />
                        <span>Leht</span>
                      </Link>
                    )}
                    {speech.video_url && (
                      <a
                        href={speech.video_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="transcript-video-btn"
                        title="Vaata kõnet videost alates selle algusest"
                      >
                        <Video size={13} aria-hidden="true" />
                        <span>Video</span>
                      </a>
                    )}
                  </div>
                </div>
                <div className="transcript-row-text">
                  {highlightKeywords(speech.text, groups, contextSearchTerm, speech.matched_words)}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default ContextModal;
