import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { parseQueryToGroups, mergeInputToGroups } from "../src/lib/queryHelpers.js";

describe("queryHelpers mergeInputToGroups and parseQueryToGroups", () => {
  it('parses "eelarve, maks" into two groups', () => {
    const result = parseQueryToGroups("eelarve, maks");
    assert.deepStrictEqual(result, [["eelarve"], ["maks"]]);

    const merged = mergeInputToGroups([[]], "eelarve, maks");
    assert.deepStrictEqual(merged, [["eelarve"], ["maks"]]);
  });

  it('parses "\\"riigi eelarve\\" kärped, putin" into two groups with phrase and word', () => {
    const result = parseQueryToGroups('"riigi eelarve" kärped, putin');
    assert.deepStrictEqual(result, [["riigi eelarve", "kärped"], ["putin"]]);

    const merged = mergeInputToGroups([[]], '"riigi eelarve" kärped, putin');
    assert.deepStrictEqual(merged, [["riigi eelarve", "kärped"], ["putin"]]);
  });

  it('parses "\\"Eesti 200\\"" into one phrase pill', () => {
    const result = parseQueryToGroups('"Eesti 200"');
    assert.deepStrictEqual(result, [["Eesti 200"]]);

    const merged = mergeInputToGroups([[]], '"Eesti 200"');
    assert.deepStrictEqual(merged, [["Eesti 200"]]);
  });

  it("merges typed input into existing non-empty groups", () => {
    const initial = [["vanasõna"]];
    const merged = mergeInputToGroups(initial, "eelarve, maks");
    assert.deepStrictEqual(merged, [["vanasõna", "eelarve"], ["maks"]]);
  });

  it("handles empty or whitespace input gracefully", () => {
    const initial = [["vanasõna"]];
    assert.deepStrictEqual(mergeInputToGroups(initial, ""), [["vanasõna"]]);
    assert.deepStrictEqual(mergeInputToGroups(initial, "   "), [["vanasõna"]]);
  });
});
