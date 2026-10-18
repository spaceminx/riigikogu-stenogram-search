import React from "react";
import { Link } from "react-router-dom";
import { formatDate } from "../lib/calendarUtils";
import { formatOvernightTime, formatVotingSummary } from "../lib/votingUtils";

export function VotingRow({ voting, showDate = true }) {
  if (!voting) return null;

  const timeFormatted = formatOvernightTime(voting.start_time, voting.sitting_date, voting.date);
  const dateFormatted = showDate ? formatDate(voting.sitting_date) : "";
  const timeDisplay = dateFormatted ? `${dateFormatted} ${timeFormatted}`.trim() : timeFormatted;
  const summary = formatVotingSummary(voting.totals);

  return (
    <Link to={`/haaletus/${voting.uuid}`} className="voting-row-link">
      <div className="voting-row-main">
        <div className="voting-row-meta">
          <span className="voting-row-time">{timeDisplay}</span>
          <div className="voting-badges">
            {voting.type === "SALAJANE" && (
              <span className="voting-badge voting-badge-secret">Salajane</span>
            )}
            {voting.is_technical && (
              <span className="voting-badge voting-badge-technical">Tehniline</span>
            )}
          </div>
        </div>
        <div className="voting-row-desc">{voting.description}</div>
        {voting.related_document?.title && (
          <div className="voting-row-doc">
            {voting.related_document.reference ? `${voting.related_document.reference} · ` : ""}
            {voting.related_document.title}
          </div>
        )}
        {summary && <div className="voting-row-summary">{summary}</div>}
      </div>
    </Link>
  );
}

export default VotingRow;
