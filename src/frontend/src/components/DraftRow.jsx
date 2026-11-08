import React from "react";
import { Link } from "react-router-dom";
import { formatDate } from "../lib/calendarUtils";
import { formatDraftMark, formatDraftStage } from "../lib/draftUtils";

function countLabel(count, one, many) {
  return `${count.toLocaleString("et-EE")} ${count === 1 ? one : many}`;
}

export function DraftRow({ draft }) {
  if (!draft) return null;

  const mark = formatDraftMark(draft.mark, draft.type_code);
  const stage = formatDraftStage(draft.stage, draft.status);
  // Drafts missing from the upstream list have no stage; their last plenary sitting dates them
  const date = draft.stage ? draft.status_date : draft.last_plenary_date;
  const facts = [
    draft.leading_committee?.name,
    draft.reading_count > 0 && `${draft.reading_count.toLocaleString("et-EE")} täiskogu arutelu`,
    draft.speech_count > 0 && countLabel(draft.speech_count, "sõnavõtt", "sõnavõttu"),
    draft.voting_count > 0 && countLabel(draft.voting_count, "hääletus", "hääletust"),
    // A just initiated draft would show the same date twice
    draft.initiated && draft.initiated !== date && `Algatatud ${formatDate(draft.initiated)}`,
  ].filter(Boolean);

  return (
    <Link to={`/eelnou/${draft.uuid}`} className="draft-row-link">
      <div className="draft-row-meta">
        {mark && <span className="draft-row-mark">{mark}</span>}
        {stage && (
          <span className={`draft-stage-badge draft-stage-${draft.status_group || "other"}`}>
            {stage}
          </span>
        )}
        {date && <span className="draft-row-date">{formatDate(date)}</span>}
      </div>
      <div className="draft-row-title">{draft.title}</div>
      {facts.length > 0 && (
        <div className="draft-row-facts">
          {/* The separator stays with the preceding part so a wrapped line never starts with it */}
          {facts.map((part, index) => (
            <React.Fragment key={part}>
              {index > 0 && " "}
              <span className="draft-row-fact">
                {index < facts.length - 1 ? `${part} ·` : part}
              </span>
            </React.Fragment>
          ))}
        </div>
      )}
    </Link>
  );
}

export default DraftRow;
