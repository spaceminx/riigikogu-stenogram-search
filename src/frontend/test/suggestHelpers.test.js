import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  isPrefixEligible,
  getNextHighlightedIndex,
  formatSuggestionCount,
} from "../src/lib/suggestHelpers.js";

describe("suggestHelpers", () => {
  describe("isPrefixEligible", () => {
    it("returns true for valid single-word prefixes >= 2 chars", () => {
      assert.strictEqual(isPrefixEligible("ee"), true);
      assert.strictEqual(isPrefixEligible("eelarve"), true);
      assert.strictEqual(isPrefixEligible("õp"), true);
      assert.strictEqual(isPrefixEligible("Seeder"), true);
    });

    it("returns false for inputs with spaces (multi-word phrases)", () => {
      assert.strictEqual(isPrefixEligible("eesti "), false);
      assert.strictEqual(isPrefixEligible(" eelarve"), false);
      assert.strictEqual(isPrefixEligible("riigi eelarve"), false);
      assert.strictEqual(isPrefixEligible("a b"), false);
    });

    it("returns false for single char or empty input", () => {
      assert.strictEqual(isPrefixEligible(""), false);
      assert.strictEqual(isPrefixEligible("a"), false);
      assert.strictEqual(isPrefixEligible("õ"), false);
    });

    it("returns false for non-string or overlong input", () => {
      assert.strictEqual(isPrefixEligible(null), false);
      assert.strictEqual(isPrefixEligible(undefined), false);
      assert.strictEqual(isPrefixEligible(123), false);
      assert.strictEqual(isPrefixEligible("a".repeat(41)), false);
    });
  });

  describe("getNextHighlightedIndex", () => {
    it("returns -1 when totalCount <= 0", () => {
      assert.strictEqual(getNextHighlightedIndex(-1, 1, 0), -1);
      assert.strictEqual(getNextHighlightedIndex(0, 1, 0), -1);
    });

    it("starts from first item on ArrowDown from unhighlighted state", () => {
      assert.strictEqual(getNextHighlightedIndex(-1, 1, 5), 0);
    });

    it("starts from last item on ArrowUp from unhighlighted state", () => {
      assert.strictEqual(getNextHighlightedIndex(-1, -1, 5), 4);
    });

    it("moves forward and wraps around at the bottom", () => {
      assert.strictEqual(getNextHighlightedIndex(0, 1, 3), 1);
      assert.strictEqual(getNextHighlightedIndex(1, 1, 3), 2);
      assert.strictEqual(getNextHighlightedIndex(2, 1, 3), 0);
    });

    it("moves backward and wraps around at the top", () => {
      assert.strictEqual(getNextHighlightedIndex(2, -1, 3), 1);
      assert.strictEqual(getNextHighlightedIndex(1, -1, 3), 0);
      assert.strictEqual(getNextHighlightedIndex(0, -1, 3), 2);
    });
  });

  describe("formatSuggestionCount", () => {
    it("formats 1 as singular '1 kõne'", () => {
      assert.strictEqual(formatSuggestionCount(1), "1 kõne");
    });

    it("formats 0 and other numbers as plural '... kõnet'", () => {
      assert.strictEqual(formatSuggestionCount(0), "0 kõnet");
      assert.strictEqual(formatSuggestionCount(2), "2 kõnet");
      assert.strictEqual(formatSuggestionCount(15), "15 kõnet");
    });

    it("formats thousands with space separator", () => {
      assert.strictEqual(formatSuggestionCount(1040), "1 040 kõnet");
      assert.strictEqual(formatSuggestionCount(1953), "1 953 kõnet");
      assert.strictEqual(formatSuggestionCount(124258), "124 258 kõnet");
    });

    it("handles invalid inputs gracefully", () => {
      assert.strictEqual(formatSuggestionCount(null), "");
      assert.strictEqual(formatSuggestionCount(undefined), "");
      assert.strictEqual(formatSuggestionCount(NaN), "");
    });
  });
});
