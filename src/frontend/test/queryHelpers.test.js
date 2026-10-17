import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  parseQueryToGroups,
  mergeInputToGroups,
  serializeGroupsToQuery,
} from "../src/lib/queryHelpers.js";

describe("queryHelpers mergeInputToGroups and parseQueryToGroups", () => {
  it('typed "eesti inimesed" → one pill "eesti inimesed"', () => {
    const result = mergeInputToGroups([[]], "eesti inimesed");
    assert.deepStrictEqual(result, [["eesti inimesed"]]);
  });

  it('typed "  eesti   inimesed " → "eesti inimesed"', () => {
    const result = mergeInputToGroups([[]], "  eesti   inimesed ");
    assert.deepStrictEqual(result, [["eesti inimesed"]]);
  });

  it('typed "eelarve, maks" → ONE pill "eelarve, maks"', () => {
    const result = mergeInputToGroups([[]], "eelarve, maks");
    assert.deepStrictEqual(result, [["eelarve, maks"]]);
  });

  it('typed "\\"riigi eelarve\\"" → pill "riigi eelarve"', () => {
    const result = mergeInputToGroups([[]], '"riigi eelarve"');
    assert.deepStrictEqual(result, [["riigi eelarve"]]);
  });

  it('[["eelarve"]] + "+ JA" "eesti inimesed" → [["eelarve","eesti inimesed"]]', () => {
    const initial = [["eelarve"]];
    const result = mergeInputToGroups(initial, "eesti inimesed");
    assert.deepStrictEqual(result, [["eelarve", "eesti inimesed"]]);
  });

  it('"+ VÕI" adds a new group', () => {
    // When typed input is present
    const withTyped = mergeInputToGroups([["eelarve"]], "eesti inimesed");
    const orGroups = [...withTyped, []];
    assert.deepStrictEqual(orGroups, [["eelarve", "eesti inimesed"], []]);

    // When input is empty
    const initial = [["eelarve"]];
    const emptyOr = [...initial, []];
    assert.deepStrictEqual(emptyOr, [["eelarve"], []]);
  });

  it('parseQueryToGroups("eelarve, maks") → [["eelarve"],["maks"]] (old links unchanged)', () => {
    const result = parseQueryToGroups("eelarve, maks");
    assert.deepStrictEqual(result, [["eelarve"], ["maks"]]);
  });

  it('parses "\\"riigi eelarve\\" kärped, putin" into two groups with phrase and word', () => {
    const result = parseQueryToGroups('"riigi eelarve" kärped, putin');
    assert.deepStrictEqual(result, [["riigi eelarve", "kärped"], ["putin"]]);
  });

  it('parses "\\"Eesti 200\\"" into one phrase pill', () => {
    const result = parseQueryToGroups('"Eesti 200"');
    assert.deepStrictEqual(result, [["Eesti 200"]]);
  });

  it("handles empty or whitespace input gracefully", () => {
    const initial = [["vanasõna"]];
    assert.deepStrictEqual(mergeInputToGroups(initial, ""), [["vanasõna"]]);
    assert.deepStrictEqual(mergeInputToGroups(initial, "   "), [["vanasõna"]]);
    assert.deepStrictEqual(mergeInputToGroups(initial, '""'), [["vanasõna"]]);
  });

  it("serialises groups with spaces and commas properly", () => {
    const groups = [["eesti inimesed", "eelarve"], ["putin"]];
    const q = serializeGroupsToQuery(groups);
    assert.strictEqual(q, '"eesti inimesed" eelarve, putin');
  });
});
