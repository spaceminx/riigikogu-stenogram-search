import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  filterFactionsByRole,
  formatPeriods,
  getSeatCounts,
  getSeatSegments,
  isFullTerm,
  joinedLater,
  splitMembers,
} from "../src/lib/factionsUtils.js";

const XV_START = "2023-04-10";
const XV_END = "2027-02-25";
const XIV = ["2019-04-04", "2023-04-09"];

const member = (periods, extra = {}) => ({ uuid: "a", periods, ...extra });

describe("factionsUtils", () => {
  it("formats closed and ongoing periods", () => {
    assert.strictEqual(
      formatPeriods([
        { start: "2023-04-10", end: "2024-07-23" },
        { start: "2025-03-25", end: null },
      ]),
      "10.04.2023–23.07.2024, alates 25.03.2025"
    );
    assert.strictEqual(formatPeriods([]), "");
  });

  it("counts members who joined in the first month as there from the start", () => {
    assert.strictEqual(joinedLater(member([{ start: "2023-04-11", end: null }]), XV_START), false);
    assert.strictEqual(joinedLater(member([{ start: "2023-05-11", end: null }]), XV_START), false);
    assert.strictEqual(joinedLater(member([{ start: "2023-05-12", end: null }]), XV_START), true);
  });

  it("needs no dates only for one period covering the whole membership", () => {
    assert.strictEqual(
      isFullTerm(member([{ start: "2023-04-11", end: null }]), XV_START, XV_END),
      true
    );
    // Returned after a suspended mandate
    assert.strictEqual(
      isFullTerm(
        member([
          { start: "2023-04-10", end: "2024-07-23" },
          { start: "2025-03-25", end: null },
        ]),
        XV_START,
        XV_END
      ),
      false
    );
    assert.strictEqual(
      isFullTerm(member([{ start: "2024-07-08", end: null }]), XV_START, XV_END),
      false
    );
    // A past membership: periods end shortly before the next one starts
    assert.strictEqual(
      isFullTerm(member([{ start: "2019-04-04", end: "2023-04-01" }]), ...XIV),
      true
    );
    assert.strictEqual(
      isFullTerm(member([{ start: "2019-04-04", end: "2021-01-26" }]), ...XIV),
      false
    );
    // Two periods near the end are still a break worth showing
    assert.strictEqual(
      isFullTerm(
        member([
          { start: "2019-04-04", end: "2023-03-20" },
          { start: "2023-03-25", end: "2023-04-05" },
        ]),
        ...XIV
      ),
      false
    );
  });

  it("splits current and former members", () => {
    const { current, former } = splitMembers({
      members: [
        { uuid: "a", current: true },
        { uuid: "b", current: false },
      ],
    });
    assert.deepStrictEqual([current.map((m) => m.uuid), former.map((m) => m.uuid)], [["a"], ["b"]]);
  });

  it("filters by role and keeps every faction when no role is chosen", () => {
    const factions = [
      { faction: "A", role: "coalition" },
      { faction: "B", role: "opposition" },
      { faction: "C", role: "none" },
    ];
    assert.deepStrictEqual(
      filterFactionsByRole(factions, "coalition").map((f) => f.faction),
      ["A"]
    );
    assert.strictEqual(filterFactionsByRole(factions, "").length, 3);
  });

  it("counts current seats by role and drops empty bar segments", () => {
    const counts = getSeatCounts([
      { role: "coalition", current_count: 36 },
      { role: "coalition", current_count: 12 },
      { role: "opposition", current_count: 33 },
      { role: "none", current_count: 20 },
    ]);
    assert.deepStrictEqual(counts, { coalition: 48, opposition: 33, none: 20 });
    assert.deepStrictEqual(
      getSeatSegments({ coalition: 48, opposition: 53, none: 0 }).map((s) => s.key),
      ["coalition", "opposition"]
    );
  });
});
