export const STAGE_LABELS = {
  ESIMENE_LUGEMINE: "Esimene lugemine",
  TEINE_LUGEMINE: "Teine lugemine",
  KOLMAS_LUGEMINE: "Kolmas lugemine",
};

/**
 * Format stage label for a reading.
 * ESIMENE_LUGEMINE -> "Esimene lugemine"
 * TEINE_LUGEMINE -> "Teine lugemine"
 * KOLMAS_LUGEMINE -> "Kolmas lugemine"
 * Any other code -> decision_value or the code with "_" -> " " in sentence case.
 */
export function formatStageLabel(stage, decisionValue) {
  if (stage && STAGE_LABELS[stage]) {
    return STAGE_LABELS[stage];
  }
  if (decisionValue && typeof decisionValue === "string" && decisionValue.trim()) {
    return decisionValue.trim();
  }
  if (!stage) return "";
  const text = String(stage).replace(/_/g, " ").trim();
  if (!text) return "";
  return text.charAt(0).toUpperCase() + text.slice(1).toLowerCase();
}

/**
 * Sort readings chronologically by sitting date and order.
 */
export function sortReadingsByDate(readings = []) {
  if (!Array.isArray(readings)) return [];
  return [...readings].sort((a, b) => {
    const dateA = a.sitting_date || "";
    const dateB = b.sitting_date || "";
    if (dateA !== dateB) {
      return dateA.localeCompare(dateB);
    }
    return (a.order || 0) - (b.order || 0);
  });
}

/**
 * Group votings by reading using each reading's voting_uuids.
 */
export function groupVotingsByReading(readings = [], votings = []) {
  if (!Array.isArray(readings)) return [];
  const safeVotings = Array.isArray(votings) ? votings : [];
  const votingsByUuid = new Map(safeVotings.filter((v) => v && v.uuid).map((v) => [v.uuid, v]));

  return readings.map((reading) => {
    const uuids = Array.isArray(reading?.voting_uuids) ? reading.voting_uuids : [];
    const matchedVotings = uuids.map((uuid) => votingsByUuid.get(uuid)).filter(Boolean);
    return {
      ...reading,
      votings: matchedVotings,
    };
  });
}

/**
 * Select votings that belong to no reading ("Muud hääletused").
 */
export function getOtherVotings(readings = [], votings = []) {
  if (!Array.isArray(votings)) return [];
  const assignedUuids = new Set();
  if (Array.isArray(readings)) {
    for (const reading of readings) {
      if (Array.isArray(reading?.voting_uuids)) {
        for (const uuid of reading.voting_uuids) {
          if (uuid) assignedUuids.add(uuid);
        }
      }
    }
  }

  return votings.filter((v) => v && v.uuid && !assignedUuids.has(v.uuid));
}

/**
 * Construct link to official Riigikogu draft page.
 */
export function getRiigikoguDraftUrl(uuid) {
  if (!uuid) return "";
  return `https://www.riigikogu.ee/tegevus/eelnoud/${encodeURIComponent(uuid)}/`;
}
