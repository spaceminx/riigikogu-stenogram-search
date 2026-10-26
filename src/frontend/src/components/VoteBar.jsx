import React from "react";
import { getVoteBarSegments } from "../lib/votingUtils";

// Proportional result bar; the numbers are always shown as text next to it, so it is decorative.
// Takes voting totals, or ready segments from the attendance tables.
export function VoteBar({ totals, segments }) {
  const parts = segments ?? getVoteBarSegments(totals);
  if (parts.length === 0) return null;

  return (
    <div className="vote-bar" aria-hidden="true">
      {parts.map((segment) => (
        <span
          key={segment.key}
          className={`vote-bar-segment vote-bar-${segment.key}`}
          style={{ flexGrow: segment.value }}
        />
      ))}
    </div>
  );
}

export default VoteBar;
