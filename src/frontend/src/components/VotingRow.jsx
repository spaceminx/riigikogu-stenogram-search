import React from "react";
import { Link } from "react-router-dom";
import {
  formatDocumentReference,
  getVotingHeading,
  getVotingSummaryParts,
  getVotingTimeParts,
} from "../lib/votingUtils";
import VoteBar from "./VoteBar";

export function VotingRow({ voting, showDate = true, showDocument = true }) {
  if (!voting) return null;

  const { label: timeLabel, sittingLabel } = getVotingTimeParts(voting, { withDate: showDate });
  // On a session page (no date) the sitting is the page itself
  const showSitting = showDate && sittingLabel;
  const summaryParts = getVotingSummaryParts(voting.totals);
  const { title, stage } = getVotingHeading(voting, { showDocument });
  const reference = showDocument ? formatDocumentReference(voting.related_document) : "";

  return (
    <Link to={`/haaletus/${voting.uuid}`} className="voting-row-link">
      <div className="voting-row-main">
        <div className="voting-row-meta">
          {timeLabel && (
            <span className="voting-row-time">
              {/* The separator stays with the time so a wrapped line never starts with it */}
              <span className="voting-row-time-part">
                {showSitting ? `${timeLabel} ·` : timeLabel}
              </span>
              {showSitting && (
                <>
                  {" "}
                  <span className="voting-row-time-part voting-row-sitting">{sittingLabel}</span>
                </>
              )}
            </span>
          )}
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
