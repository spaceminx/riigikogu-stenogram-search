import React from "react";

/** One-line error in place of a section whose request failed, with a retry button. */
export function SectionError({ message, onRetry }) {
  return (
    <div className="error-banner" role="alert" style={{ margin: "0.5rem 0" }}>
      <div className="error-content">
        <span className="error-icon">!</span>
        <span>{message}</span>
      </div>
      {onRetry && (
        <button type="button" className="filter-search-btn" onClick={onRetry}>
          Proovi uuesti
        </button>
      )}
    </div>
  );
}
