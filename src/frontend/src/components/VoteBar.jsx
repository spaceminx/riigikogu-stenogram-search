import React from "react";
import { getVoteBarSegments } from "../lib/votingUtils";

// Proportional result bar; the numbers are always shown as text next to it, so it is decorative
export function VoteBar({ totals }) {
  const segments = getVoteBarSegments(totals);
  if (segments.length === 0) return null;

  return (
    <div className="vote-bar" aria-hidden="true">
      {segments.map((segment) => (
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
