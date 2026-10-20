/**
 * Pure helper functions for search query suggestions.
 */

/**
 * Determine if an input string is eligible for prefix suggestions.
 * Must have no spaces and trimmed length between 2 and 40 characters.
 *
 * @param {string} input
 * @returns {boolean}
 */
export function isPrefixEligible(input) {
  if (typeof input !== "string") return false;
  if (/\s/.test(input)) return false;
  const trimmed = input.trim();
  return trimmed.length >= 2 && trimmed.length <= 40;
}

/**
 * Calculate next highlighted index with wrap-around navigation.
 *
 * @param {number} currentIndex Current highlighted index (-1 if none)
 * @param {number} delta Navigation direction (+1 for down, -1 for up)
 * @param {number} totalCount Total number of suggestion items
 * @returns {number} Next highlighted index (-1 if totalCount <= 0)
 */
export function getNextHighlightedIndex(currentIndex, delta, totalCount) {
  if (!totalCount || totalCount <= 0) return -1;
  if (currentIndex === -1) {
    return delta > 0 ? 0 : totalCount - 1;
  }
  return (currentIndex + delta + totalCount) % totalCount;
}

/**
 * Format speech occurrence count in Estonian (e.g. "1 953 kõnet", "1 kõne").
 *
 * @param {number} count
 * @returns {string}
 */
export function formatSuggestionCount(count) {
  if (typeof count !== "number" || isNaN(count)) return "";
  const numStr = Math.round(count)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  const unit = count === 1 ? "kõne" : "kõnet";
  return `${numStr} ${unit}`;
}
