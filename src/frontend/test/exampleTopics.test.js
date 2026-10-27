import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { EXAMPLE_TOPICS, getTopicQuery } from "../src/lib/exampleTopics.js";
import { parseQueryToGroups } from "../src/lib/queryHelpers.js";

describe("exampleTopics", () => {
  it("builds an OR query with phrases in quotes", () => {
    const energy = EXAMPLE_TOPICS.find((t) => t.label === "Energeetika");
    assert.strictEqual(getTopicQuery(energy), 'tuulepark, tuumajaam, põlevkivi, "elektri hind"');
  });

  it("every topic opens in the search box as the same blocks", () => {
    for (const topic of EXAMPLE_TOPICS) {
      assert.deepStrictEqual(parseQueryToGroups(getTopicQuery(topic)), topic.groups, topic.label);
    }
  });

  it("has unique labels and at least two blocks per topic", () => {
    const labels = EXAMPLE_TOPICS.map((t) => t.label);
    assert.strictEqual(new Set(labels).size, labels.length);
    for (const topic of EXAMPLE_TOPICS) {
      assert.ok(topic.groups.length >= 2, topic.label);
    }
  });
});
