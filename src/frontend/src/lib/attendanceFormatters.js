/**
 * Format metric ratio e.g. "62% · 203/328" or "83% · 822/989".
 * Returns "–" when total is 0 or nullish.
 *
 * @param {number|null|undefined} pct - Optional percentage (rounded to integer if present)
 * @param {number} count - Count of occurrences
 * @param {number} total - Total denominator
 * @returns {string} Formatted string e.g. "62% · 203/328"
 */
export function formatMetricRatio(pct, count, total) {
  if (total == null || total <= 0) {
    return "–";
  }
  const countVal = count ?? 0;
  const p = pct != null ? Math.round(pct) : Math.round((countVal / total) * 100);
  return `${p}% · ${countVal}/${total}`;
}

/**
 * Format vote split subtext e.g.
 * - integer: "ei hääletanud 9% · puudus 8%"
 * - decimals: "ei hääletanud 9,0% · puudus 7,9%"
 * Returns empty string when total is 0 or nullish.
 *
 * @param {number} notVoted - Count of EI_HAALETANUD
 * @param {number} absent - Count of PUUDUB
 * @param {number} total - Total ballots denominator
 * @param {Object} [options] - Optional formatting options
 * @param {number|boolean} [options.decimals] - Number of decimal places (e.g. 1) or true for 1 decimal
 * @returns {string} Formatted split line
 */
export function formatVoteSplit(notVoted, absent, total, options = {}) {
  if (total == null || total <= 0) {
    return "";
  }
  const nv = notVoted ?? 0;
  const ab = absent ?? 0;

  const useDecimals =
    options?.decimals === 1 || options?.decimals === true || options?.decimals > 0;

  if (useDecimals) {
    const nvStr = ((nv / total) * 100).toFixed(1).replace(".", ",");
    const abStr = ((ab / total) * 100).toFixed(1).replace(".", ",");
    return `ei hääletanud ${nvStr}% · puudus ${abStr}%`;
  }

  const nvPct = Math.round((nv / total) * 100);
  const abPct = Math.round((ab / total) * 100);
  return `ei hääletanud ${nvPct}% · puudus ${abPct}%`;
}
