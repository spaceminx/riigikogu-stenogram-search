import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  formatActivityShare,
  formatActivityTooltip,
  isNullPeriod,
  parseScaleParam,
  updateScaleParam,
} from "../src/lib/activityUtils.js";

describe("activityUtils", () => {
  describe("share formatting", () => {
    it("formats 0.035 to Estonian comma percentage '3,5%'", () => {
      assert.strictEqual(formatActivityShare(0.035), "3,5%");
      assert.strictEqual(formatActivityShare("0.035"), "3,5%");
    });

    it("formats 0.1 to 10%", () => {
      assert.strictEqual(formatActivityShare(0.1), "10%");
    });

    it("formats 0 to 0%", () => {
      assert.strictEqual(formatActivityShare(0), "0%");
      assert.strictEqual(formatActivityShare(0.0), "0%");
    });

    it("formats 1 to 100%", () => {
      assert.strictEqual(formatActivityShare(1), "100%");
    });

    it("handles null / undefined / invalid as null", () => {
      assert.strictEqual(formatActivityShare(null), null);
      assert.strictEqual(formatActivityShare(undefined), null);
      assert.strictEqual(formatActivityShare(""), null);
      assert.strictEqual(formatActivityShare("abc"), null);
    });

    it("formats tooltip in share mode with Estonian percent", () => {
      const item = { count: 7, total: 200, share: 0.035 };
      assert.strictEqual(formatActivityTooltip(item, "share"), "7 sõnavõttu 200-st (3,5%)");
    });
  });

  describe("null period rendering helper", () => {
    it("identifies null period correctly", () => {
      assert.strictEqual(isNullPeriod(null), true);
      assert.strictEqual(isNullPeriod(undefined), true);
      assert.strictEqual(isNullPeriod({ share: null }), true);
      assert.strictEqual(isNullPeriod({ count: 0, total: 0, share: null }), true);
    });

    it("identifies non-null period correctly", () => {
      assert.strictEqual(isNullPeriod({ share: 0 }), false);
      assert.strictEqual(isNullPeriod({ share: 0.035 }), false);
      assert.strictEqual(isNullPeriod({ count: 0, total: 50, share: 0 }), false);
    });

    it("formats null period tooltip as 'Istungeid polnud'", () => {
      assert.strictEqual(formatActivityTooltip({ share: null }, "share"), "Istungeid polnud");
      assert.strictEqual(
        formatActivityTooltip({ count: 0, total: 0, share: null }, "share"),
        "Istungeid polnud"
      );
    });

    it("formats zero-share period with sittings properly", () => {
      assert.strictEqual(
        formatActivityTooltip({ count: 0, total: 50, share: 0 }, "share"),
        "0 sõnavõttu 50-st (0%)"
      );
    });

    it("formats count scale tooltip with total when present", () => {
      assert.strictEqual(
        formatActivityTooltip({ count: 12, total: 100 }, "count"),
        "12 sõnavõttu (kokku 100 sõnavõttu)"
      );
      assert.strictEqual(formatActivityTooltip({ count: 12 }, "count"), "12 sõnavõttu");
    });
  });

  describe("URL param round trip", () => {
    it("parses scale query parameter with fallback to count", () => {
      assert.strictEqual(parseScaleParam("share"), "share");
      assert.strictEqual(parseScaleParam("count"), "count");
      assert.strictEqual(parseScaleParam(null), "count");
      assert.strictEqual(parseScaleParam(undefined), "count");
      assert.strictEqual(parseScaleParam("unknown"), "count");
    });

    it("updates URLSearchParams to share and back to count", () => {
      const initial = new URLSearchParams("q=mets&interval=monthly");
      const withShare = updateScaleParam(initial, "share");
      assert.strictEqual(withShare.get("scale"), "share");
      assert.strictEqual(withShare.toString(), "q=mets&interval=monthly&scale=share");

      // Round trip back to count deletes the parameter to keep URL clean
      const backToCount = updateScaleParam(withShare, "count");
      assert.strictEqual(backToCount.get("scale"), null);
      assert.strictEqual(parseScaleParam(backToCount.get("scale")), "count");
      assert.strictEqual(backToCount.toString(), "q=mets&interval=monthly");
    });
  });
});
