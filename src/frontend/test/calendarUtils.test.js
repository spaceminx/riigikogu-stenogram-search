import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  getQuickPresets,
  getPresetRange,
  isValidDateKey,
  QUICK_PRESETS,
  visibleMemberships,
} from "../src/lib/calendarUtils.js";

describe("calendar quick presets", () => {
  it("builds presets for current and ended memberships", () => {
    const memberships = [
      { id: "15", number: 15, start_date: "2023-04-10", end_date: "2027-02-25" },
      { id: "14", number: 14, start_date: "2019-04-04", end_date: "2023-04-09" },
      { id: "13", number: 13, start_date: "2015-03-30", end_date: "2019-04-03" },
    ];
    const today = "2024-06-01";
    const presets = getQuickPresets(memberships, today);

    assert.strictEqual(presets.length, 4);

    // Current membership
    assert.strictEqual(presets[0].id, "15");
    assert.strictEqual(presets[0].label, "XV Riigikogu (2023–praegu)");
    assert.strictEqual(presets[0].startDate, "2023-04-10");
    assert.strictEqual(presets[0].endDate, "2024-06-01");

    // Ended membership
    assert.strictEqual(presets[1].id, "14");
    assert.strictEqual(presets[1].label, "XIV Riigikogu (2019–2023)");
    assert.strictEqual(presets[1].startDate, "2019-04-04");
    assert.strictEqual(presets[1].endDate, "2023-04-09");

    // Standard presets
    assert.strictEqual(presets[2].id, "year");
    assert.strictEqual(presets[2].label, "Viimane aasta");
    assert.strictEqual(presets[3].id, "archive");
    assert.strictEqual(presets[3].label, "Kogu arhiiv");

    // getPresetRange tests
    const range15 = getPresetRange("15", [], memberships, today);
    assert.deepStrictEqual(range15, { startDate: "2023-04-10", endDate: "2024-06-01" });

    const range14 = getPresetRange("14", [], memberships, today);
    assert.deepStrictEqual(range14, { startDate: "2019-04-04", endDate: "2023-04-09" });
  });

  it("excludes future memberships that have not started yet", () => {
    const memberships = [
      { id: "16", number: 16, start_date: "2027-03-30", end_date: "2031-03-31" },
      { id: "15", number: 15, start_date: "2023-04-10", end_date: "2027-02-25" },
      { id: "14", number: 14, start_date: "2019-04-04", end_date: "2023-04-09" },
    ];
    const today = "2026-10-18";
    const presets = getQuickPresets(memberships, today);

    assert.strictEqual(presets.length, 4);
    assert.strictEqual(presets[0].id, "15");
    assert.strictEqual(presets[0].label, "XV Riigikogu (2023–praegu)");
    assert.strictEqual(presets[1].id, "14");
    assert.strictEqual(presets[1].label, "XIV Riigikogu (2019–2023)");
    assert.ok(!presets.some((p) => p.id === "16"));
  });

  it("falls back to hard-coded presets when memberships are not loaded", () => {
    const fallbackNull = getQuickPresets(null);
    assert.deepStrictEqual(fallbackNull, QUICK_PRESETS);

    const fallbackEmpty = getQuickPresets([]);
    assert.deepStrictEqual(fallbackEmpty, QUICK_PRESETS);

    const fallbackUndefined = getQuickPresets(undefined);
    assert.deepStrictEqual(fallbackUndefined, QUICK_PRESETS);

    // Fallback getPresetRange
    const rangeXv = getPresetRange("xv", [], null, "2026-10-18");
    assert.deepStrictEqual(rangeXv, { startDate: "2023-04-10", endDate: "2026-10-18" });

    const rangeXiv = getPresetRange("xiv", [], null, "2026-10-18");
    assert.deepStrictEqual(rangeXiv, { startDate: "2019-04-04", endDate: "2023-04-09" });
  });
});

describe("visible memberships", () => {
  const api = [
    { id: "16", number: 16, start_date: "2027-03-30", end_date: "2099-12-31" },
    { id: "15", number: 15, start_date: "2023-04-10", end_date: "2027-03-29" },
    { id: "14", number: 14, start_date: "2019-04-04", end_date: "2023-04-09" },
    { id: "13", number: 13, start_date: "2015-03-30", end_date: "2019-04-03" },
  ];

  it("hides a newly elected membership until it convenes", () => {
    const ids = visibleMemberships(api, "2027-03-29").map((m) => m.id);
    assert.deepStrictEqual(ids, ["15", "14"]);
    // The XV preset stays "current" right up to the day before XVI convenes
    const presets = getQuickPresets(visibleMemberships(api, "2027-03-29"), "2027-03-29");
    assert.strictEqual(presets[0].label, "XV Riigikogu (2023–praegu)");
  });

  it("shows it from the convening day", () => {
    const ids = visibleMemberships(api, "2027-03-30").map((m) => m.id);
    assert.deepStrictEqual(ids, ["16", "15", "14"]);
  });

  it("handles missing data", () => {
    assert.deepStrictEqual(visibleMemberships(undefined), []);
    assert.deepStrictEqual(visibleMemberships(null), []);
  });
});

describe("date keys", () => {
  it("accepts real calendar days", () => {
    for (const value of ["2026-10-21", "2024-02-29", "2019-04-04"]) {
      assert.equal(isValidDateKey(value), true, value);
    }
  });

  it("rejects impossible days and other formats", () => {
    for (const value of [
      "2026-13-45",
      "2026-02-29",
      "2026-04-31",
      "2026-00-10",
      "2026-1-5",
      "21.10.2026",
      "abc",
      "",
      null,
      undefined,
    ]) {
      assert.equal(isValidDateKey(value), false, String(value));
    }
  });
});
