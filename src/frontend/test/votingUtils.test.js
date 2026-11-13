import test from "node:test";
import assert from "node:assert/strict";
import {
  DECISION_LABELS,
  formatDecision,
  formatMajorityPosition,
  computeNotVoted,
  formatTimeHHMM,
  getVotingTimeParts,
  getVotingSummaryParts,
  getVotingHeading,
  formatDocumentReference,
  getVoteBarSegments,
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

  await t.test("getVotingTimeParts", () => {
    const sameDay = {
      date: "2026-11-11",
      sitting_date: "2026-11-11",
      start_time: "2026-11-11T16:05:12.1",
    };
    assert.deepEqual(getVotingTimeParts(sameDay), {
      label: "11.11.2026 16:05",
      time: "16:05",
      voteDate: "2026-11-11",
      isOvernight: false,
      sittingLabel: "",
    });
    assert.equal(getVotingTimeParts(sameDay, { withDate: false }).label, "16:05");

    // The 11.11.2026 sitting ran until the next morning: the vote happened on 12.11
    const overnight = {
      date: "2026-11-12",
      sitting_date: "2026-11-11",
      start_time: "2026-11-12T03:40:58.373",
    };
    assert.deepEqual(getVotingTimeParts(overnight), {
      label: "12.11.2026 03:40",
      time: "03:40",
      voteDate: "2026-11-12",
      isOvernight: true,
      sittingLabel: "11.11. istung",
    });
    assert.equal(getVotingTimeParts(overnight, { withDate: false }).label, "12.11. kell 03:40");

    // Without `date` the vote date comes from start_time; a bare time falls back to the sitting
    assert.equal(
      getVotingTimeParts({ sitting_date: "2026-11-11", start_time: "2026-11-12T00:43:00" })
        .sittingLabel,
      "11.11. istung"
    );
    assert.deepEqual(
      getVotingTimeParts(
        { sitting_date: "2026-11-11", start_time: "10:15:00" },
        { withDate: false }
      ),
      {
        label: "10:15",
        time: "10:15",
        voteDate: "2026-11-11",
        isOvernight: false,
        sittingLabel: "",
      }
    );

    // Across the new year
    assert.equal(
      getVotingTimeParts({
        date: "2027-01-01",
        sitting_date: "2026-12-31",
        start_time: "2027-01-01T00:30:00",
      }).sittingLabel,
      "31.12. istung"
    );

    assert.equal(getVotingTimeParts(null).label, "");
  });

  await t.test("getVotingSummaryParts", () => {
    const totals = {
      present: 81,
      in_favor: 54,
      against: 22,
      neutral: 0,
      absent: 20,
    };
    // Ei hääletanud = 81 - 54 - 22 - 0 = 5
    assert.deepEqual(getVotingSummaryParts(totals), [
      "Poolt 54",
      "Vastu 22",
      "Erapooletu 0",
      "Ei hääletanud 5",
      "Puudus 20",
    ]);
    assert.deepEqual(getVotingSummaryParts(null), []);
  });

  await t.test("getVotingHeading puts the document first and keeps the step as a label", () => {
    const voting = {
      description: "Lõpphääletus",
      related_document: { reference: "855", title: "Relvaseaduse muutmise seadus", type: "DRAFT" },
    };
    assert.deepEqual(getVotingHeading(voting), {
      title: "Relvaseaduse muutmise seadus",
      stage: "Lõpphääletus",
    });
    assert.deepEqual(getVotingHeading(voting, { showDocument: false }), {
      title: "Lõpphääletus",
      stage: null,
    });
    assert.deepEqual(getVotingHeading({ description: "Päevakorra kinnitamine" }), {
      title: "Päevakorra kinnitamine",
      stage: null,
    });
  });

  await t.test("formatDocumentReference", () => {
    assert.equal(formatDocumentReference({ reference: "855", type: "DRAFT" }), "Eelnõu 855");
    assert.equal(
      formatDocumentReference({ reference: "OE 12", type: "otherQuestionDocument" }),
      "OE 12"
    );
    assert.equal(formatDocumentReference({ title: "Ilma numbrita" }), "");
    assert.equal(formatDocumentReference(null), "");
  });

  await t.test("getVoteBarSegments keeps non-zero groups in vote order", () => {
    const segments = getVoteBarSegments({
      present: 90,
      absent: 11,
      in_favor: 0,
      against: 18,
      neutral: 0,
    });
    assert.deepEqual(
      segments.map((s) => [s.key, s.value]),
      [
        ["against", 18],
        ["none", 72],
        ["absent", 11],
      ]
    );
    assert.deepEqual(getVoteBarSegments({ present: 0, absent: 0 }), []);
    assert.deepEqual(getVoteBarSegments(null), []);
  });
});
