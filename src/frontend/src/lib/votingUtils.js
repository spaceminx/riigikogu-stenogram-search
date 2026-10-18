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

export function formatOvernightTime(startTime, sittingDate, voteDate) {
  const timeFormatted = formatTimeHHMM(startTime);
  if (!timeFormatted) return "";
  if (voteDate && sittingDate && voteDate !== sittingDate) {
    return `${timeFormatted} (${formatDate(voteDate)})`;
  }
  return timeFormatted;
}

export function formatVotingSummary(totals) {
  if (!totals) return "";
  const poolt = totals.in_favor ?? 0;
  const vastu = totals.against ?? 0;
  const erapooletu = totals.neutral ?? 0;
  const eiHaaletanud = computeNotVoted(totals);
  const puudus = totals.absent ?? 0;
  return `Poolt ${poolt} · Vastu ${vastu} · Erapooletu ${erapooletu} · Ei hääletanud ${eiHaaletanud} · Puudus ${puudus}`;
}
