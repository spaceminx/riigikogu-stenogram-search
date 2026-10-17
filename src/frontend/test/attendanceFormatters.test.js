import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  formatMetricRatio,
  formatPercent,
  formatVoteSplit,
  isSmallSample,
  sortAttendanceItems,
} from "../src/lib/attendanceFormatters.js";

describe("attendanceFormatters", () => {
  describe("formatPercent", () => {
    it("formats 61.9 to Estonian decimal comma", () => {
      assert.strictEqual(formatPercent(61.9), "61,9%");
      assert.strictEqual(formatPercent(83.1), "83,1%");
    });

    it("formats 100 to 100%", () => {
      assert.strictEqual(formatPercent(100), "100%");
      assert.strictEqual(formatPercent(100.0), "100%");
      assert.strictEqual(formatPercent("100"), "100%");
    });

    it("formats null / undefined / empty to dash", () => {
      assert.strictEqual(formatPercent(null), "–");
      assert.strictEqual(formatPercent(undefined), "–");
      assert.strictEqual(formatPercent(""), "–");
      assert.strictEqual(formatPercent(NaN), "–");
    });

    it("formats zero to 0%", () => {
      assert.strictEqual(formatPercent(0), "0%");
      assert.strictEqual(formatPercent(0.0), "0%");
    });

    it("respects decimals = 0", () => {
      assert.strictEqual(formatPercent(61.9, 0), "62%");
      assert.strictEqual(formatPercent(83.1, 0), "83%");
    });
  });

  describe("formatMetricRatio", () => {
    it("formats percentage with decimal comma and counts correctly for Ando Kiviberg sample", () => {
      // 203 / 328 presence checks (61.9%)
      assert.strictEqual(formatMetricRatio(61.9, 203, 328), "61,9% · 203/328");
      // 822 / 989 votes (83.1%)
      assert.strictEqual(formatMetricRatio(83.1, 822, 989), "83,1% · 822/989");
    });

    it("calculates percentage when pct is not provided", () => {
      assert.strictEqual(formatMetricRatio(null, 203, 328), "61,9% · 203/328");
      assert.strictEqual(formatMetricRatio(undefined, 822, 989), "83,1% · 822/989");
      assert.strictEqual(formatMetricRatio(null, 5, 10), "50,0% · 5/10");
    });

    it("returns dash for zero or null total", () => {
      assert.strictEqual(formatMetricRatio(null, 0, 0), "–");
      assert.strictEqual(formatMetricRatio(0, 0, 0), "–");
      assert.strictEqual(formatMetricRatio(null, 0, null), "–");
      assert.strictEqual(formatMetricRatio(null, 0, -1), "–");
    });

    it("handles 100% and 0% cleanly", () => {
      assert.strictEqual(formatMetricRatio(100, 10, 10), "100% · 10/10");
      assert.strictEqual(formatMetricRatio(0.0, 0, 100), "0% · 0/100");
    });
  });

  describe("formatVoteSplit", () => {
    it("formats 1-decimal split with Estonian comma by default", () => {
      // 89 / 989 = 8.998% -> 9,0%, 78 / 989 = 7.886% -> 7,9%
      assert.strictEqual(formatVoteSplit(89, 78, 989), "ei hääletanud 9,0% · puudus 7,9%");
    });

    it("formats integer split when decimals: 0 is specified", () => {
      assert.strictEqual(
        formatVoteSplit(89, 78, 989, { decimals: 0 }),
        "ei hääletanud 9% · puudus 8%"
      );
    });

    it("handles round percentages with 1 decimal", () => {
      assert.strictEqual(formatVoteSplit(10, 5, 100), "ei hääletanud 10,0% · puudus 5,0%");
    });

    it("returns empty string when total is 0 or null", () => {
      assert.strictEqual(formatVoteSplit(0, 0, 0), "");
      assert.strictEqual(formatVoteSplit(null, null, null), "");
      assert.strictEqual(formatVoteSplit(5, 5, 0), "");
    });
  });

  describe("isSmallSample", () => {
    it("checks votes_total < 50 for votes", () => {
      assert.strictEqual(isSmallSample({ votes_total: 4 }, "votes_voted_pct"), true);
      assert.strictEqual(isSmallSample({ votes_total: 49 }, "votes_voted_pct"), true);
      assert.strictEqual(isSmallSample({ votes_total: 50 }, "votes_voted_pct"), false);
      assert.strictEqual(isSmallSample({ votes_total: 500 }, "votes_voted_pct"), false);
    });

    it("checks total_checks < 20 for registration", () => {
      assert.strictEqual(isSmallSample({ total_checks: 19 }, "registered_pct"), true);
      assert.strictEqual(isSmallSample({ total_checks: 20 }, "registered_pct"), false);
      assert.strictEqual(isSmallSample({ total_sessions: 5 }, "registered_pct"), true);
    });
  });

  describe("sortAttendanceItems", () => {
    const items = [
      { name: "Minister", votes_voted_pct: 100.0, votes_total: 5, votes_voted: 5 },
      { name: "Active1", votes_voted_pct: 85.0, votes_total: 500, votes_voted: 425 },
      { name: "Active2", votes_voted_pct: 85.0, votes_total: 600, votes_voted: 510 },
      { name: "LowActive", votes_voted_pct: 60.0, votes_total: 400, votes_voted: 240 },
      { name: "SmallLow", votes_voted_pct: 50.0, votes_total: 10, votes_voted: 5 },
    ];

    it("partitions small samples (< 50 votes) to bottom in descending sort", () => {
      const sorted = sortAttendanceItems(items, {
        key: "votes_voted_pct",
        direction: "descending",
      });
      // Sufficient block: Active2 (85%, 600), Active1 (85%, 500), LowActive (60%, 400)
      // Small block: Minister (100%, 5), SmallLow (50%, 10)
      assert.strictEqual(sorted[0].name, "Active2");
      assert.strictEqual(sorted[1].name, "Active1");
      assert.strictEqual(sorted[2].name, "LowActive");
      assert.strictEqual(sorted[3].name, "Minister");
      assert.strictEqual(sorted[4].name, "SmallLow");
    });

    it("partitions small samples to bottom even in ascending sort", () => {
      const sorted = sortAttendanceItems(items, {
        key: "votes_voted_pct",
        direction: "ascending",
      });
      // Sufficient block ascending: LowActive (60%), Active1 (85%), Active2 (85%)
      // Small block ascending: SmallLow (50%), Minister (100%)
      assert.strictEqual(sorted[0].name, "LowActive");
      assert.strictEqual(sorted[1].name, "Active2");
      assert.strictEqual(sorted[2].name, "Active1");
      assert.strictEqual(sorted[3].name, "SmallLow");
      assert.strictEqual(sorted[4].name, "Minister");
    });

    it("partitions small samples (< 20 checks) when sorting by registered_pct", () => {
      const checkItems = [
        { name: "BriefMP", registered_pct: 100.0, total_checks: 5 },
        { name: "RegularMP", registered_pct: 70.0, total_checks: 100 },
        { name: "VeryActiveMP", registered_pct: 90.0, total_checks: 120 },
      ];
      const sorted = sortAttendanceItems(checkItems, {
        key: "registered_pct",
        direction: "descending",
      });
      assert.strictEqual(sorted[0].name, "VeryActiveMP");
      assert.strictEqual(sorted[1].name, "RegularMP");
      assert.strictEqual(sorted[2].name, "BriefMP");
    });
  });
});
