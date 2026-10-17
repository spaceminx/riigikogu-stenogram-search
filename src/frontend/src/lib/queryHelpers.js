export function splitQueryGroups(queryString) {
  if (!queryString || !queryString.trim()) return [];
  const str = queryString.trim();
  const quoteCount = (str.match(/"/g) || []).length;
  const respectQuotes = quoteCount % 2 === 0;

  const groups = [];
  let current = "";
  let inQuotes = false;

  for (let i = 0; i < str.length; i++) {
    const ch = str[i];
    if (ch === '"' && respectQuotes) {
      inQuotes = !inQuotes;
      current += ch;
    } else if (ch === "," && !inQuotes) {
      const trimmed = current.trim();
      if (trimmed) {
        groups.push(trimmed);
      }
      current = "";
    } else {
      current += ch;
    }
  }
  const trimmed = current.trim();
  if (trimmed) {
    groups.push(trimmed);
  }
  return groups;
}

export function parseQueryToGroups(queryString) {
  if (!queryString || !queryString.trim()) return [[]];
  const parts = splitQueryGroups(queryString);
  if (parts.length === 0) return [[]];

  return parts.map((part) => {
    const quoteCount = (part.match(/"/g) || []).length;
    if (quoteCount % 2 !== 0) {
      return part.replace(/"/g, " ").split(/\s+/).filter(Boolean);
    }
    const pills = [];
    const regex = /"([^"]*)"|(\S+)/g;
    let m;
    while ((m = regex.exec(part)) !== null) {
      const val = (m[1] !== undefined ? m[1] : m[2]).trim();
      if (val) {
        pills.push(val);
      }
    }
    return pills;
  });
}

export function mergeInputToGroups(currentGroups, input) {
  if (typeof input !== "string") {
    return currentGroups && currentGroups.length > 0 ? currentGroups : [[]];
  }
  const cleaned = input.replace(/"/g, "").replace(/\s+/g, " ").trim();
  if (!cleaned) {
    return currentGroups && currentGroups.length > 0 ? currentGroups : [[]];
  }

  const base = currentGroups && currentGroups.length > 0 ? currentGroups.map((g) => [...g]) : [[]];
  const lastIndex = base.length - 1;
  base[lastIndex].push(cleaned);
  return base;
}

export function serializeGroupsToQuery(groups) {
  if (!groups || groups.length === 0) return "";
  return groups
    .filter((g) => g && g.length > 0)
    .map((group) =>
      group.map((pill) => (pill.includes(" ") || pill.includes(",") ? `"${pill}"` : pill)).join(" ")
    )
    .filter(Boolean)
    .join(", ");
}
