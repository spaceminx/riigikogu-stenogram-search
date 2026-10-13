import React from "react";
import { Link } from "react-router-dom";
import { formatFactionName } from "../lib/formatters";

export function SpeakersPanel({
  speakers = [],
  showingArchiveSpeakers = false,
  overviewError = false,
}) {
  const maxCount = Math.max(...speakers.map((s) => Number(s.count || 0)), 1);

  return (
    <section className="glass-panel members-panel" aria-labelledby="members-title">
      <div className="chart-header">
        <div>
          <span className="section-kicker">ARUTELUDE PÕHJAL</span>
          <h2 id="members-title">Aktiivseimad kõnelejad</h2>
        </div>
        <span className="member-total">{speakers.length || "—"}</span>
      </div>
      {speakers.length > 0 ? (
        <div className="speakers-list">
          {speakers.map((sp, idx) => {
            const initials = (sp.speaker || "?")
              .split(/\s+/)
              .slice(0, 2)
              .map((part) => part[0])
              .join("")
              .toUpperCase();

            return (
              <article key={`${sp.speaker}-${idx}`} className="speaker-item profile-card">
                <span className={`profile-avatar avatar-${idx % 5}`} aria-hidden="true">
                  {initials}
                </span>
                <div className="profile-details">
                  <strong className="speaker-name">
                    {sp.speaker_uuid ? (
                      <Link
                        to={`/saadik/${encodeURIComponent(sp.speaker_uuid)}`}
                        className="speaker-name-link"
                      >
                        {sp.speaker}
                      </Link>
                    ) : (
                      sp.speaker
                    )}
                  </strong>
                  {sp.faction && (
                    <span className="faction-badge">{formatFactionName(sp.faction)}</span>
                  )}
                  <span className="speaker-count-caption">
                    {Number(sp.count || 0).toLocaleString("et-EE")}{" "}
                    {showingArchiveSpeakers ? "kõnet" : "teemakohast mainimist"}
                  </span>
                  <span className="profile-meter">
                    <i
                      style={{
                        width: `${Math.max(8, (Number(sp.count || 0) / maxCount) * 100)}%`,
                      }}
                    />
                  </span>
                </div>
                <span className="profile-rank">{String(idx + 1).padStart(2, "0")}</span>
              </article>
            );
          })}
        </div>
      ) : (
        <p className="sidebar-empty-state">
          {overviewError
            ? "Kõnelejate koondandmed pole praegu kättesaadavad."
            : "Kõnelejate andmed laaditakse arhiivist."}
        </p>
      )}
    </section>
  );
}

export default SpeakersPanel;
