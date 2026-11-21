// The /saadikud list is built from the /factions response of one membership: every member with
// the faction they belong to now (or last belonged to in a past membership)

function latestEnd(member) {
  const periods = member.periods ?? [];
  if (periods.some((p) => !p.end)) return "9999-12-31";
  return periods.reduce((max, p) => (p.end > max ? p.end : max), "");
}

// One row per person; a member who changed factions keeps the latest one and lists the others
export function buildMemberRows(factions = []) {
  const byUuid = new Map();
  for (const faction of factions) {
    for (const member of faction.members ?? []) {
      const entry = { faction: faction.faction, current: Boolean(member.current), member };
      const list = byUuid.get(member.uuid);
      if (list) list.push(entry);
      else byUuid.set(member.uuid, [entry]);
    }
  }

  const rows = [];
  for (const entries of byUuid.values()) {
    const sorted = [...entries].sort(
      (a, b) =>
        Number(b.current) - Number(a.current) ||
        latestEnd(b.member).localeCompare(latestEnd(a.member))
    );
    const { member, faction } = sorted[0];
    rows.push({
      uuid: member.uuid,
      fullName: member.full_name,
      firstName: member.first_name ?? "",
      lastName: member.last_name ?? "",
      photoUrl: member.photo_url || null,
      district: member.electoral_district || "",
      faction,
      formerFactions: [...new Set(sorted.slice(1).map((e) => e.faction))].filter(
        (f) => f !== faction
      ),
      current: entries.some((e) => e.current),
    });
  }
  return rows.sort(
    (a, b) =>
      a.lastName.localeCompare(b.lastName, "et") || a.firstName.localeCompare(b.firstName, "et")
  );
}

// Case- and accent-insensitive, so "oun" finds "Õun" and "jarvik" finds "Järvik"
export function normalizeName(text = "") {
  return text
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

export function filterMemberRows(
  rows = [],
  { query = "", faction = "", currentOnly = false } = {}
) {
  const q = normalizeName(query);
  return rows.filter(
    (row) =>
      (!currentOnly || row.current) &&
      (!faction || row.faction === faction || row.formerFactions.includes(faction)) &&
      (!q || normalizeName(row.fullName).includes(q))
  );
}

export function memberCountText(count) {
  return `${count} ${count === 1 ? "saadik" : "saadikut"}`;
}
