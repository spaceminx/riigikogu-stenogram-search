import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";

/**
 * Moves a page number past the end (a hand-edited or stale address) to the last page, so the
 * list is not empty under "Lehekülg 999 / 109". `totalPages` is null until the count is known;
 * with no results at all nothing is moved.
 */
export function useClampPage(param, page, totalPages) {
  const [, setSearchParams] = useSearchParams();

  useEffect(() => {
    if (!totalPages || page <= totalPages) return;
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (totalPages === 1) next.delete(param);
        else next.set(param, String(totalPages));
        return next;
      },
      { replace: true }
    );
  }, [param, page, totalPages, setSearchParams]);
}
