import { describe, it } from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import {
  buildMemberRows,
  filterMemberRows,
  memberCountText,
  normalizeName,
} from "../src/lib/membersUtils.js";

const NO_FACTION = "Fraktsiooni mittekuuluvad Riigikogu liikmed";
const fixture = JSON.parse(
  fs.readFileSync(new URL("../e2e/fixtures/factions.json", import.meta.url), "utf-8")
);
const rows = buildMemberRows(fixture.factions);
const byName = (name) => rows.find((r) => r.fullName === name);

describe("buildMemberRows", () => {
  it("lists every person once, sorted by last name in Estonian order", () => {
    assert.strictEqual(rows.length, 19);
    assert.strictEqual(new Set(rows.map((r) => r.uuid)).size, rows.length);
    const lastNames = rows.map((r) => r.lastName);
    assert.deepStrictEqual(
      lastNames,
      [...lastNames].sort((a, b) => a.localeCompare(b, "et"))
    );
  });

  it("shows a faction switcher under the current faction with the former one noted", () => {
    const row = byName("Züleyxa Izmailova");
    assert.strictEqual(row.faction, NO_FACTION);
    assert.deepStrictEqual(row.formerFactions, ["Eesti 200 fraktsioon"]);
    assert.strictEqual(row.current, true);
  });

  it("takes the latest faction of a member who has left", () => {
    const row = byName("Jüri Ratas");
    assert.strictEqual(row.faction, NO_FACTION);
    assert.deepStrictEqual(row.formerFactions, ["Eesti Keskerakonna fraktsioon"]);
    assert.strictEqual(row.current, false);
  });
});

describe("filterMemberRows", () => {
  it("hides former members when asked", () => {
    assert.strictEqual(filterMemberRows(rows, { currentOnly: true }).length, 16);
    assert.ok(
      !filterMemberRows(rows, { currentOnly: true }).some((r) => r.fullName === "Jüri Ratas")
    );
  });

  it("finds names regardless of case and diacritics", () => {
    const found = (query) => filterMemberRows(rows, { query }).map((r) => r.fullName);
    assert.deepStrictEqual(found("POLLUAAS"), ["Henn Põlluaas"]);
    assert.deepStrictEqual(found("jüri"), ["Jüri Jaanson", "Jüri Ratas"]);
    assert.deepStrictEqual(found("  kallas "), ["Madis Kallas", "Siim Kallas"]);
  });

  it("matches a faction the member belonged to earlier in the membership too", () => {
    const names = filterMemberRows(rows, { faction: "Eesti 200 fraktsioon" }).map(
      (r) => r.fullName
    );
    assert.ok(names.includes("Züleyxa Izmailova"));
  });
});

describe("helpers", () => {
  it("normalizeName strips accents and case", () => {
    assert.strictEqual(normalizeName(" Õun Šmigun-Vähi "), "oun smigun-vahi");
  });

  it("memberCountText", () => {
    assert.strictEqual(memberCountText(1), "1 saadik");
    assert.strictEqual(memberCountText(101), "101 saadikut");
  });
});
