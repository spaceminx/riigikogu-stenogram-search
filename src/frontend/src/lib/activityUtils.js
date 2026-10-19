import { formatPercent } from "./attendanceFormatters.js";

/**
 * Format share ratio (e.g. 0.035) into Estonian percentage string (e.g. "3,5%").
 *
 * @param {number|string|null|undefined} share
 * @param {number} [decimals=1]
 * @returns {string|null}
 */
export function formatActivityShare(share, decimals = 1) {
  if (share == null || share === "" || isNaN(Number(share))) {
    return null;
  }
  const pct = Number(share) * 100;
  const isInt = Number.isInteger(Math.round(pct * 1000) / 1000) && Number.isInteger(pct);
  return formatPercent(pct, isInt ? 0 : decimals);
}

/**
 * Check whether a timeline period had no plenary sittings (share is null).
 *
 * @param {object|null|undefined} item
 * @returns {boolean}
 */
export function isNullPeriod(item) {
  return item == null || item.share == null;
}

/**
 * Format activity chart tooltip description.
 *
 * @param {object|null|undefined} item
 * @param {"count"|"share"} [scale="count"]
 * @returns {string}
 */
export function formatActivityTooltip(item, scale = "count") {
  if (!item) return "";
  if (scale === "share") {
    if (isNullPeriod(item)) {
      return "Istungeid polnud";
    }
    const shareStr = formatActivityShare(item.share) || "0%";
    const count = item.count ?? 0;
    const total = item.total ?? 0;
    return `${count} sõnavõttu ${total}-st (${shareStr})`;
  }

  const count = item.count ?? 0;
  if (item.total != null && item.total > 0) {
    return `${count} sõnavõttu (kokku ${item.total} sõnavõttu)`;
  }
  return `${count} sõnavõttu`;
}

/**
 * Parse scale query parameter from URL ("share" or default "count").
 *
 * @param {string|null|undefined} value
 * @returns {"count"|"share"}
 */
export function parseScaleParam(value) {
  return value === "share" ? "share" : "count";
}

/**
 * Update URLSearchParams with scale parameter, omitting it when default "count".
 *
 * @param {URLSearchParams|string} params
 * @param {"count"|"share"} scale
 * @returns {URLSearchParams}
 */
export function updateScaleParam(params, scale) {
  const next = new URLSearchParams(params);
  if (scale === "share") {
    next.set("scale", "share");
  } else {
    next.delete("scale");
  }
  return next;
}
