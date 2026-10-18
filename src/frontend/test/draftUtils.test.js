import test from "node:test";
import assert from "node:assert/strict";
import {
  STAGE_LABELS,
  formatStageLabel,
  sortReadingsByDate,
  groupVotingsByReading,
  getOtherVotings,
  getRiigikoguDraftUrl,
} from "../src/lib/draftUtils.js";

test("draft utilities", async (t) => {
  await t.test("formatStageLabel maps standard reading stages", () => {
    assert.equal(STAGE_LABELS.ESIMENE_LUGEMINE, "Esimene lugemine");
    assert.equal(STAGE_LABELS.TEINE_LUGEMINE, "Teine lugemine");
    assert.equal(STAGE_LABELS.KOLMAS_LUGEMINE, "Kolmas lugemine");

    assert.equal(formatStageLabel("ESIMENE_LUGEMINE"), "Esimene lugemine");
    assert.equal(formatStageLabel("TEINE_LUGEMINE"), "Teine lugemine");
    assert.equal(formatStageLabel("KOLMAS_LUGEMINE"), "Kolmas lugemine");

    // Decision value does not override standard reading stages
    assert.equal(formatStageLabel("ESIMENE_LUGEMINE", "Lõpetatud"), "Esimene lugemine");
  });

  await t.test("formatStageLabel handles non-standard codes and fallback", () => {
    // When decision_value is provided for non-standard code
    assert.equal(formatStageLabel("VASTU_VOETUD", "Vastu võetud"), "Vastu võetud");
    assert.equal(formatStageLabel("ARUTELU", "Esimene arutelu"), "Esimene arutelu");

    // When decision_value is missing, converts code with _ to sentence case
    assert.equal(formatStageLabel("VASTU_VOETUD"), "Vastu voetud");
    assert.equal(formatStageLabel("MUUDATUS_ETTEPANEKUD"), "Muudatus ettepanekud");

    // Empty or null inputs
    assert.equal(formatStageLabel(null, "Esimene"), "Esimene");
    assert.equal(formatStageLabel(undefined, "Teine"), "Teine");
    assert.equal(formatStageLabel(null, null), "");
    assert.equal(formatStageLabel("", ""), "");
  });

  await t.test("sortReadingsByDate sorts readings chronologically", () => {
    const readings = [
      { sitting_date: "2026-10-14", order: 2 },
      { sitting_date: "2024-05-29", order: 1 },
      { sitting_date: "2026-10-14", order: 1 },
      { sitting_date: "2025-06-17", order: 1 },
    ];
    const sorted = sortReadingsByDate(readings);
    assert.deepEqual(
      sorted.map((r) => `${r.sitting_date}#${r.order}`),
      ["2024-05-29#1", "2025-06-17#1", "2026-10-14#1", "2026-10-14#2"]
    );
    assert.deepEqual(sortReadingsByDate([]), []);
    assert.deepEqual(sortReadingsByDate(null), []);
  });

  await t.test("groupVotingsByReading assigns votings to readings by voting_uuids", () => {
    const readings = [
      {
        agenda_item_uuid: "ag-1",
        voting_uuids: ["v-1", "v-2"],
      },
      {
        agenda_item_uuid: "ag-2",
        voting_uuids: [],
      },
      {
        agenda_item_uuid: "ag-3",
        voting_uuids: ["v-3"],
      },
    ];

    const votings = [
      { uuid: "v-1", description: "Hääletus 1" },
      { uuid: "v-2", description: "Hääletus 2" },
      { uuid: "v-3", description: "Hääletus 3" },
      { uuid: "v-4", description: "Muu hääletus" },
    ];

    const grouped = groupVotingsByReading(readings, votings);
    assert.equal(grouped.length, 3);
    assert.deepEqual(
      grouped[0].votings.map((v) => v.uuid),
      ["v-1", "v-2"]
    );
    assert.deepEqual(grouped[1].votings, []);
    assert.deepEqual(
      grouped[2].votings.map((v) => v.uuid),
      ["v-3"]
    );
  });

  await t.test("getOtherVotings returns votings belonging to no reading", () => {
    const readings = [
      {
        agenda_item_uuid: "ag-1",
        voting_uuids: ["v-1", "v-2"],
      },
    ];

    const votings = [
      { uuid: "v-1", description: "Hääletus 1" },
      { uuid: "v-2", description: "Hääletus 2" },
      { uuid: "v-3", description: "Muu hääletus 1" },
      { uuid: "v-4", description: "Muu hääletus 2" },
    ];

    const other = getOtherVotings(readings, votings);
    assert.deepEqual(
      other.map((v) => v.uuid),
      ["v-3", "v-4"]
    );

    // When all votings are assigned
    const allAssigned = getOtherVotings(
      [{ voting_uuids: ["v-1", "v-2"] }],
      [{ uuid: "v-1" }, { uuid: "v-2" }]
    );
    assert.deepEqual(allAssigned, []);

    // Empty cases
    assert.deepEqual(getOtherVotings([], votings).length, 4);
    assert.deepEqual(getOtherVotings([], []), []);
    assert.deepEqual(getOtherVotings(null, null), []);
  });

  await t.test("getRiigikoguDraftUrl formats official draft page url", () => {
    assert.equal(
      getRiigikoguDraftUrl("b9fab890-fa21-4a69-9039-171a0015bc84"),
      "https://www.riigikogu.ee/tegevus/eelnoud/b9fab890-fa21-4a69-9039-171a0015bc84/"
    );
    assert.equal(getRiigikoguDraftUrl(""), "");
    assert.equal(getRiigikoguDraftUrl(null), "");
  });
});
