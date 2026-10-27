import { formatDate } from "./calendarUtils.js";

export const NO_FACTION = "Fraktsiooni mittekuuluvad Riigikogu liikmed";

// Members who joined within this many days of the membership start were there from the start
const JOINED_LATER_DAYS = 31;

function addDays(day, days) {
  const date = new Date(`${day}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function formatPeriod({ start, end }) {
  return end ? `${formatDate(start)}–${formatDate(end)}` : `alates ${formatDate(start)}`;
}

export function formatPeriods(periods = []) {
  return periods.map(formatPeriod).join(", ");
}

export function joinedLater(member, membershipStart) {
  const first = member.periods?.[0]?.start;
  return Boolean(first && membershipStart && first > addDays(membershipStart, JOINED_LATER_DAYS));
}

// One period from the start to the end of the membership (or still ongoing) needs no dates
export function isFullTerm(member, membershipStart, membershipEnd) {
  const periods = member.periods ?? [];
  if (periods.length !== 1 || joinedLater(member, membershipStart)) return false;
  const { end } = periods[0];
  return !end || Boolean(membershipEnd && end >= addDays(membershipEnd, -JOINED_LATER_DAYS));
}

export function splitMembers(faction) {
  const current = [];
  const former = [];
  for (const member of faction.members ?? []) {
    (member.current ? current : former).push(member);
  }
  return { current, former };
}

export function filterFactionsByRole(factions = [], role = "") {
  if (!role) return factions;
  return factions.filter((f) => f.role === role);
}

export function getSeatCounts(factions = []) {
  const counts = { coalition: 0, opposition: 0, none: 0 };
  for (const f of factions) {
    if (f.role in counts) counts[f.role] += f.current_count ?? 0;
  }
  return counts;
}

// Segments for VoteBar, in a fixed order; empty groups are left out
export function getSeatSegments(counts) {
  return [
    { key: "coalition", value: counts.coalition },
    { key: "opposition", value: counts.opposition },
    { key: "nonaligned", value: counts.none },
  ].filter((s) => s.value > 0);
}

export const ROLE_LABELS = {
  coalition: "Koalitsioonis",
  opposition: "Opositsioonis",
};
