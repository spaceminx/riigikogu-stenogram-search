/**
 * Format percentage with Estonian decimal comma.
 * - Integer percentages: 100 -> "100%", 0 -> "0%"
 * - Decimals: 61.9 -> "61,9%", 83.1 -> "83,1%"
 * - Null / undefined / invalid: "–" (en-dash)
 *
 * @param {number|string|null|undefined} value
 * @param {number} [decimals=1]
 * @returns {string} Formatted percentage
 */
export function formatPercent(value, decimals = 1) {
  if (value == null || value === "" || isNaN(Number(value))) {
    return "–";
  }
  const num = Number(value);
  if (decimals === 0) {
    return `${Math.round(num)}%`;
  }
  const formatted = num.toFixed(decimals).replace(".", ",");
  if (formatted === "100," + "0".repeat(decimals) || num >= 100) {
    return "100%";
  }
  if (formatted === "0," + "0".repeat(decimals) || num <= 0) {
    return "0%";
  }
  return `${formatted}%`;
}

/**
 * Format metric ratio e.g. "61,9% · 203/328" or "83,1% · 822/989".
 * Returns "–" when total is 0 or nullish.
 *
 * @param {number|null|undefined} pct - Optional percentage (Estonian decimal comma)
 * @param {number} count - Count of occurrences
 * @param {number} total - Total denominator
 * @returns {string} Formatted string e.g. "61,9% · 203/328"
 */
export function formatMetricRatio(pct, count, total) {
  if (total == null || total <= 0) {
    return "–";
  }
  const countVal = count ?? 0;
  const pctVal = pct != null ? pct : (countVal / total) * 100;
  const pStr = formatPercent(pctVal, 1);
  return `${pStr} · ${countVal}/${total}`;
}

/**
 * Format vote split subtext e.g.
 * - with decimals (default): "ei hääletanud 9,0% · puudus 7,9%"
 * - integer ({ decimals: 0 }): "ei hääletanud 9% · puudus 8%"
 * Returns empty string when total is 0 or nullish.
 *
 * @param {number} notVoted - Count of EI_HAALETANUD
 * @param {number} absent - Count of PUUDUB
 * @param {number} total - Total ballots denominator
 * @param {Object} [options] - Optional formatting options
 * @param {number} [options.decimals] - Number of decimal places (default 1)
 * @returns {string} Formatted split line
 */
export function formatVoteSplit(notVoted, absent, total, options = {}) {
  if (total == null || total <= 0) {
    return "";
  }
  const nv = notVoted ?? 0;
  const ab = absent ?? 0;
  const decimals = options?.decimals ?? 1;

  const nvStr = formatPercent((nv / total) * 100, decimals);
  const abStr = formatPercent((ab / total) * 100, decimals);
  return `ei hääletanud ${nvStr} · puudus ${abStr}`;
}

/**
 * Check if an item has a small sample for the given metric.
 * - registered_pct: total_checks < 20
 * - votes_voted_pct (default): votes_total < 50
 *
 * @param {Object} item
 * @param {string} [sortKey]
 * @returns {boolean}
 */
export function isSmallSample(item, sortKey) {
  if (!item) return false;
  if (sortKey === "registered_pct") {
    const checks = item.total_checks ?? item.total_sessions ?? 0;
    return checks < 20;
  }
  const votes = item.votes_total ?? 0;
  return votes < 50;
}

/**
 * Sort attendance items (members or factions) putting small samples last.
 * - Items with small sample go after everyone else regardless of sort direction.
 * - Inside each block, sort by chosen percentage (respecting direction), then by total descending.
 *
 * @param {Array} items
 * @param {Object} sortConfig - { key, direction }
 * @returns {Array} Sorted array
 */
export function sortAttendanceItems(items, sortConfig) {
  if (!items || items.length === 0) return [];
  const list = [...items];
  const key = sortConfig?.key;
  if (!key) return list;

  const isPctSort = key === "votes_voted_pct" || key === "registered_pct";

  list.sort((a, b) => {
    // If sorting by percentage, partition small samples to the bottom regardless of sort direction
    if (isPctSort) {
      const smallA = isSmallSample(a, key);
      const smallB = isSmallSample(b, key);
      if (smallA !== smallB) {
        return smallA ? 1 : -1;
      }
    }

    const valA = a[key];
    const valB = b[key];

    // Put nulls/undefined at the very end of their block
    if (valA == null && valB == null) return 0;
    if (valA == null) return 1;
    if (valB == null) return -1;

    // String sorting with locale collation
    if (typeof valA === "string" && typeof valB === "string") {
      const cmp = valA.localeCompare(valB, "et");
      return sortConfig.direction === "ascending" ? cmp : -cmp;
    }

    if (valA < valB) {
      return sortConfig.direction === "ascending" ? -1 : 1;
    }
    if (valA > valB) {
      return sortConfig.direction === "ascending" ? 1 : -1;
    }

    // Tie-breakers: inside each block, sort then by total descending
    if (key === "votes_voted_pct") {
      const totDiff = (b.votes_total ?? 0) - (a.votes_total ?? 0);
      if (totDiff !== 0) return totDiff;
      return (b.votes_voted ?? 0) - (a.votes_voted ?? 0);
    }
    if (key === "registered_pct") {
      const checksA = a.total_checks ?? a.total_sessions ?? 0;
      const checksB = b.total_checks ?? b.total_sessions ?? 0;
      const totDiff = checksB - checksA;
      if (totDiff !== 0) return totDiff;
      return (
        (b.registered_checks ?? b.present_sessions ?? 0) -
        (a.registered_checks ?? a.present_sessions ?? 0)
      );
    }

    return 0;
  });

  return list;
}
