import { formatDate } from "./calendarUtils.js";

export const DECISION_LABELS = {
  POOLT: "Poolt",
  VASTU: "Vastu",
  ERAPOOLETU: "Erapooletu",
  EI_HAALETANUD: "Ei hääletanud",
  PUUDUB: "Puudus",
};

export function formatDecision(decision) {
  if (!decision) return "—";
  return DECISION_LABELS[decision] || decision;
}

export function formatMajorityPosition(pos) {
  if (!pos) return "—";
  return DECISION_LABELS[pos] || pos;
}

export function computeNotVoted(totals) {
  if (!totals) return 0;
  const present = Number(totals.present) || 0;
  const inFavor = Number(totals.in_favor) || 0;
  const against = Number(totals.against) || 0;
  const neutral = Number(totals.neutral) || 0;
  return Math.max(0, present - inFavor - against - neutral);
}

export function formatTimeHHMM(timeStr) {
  if (!timeStr) return "";
  if (timeStr.includes("T")) {
    const afterT = timeStr.split("T")[1];
    return afterT.slice(0, 5);
  }
  return timeStr.slice(0, 5);
}

// "2026-11-11" -> "11.11."
function formatDayMonth(isoDate) {
  const [, month, day] = isoDate.split("-");
  return `${day}.${month}.`;
}

// A sitting can run past midnight: its later votings keep the sitting's date (`sitting_date`)
// but happen on the next day (`date`). Lead with when the vote actually happened and name the
// sitting separately, so "11.11.2026 03:40" never stands for a moment on the wrong day.
// - withDate: list rows ("12.11.2026 03:40"); without it (session page) the date is only added
//   for an overnight vote ("12.11. kell 03:40").
// - sittingLabel ("11.11. istung") is set only for an overnight vote.
export function getVotingTimeParts(voting, { withDate = true } = {}) {
  const time = formatTimeHHMM(voting?.start_time);
  const sittingDate = voting?.sitting_date || "";
  const startDate = voting?.start_time?.includes("T") ? voting.start_time.slice(0, 10) : "";
  const voteDate = voting?.date || startDate || sittingDate;
  const isOvernight = Boolean(sittingDate && voteDate && voteDate !== sittingDate);

  let label = time;
  if (withDate) {
    label = [formatDate(voteDate), time].filter(Boolean).join(" ");
  } else if (isOvernight) {
    label = time ? `${formatDayMonth(voteDate)} kell ${time}` : formatDate(voteDate);
  }

  return {
    label,
    time,
    voteDate,
    isOvernight,
    sittingLabel: isOvernight ? `${formatDayMonth(sittingDate)} istung` : "",
  };
}

export function getVotingSummaryParts(totals) {
  if (!totals) return [];
  return [
    `Poolt ${totals.in_favor ?? 0}`,
    `Vastu ${totals.against ?? 0}`,
    `Erapooletu ${totals.neutral ?? 0}`,
    `Ei hääletanud ${computeNotVoted(totals)}`,
    `Puudus ${totals.absent ?? 0}`,
  ];
}

// The voting description is usually only the procedural step ("Lõpphääletus"); the topic is the
// related document. Votings without a document ("Päevakorra kinnitamine") keep the description.
export function getVotingHeading(voting, { showDocument = true } = {}) {
  const docTitle = voting?.related_document?.title;
  if (showDocument && docTitle) {
    return { title: docTitle, stage: voting.description || null };
  }
  return { title: voting?.description || "Hääletus", stage: null };
}

export function formatDocumentReference(doc) {
  if (!doc?.reference) return "";
  return doc.type === "DRAFT" ? `Eelnõu ${doc.reference}` : doc.reference;
}

export function getVoteBarSegments(totals) {
  if (!totals) return [];
  const segments = [
    { key: "for", label: "Poolt", value: Number(totals.in_favor) || 0 },
    { key: "against", label: "Vastu", value: Number(totals.against) || 0 },
    { key: "abstain", label: "Erapooletu", value: Number(totals.neutral) || 0 },
    { key: "none", label: "Ei hääletanud", value: computeNotVoted(totals) },
    { key: "absent", label: "Puudus", value: Number(totals.absent) || 0 },
  ];
  return segments.some((s) => s.value > 0) ? segments.filter((s) => s.value > 0) : [];
}
