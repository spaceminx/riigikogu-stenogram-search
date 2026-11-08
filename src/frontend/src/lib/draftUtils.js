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

// Draft types as named in the Riigikogu classifier "eelnouLiik"
export const DRAFT_TYPE_LABELS = {
  SE: "Seadus",
  OE: "Otsus",
  AE: "Avaldus",
  TK: "Tegevuskava",
  DE: "Deklaratsioon",
  PE: "Pöördumine",
  UA: "Uuesti arutamine",
};

// Proceeding stages as named in the Riigikogu classifier "menetlusetapid"
export const DRAFT_STAGE_LABELS = {
  MENETLUSSE_VOETUD: "Menetlusse võetud",
  ALGATATUD: "Algatatud",
  ESIMENE_LUGEMINE: "Esimene lugemine",
  TEINE_LUGEMINE: "Teine lugemine",
  KOLMAS_LUGEMINE: "Kolmas lugemine",
  TEISE_LUGEMISE_JATKAMINE: "Teise lugemise jätkamine",
  TEISE_LUGEMISE_JATKUMINE: "Teise lugemise jätkumine",
  KOLMANDA_LUGEMISE_JATKAMINE: "Kolmanda lugemise jätkamine",
  KOLMANDA_LUGEMISE_JATKUMINE: "Kolmanda lugemise jätkumine",
  UUESTI_ARUTAMINE: "Uuesti arutamine",
  TAGASTATUD: "Tagastatud",
  TAGASI_VOETUD: "Tagasi võetud",
  VASTU_VOETUD: "Vastu võetud",
  TAGASI_LYKATUD: "Tagasi lükatud",
  TAGASI_VOETUD_TAISKOGUL_MENETLEMATA: "Tagasi võetud täiskogul menetlemata",
  VALJA_LANGENUD_KOOSEISU_LOPPEMISEGA: "Välja langenud koosseisu lõppemisega",
  KOLMAS_LUGEMINE_KUI_TEINE_LOPETATAKSE: "Kolmas lugemine, kui teine lõpetatakse",
  YHENDATUD: "Ühendatud",
  SAADETUD_RT: "Saadetud Riigi Teatajasse",
};

// The upstream classifier for statuses has no labels; these spell out its codes
export const DRAFT_STATUS_LABELS = {
  ALGATATUD: "Algatatud",
  MENETLUSSE_VOETUD: "Menetlusse võetud",
  SAADETUD_I_LUGEMISELE: "Saadetud I lugemisele",
  I_LUGEMINE_LOPETATUD: "I lugemine lõpetatud",
  SAADETUD_II_LUGEMISELE: "Saadetud II lugemisele",
  II_LUGEMINE_KATKESTATUD: "II lugemine katkestatud",
  SAADETUD_II_LUGEMISE_JATKAMISELE: "Saadetud II lugemise jätkamisele",
  II_LUGEMINE_LOPETATUD: "II lugemine lõpetatud",
  SAADETUD_III_LUGEMISELE: "Saadetud III lugemisele",
  III_LUGEMINE_KATKESTATUD: "III lugemine katkestatud",
  SAADETUD_III_LUGEMISE_JATKAMISELE: "Saadetud III lugemise jätkamisele",
  VASTU_VOETUD: "Vastu võetud",
  TAGASI_VOETUD: "Tagasi võetud",
  TAGASI_VOETUD_TAISKOGUL_MENETLEMATA: "Tagasi võetud täiskogul menetlemata",
  TAGASI_LYKATUD: "Tagasi lükatud",
  SAADETUD_VABARIIGI_PRESIDENDILE: "Saadetud Vabariigi Presidendile",
  VALJAKUULUTATUD: "Väljakuulutatud",
  AVALDATUD_RIIGITEATAJAS: "Avaldatud Riigi Teatajas",
  UUESTI_ARUTAMINE: "Uuesti arutamine",
  TEISTKORDNE_MENETLEMINE: "Teistkordne menetlemine",
  TAGASTATUD: "Tagastatud",
  VALJA_LANGENUD_KOOSSEISU_LOPPEDES: "Välja langenud koosseisu lõppedes",
  YHENDAMISEGA_MENETLUS_LOPETATUD: "Ühendamisega menetlus lõpetatud",
  YHENDATUD: "Ühendatud",
  SAADETUD_RT: "Saadetud Riigi Teatajasse",
};

// Filter groups of GET /drafts?status=, in the API's order
export const DRAFT_STATUS_GROUPS = [
  { value: "in_process", label: "Menetluses" },
  { value: "adopted", label: "Vastu võetud" },
  { value: "rejected", label: "Tagasi lükatud" },
  { value: "withdrawn", label: "Tagasi võetud" },
  { value: "lapsed", label: "Välja langenud" },
  { value: "other", label: "Muu" },
];

function humanizeCode(code) {
  const text = String(code).replace(/_/g, " ").trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1).toLowerCase() : "";
}

/**
 * Draft mark as Riigikogu writes it: "919 SE", or the bare number when the type is unknown.
 */
export function formatDraftMark(mark, typeCode) {
  if (mark === null || mark === undefined || mark === "") return "";
  return typeCode ? `${mark} ${typeCode}` : String(mark);
}

export function formatDraftType(typeCode) {
  if (!typeCode) return "";
  return DRAFT_TYPE_LABELS[typeCode] || typeCode;
}

export function formatDraftStage(stage, status) {
  if (stage === "VASTU_VOETUD" && status && status !== "VASTU_VOETUD") {
    return DRAFT_STATUS_LABELS[status] || humanizeCode(status);
  }
  if (!stage) return "";
  return DRAFT_STAGE_LABELS[stage] || humanizeCode(stage);
}
