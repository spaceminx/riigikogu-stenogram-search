export function parseQueryToGroups(queryString) {
  if (!queryString || !queryString.trim()) return [[]];
  const parts = queryString
    .split(",")
    .map((p) => p.trim())
    .filter(Boolean);
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
  if (!input || !input.trim()) {
    return currentGroups && currentGroups.length > 0 ? currentGroups : [[]];
  }
  const parsed = parseQueryToGroups(input.trim());
  if (!parsed || parsed.length === 0 || (parsed.length === 1 && parsed[0].length === 0)) {
    return currentGroups && currentGroups.length > 0 ? currentGroups : [[]];
  }

  const base = currentGroups && currentGroups.length > 0 ? [...currentGroups] : [[]];
  const lastIndex = base.length - 1;
  const firstParsed = parsed[0];
  const remaining = parsed.slice(1);

  const mergedLast = [...base[lastIndex], ...firstParsed];
  return [...base.slice(0, lastIndex), mergedLast, ...remaining];
}
