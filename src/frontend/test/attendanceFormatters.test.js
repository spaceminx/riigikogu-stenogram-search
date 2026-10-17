import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { formatMetricRatio, formatVoteSplit } from "../src/lib/attendanceFormatters.js";

describe("attendanceFormatters", () => {
  describe("formatMetricRatio", () => {
    it("formats percentage and counts correctly for Ando Kiviberg sample", () => {
      // 203 / 328 presence checks (61.9%)
      assert.strictEqual(formatMetricRatio(61.9, 203, 328), "62% · 203/328");
      // 822 / 989 votes (83.1%)
      assert.strictEqual(formatMetricRatio(83.1, 822, 989), "83% · 822/989");
    });

    it("calculates percentage when pct is not provided", () => {
      assert.strictEqual(formatMetricRatio(null, 203, 328), "62% · 203/328");
      assert.strictEqual(formatMetricRatio(undefined, 822, 989), "83% · 822/989");
      assert.strictEqual(formatMetricRatio(null, 5, 10), "50% · 5/10");
    });

    it("returns dash for zero or null total", () => {
      assert.strictEqual(formatMetricRatio(null, 0, 0), "–");
      assert.strictEqual(formatMetricRatio(0, 0, 0), "–");
      assert.strictEqual(formatMetricRatio(null, 0, null), "–");
      assert.strictEqual(formatMetricRatio(null, 0, -1), "–");
    });

    it("handles zero count with positive total", () => {
      assert.strictEqual(formatMetricRatio(0.0, 0, 100), "0% · 0/100");
    });
  });

  describe("formatVoteSplit", () => {
    it("formats integer split for tables (e.g. Ando Kiviberg numbers)", () => {
      // 89 / 989 = 8.998% -> 9%, 78 / 989 = 7.886% -> 8%
      assert.strictEqual(formatVoteSplit(89, 78, 989), "ei hääletanud 9% · puudus 8%");
    });

    it("formats 1-decimal split with Estonian comma for PersonView", () => {
      assert.strictEqual(
        formatVoteSplit(89, 78, 989, { decimals: 1 }),
        "ei hääletanud 9,0% · puudus 7,9%"
      );
    });

    it("handles round percentages with decimal option", () => {
      assert.strictEqual(
        formatVoteSplit(10, 5, 100, { decimals: 1 }),
        "ei hääletanud 10,0% · puudus 5,0%"
      );
    });

    it("returns empty string when total is 0 or null", () => {
      assert.strictEqual(formatVoteSplit(0, 0, 0), "");
      assert.strictEqual(formatVoteSplit(null, null, null), "");
      assert.strictEqual(formatVoteSplit(5, 5, 0), "");
    });
  });
});
