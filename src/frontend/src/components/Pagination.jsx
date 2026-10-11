import React from "react";

export function Pagination({ currentPage, totalPages, onPageChange, loading = false }) {
  if (totalPages <= 1) return null;

  return (
    <div className="pagination-container">
      <button
        type="button"
        className="pagination-btn"
        disabled={currentPage <= 1 || loading}
        onClick={() => onPageChange(currentPage - 1)}
      >
        &larr; Eelmine
      </button>
      <span className="pagination-text">
        Lehekülg {currentPage} / {totalPages}
      </span>
      <button
        type="button"
        className="pagination-btn"
        disabled={currentPage >= totalPages || loading}
        onClick={() => onPageChange(currentPage + 1)}
      >
        Järgmine &rarr;
      </button>
    </div>
  );
}

export default Pagination;
