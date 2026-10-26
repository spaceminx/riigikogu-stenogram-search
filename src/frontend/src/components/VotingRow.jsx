import React from "react";
import { Link } from "react-router-dom";
import { formatDate } from "../lib/calendarUtils";
import {
  formatDocumentReference,
  formatOvernightTime,
  getVotingHeading,
  getVotingSummaryParts,
} from "../lib/votingUtils";
import VoteBar from "./VoteBar";

export function VotingRow({ voting, showDate = true, showDocument = true }) {
  if (!voting) return null;

  const timeFormatted = formatOvernightTime(voting.start_time, voting.sitting_date, voting.date);
  const dateFormatted = showDate ? formatDate(voting.sitting_date) : "";
  const timeDisplay = dateFormatted ? `${dateFormatted} ${timeFormatted}`.trim() : timeFormatted;
  const summaryParts = getVotingSummaryParts(voting.totals);
  const { title, stage } = getVotingHeading(voting, { showDocument });
  const reference = showDocument ? formatDocumentReference(voting.related_document) : "";

  return (
    <Link to={`/haaletus/${voting.uuid}`} className="voting-row-link">
      <div className="voting-row-main">
        <div className="voting-row-meta">
          <span className="voting-row-time">{timeDisplay}</span>
          {stage && <span className="voting-stage">{stage}</span>}
          <div className="voting-badges">
            {voting.type === "SALAJANE" && (
              <span className="voting-badge voting-badge-secret">Salajane</span>
            )}
            {voting.is_technical && (
              <span className="voting-badge voting-badge-technical">Tehniline</span>
            )}
          </div>
        </div>
        <div className="voting-row-desc" title={title}>
          {title}
        </div>
        {reference && <div className="voting-row-doc">{reference}</div>}
        <VoteBar totals={voting.totals} />
        {summaryParts.length > 0 && (
          <div className="voting-row-summary">
            {/* The separator stays with the preceding part so a wrapped line never starts with it */}
            {summaryParts.map((part, index) => (
              <React.Fragment key={part}>
                {index > 0 && " "}
                <span className="voting-row-summary-part">
                  {index < summaryParts.length - 1 ? `${part} ·` : part}
                </span>
              </React.Fragment>
            ))}
          </div>
        )}
      </div>
    </Link>
  );
}

export default VotingRow;
