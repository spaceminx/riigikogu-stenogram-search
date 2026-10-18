import test from "node:test";
import assert from "node:assert/strict";
import {
  DECISION_LABELS,
  formatDecision,
  formatMajorityPosition,
  computeNotVoted,
  formatTimeHHMM,
  formatOvernightTime,
  formatVotingSummary,
} from "../src/lib/votingUtils.js";

test("voting utilities", async (t) => {
  await t.test("DECISION_LABELS and formatDecision", () => {
    assert.equal(DECISION_LABELS.POOLT, "Poolt");
    assert.equal(DECISION_LABELS.VASTU, "Vastu");
    assert.equal(DECISION_LABELS.ERAPOOLETU, "Erapooletu");
    assert.equal(DECISION_LABELS.EI_HAALETANUD, "Ei hääletanud");
    assert.equal(DECISION_LABELS.PUUDUB, "Puudus");

    assert.equal(formatDecision("POOLT"), "Poolt");
    assert.equal(formatDecision("VASTU"), "Vastu");
    assert.equal(formatDecision("ERAPOOLETU"), "Erapooletu");
    assert.equal(formatDecision("EI_HAALETANUD"), "Ei hääletanud");
    assert.equal(formatDecision("PUUDUB"), "Puudus");
    assert.equal(formatDecision(null), "—");
    assert.equal(formatDecision(undefined), "—");
    assert.equal(formatDecision("UNKNOWN"), "UNKNOWN");
  });

  await t.test("formatMajorityPosition", () => {
    assert.equal(formatMajorityPosition("POOLT"), "Poolt");
    assert.equal(formatMajorityPosition("VASTU"), "Vastu");
    assert.equal(formatMajorityPosition(null), "—");
    assert.equal(formatMajorityPosition(undefined), "—");
  });

  await t.test("computeNotVoted", () => {
    // 92 present, 49 poolt, 4 vastu, 0 erapooletu -> 39
    const totals = {
      present: 92,
      in_favor: 49,
      against: 4,
      neutral: 0,
      absent: 9,
      abstained: 48, // abstained in DB is not_voted + absent, must be ignored
    };
    assert.equal(computeNotVoted(totals), 39);

    // handles 0 or null
    assert.equal(computeNotVoted(null), 0);
    assert.equal(computeNotVoted({}), 0);

    // clamps to 0 if present is less than votes
    assert.equal(computeNotVoted({ present: 10, in_favor: 8, against: 4, neutral: 0 }), 0);
  });

  await t.test("formatTimeHHMM", () => {
    assert.equal(formatTimeHHMM("10:15:30"), "10:15");
    assert.equal(formatTimeHHMM("2026-10-15T00:43:12"), "00:43");
    assert.equal(formatTimeHHMM(""), "");
    assert.equal(formatTimeHHMM(null), "");
  });

  await t.test("formatOvernightTime", () => {
    // Same day
    assert.equal(formatOvernightTime("10:15:00", "2026-10-14", "2026-10-14"), "10:15");

    // Overnight: sitting_date 2026-10-14, vote date 2026-10-15
    assert.equal(formatOvernightTime("00:43:00", "2026-10-14", "2026-10-15"), "00:43 (15.10.2026)");

    // With ISO string
    assert.equal(
      formatOvernightTime("2026-10-15T01:22:00", "2026-10-14", "2026-10-15"),
      "01:22 (15.10.2026)"
    );
  });

  await t.test("formatVotingSummary", () => {
    const totals = {
      present: 81,
      in_favor: 54,
      against: 22,
      neutral: 0,
      absent: 20,
    };
    // Ei hääletanud = 81 - 54 - 22 - 0 = 5
    assert.equal(
      formatVotingSummary(totals),
      "Poolt 54 · Vastu 22 · Erapooletu 0 · Ei hääletanud 5 · Puudus 20"
    );
    assert.equal(formatVotingSummary(null), "");
  });
});
