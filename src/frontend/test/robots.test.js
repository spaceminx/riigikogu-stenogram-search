import { describe, it } from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import { KNOWN_BOT_UA_REGEX } from "../middleware.js";

const robots = fs.readFileSync(new URL("../public/robots.txt", import.meta.url), "utf-8");

// Groups of consecutive User-agent lines followed by their rules (RFC 9309)
function groups(text) {
  const out = [];
  let current = null;
  for (const raw of text.split("\n")) {
    const line = raw.replace(/#.*/, "").trim();
    if (!line) continue;
    const [field, ...rest] = line.split(":");
    const key = field.trim().toLowerCase();
    const value = rest.join(":").trim();
    if (key === "user-agent") {
      if (!current || current.rules.length) {
        current = { agents: [], rules: [] };
        out.push(current);
      }
      current.agents.push(value.toLowerCase());
    } else if (current && ["allow", "disallow", "crawl-delay"].includes(key)) {
      current.rules.push({ key, value });
    }
  }
  return out;
}

function groupFor(agent) {
  const all = groups(robots);
  const name = agent.toLowerCase();
  return all.find((g) => g.agents.includes(name)) ?? all.find((g) => g.agents.includes("*"));
}

const blocksEverything = (g) => g.rules.some((r) => r.key === "disallow" && r.value === "/");

describe("robots.txt", () => {
  it("keeps link-preview bots and search engines out of the blocked groups", () => {
    // Every bot the middleware serves Open Graph tags to, plus the main search engines
    const names = KNOWN_BOT_UA_REGEX.source.replace(/^\(|\)$/g, "").split("|");
    for (const name of [...names, "Googlebot", "bingbot"]) {
      assert.ok(!blocksEverything(groupFor(name)), `${name} must not be blocked`);
    }
  });

  it("blocks SEO crawlers and leaves AI assistants to the general rules", () => {
    for (const name of ["AhrefsBot", "SemrushBot", "MJ12bot", "DotBot"]) {
      assert.ok(blocksEverything(groupFor(name)), `${name} should be blocked`);
    }
    for (const name of ["GPTBot", "ClaudeBot", "PerplexityBot"]) {
      assert.ok(!blocksEverything(groupFor(name)), `${name} is not blocked for now`);
    }
  });

  it("keeps search and filtered views out, the favicon and sitemap in", () => {
    const rules = groupFor("*").rules;
    const has = (key, value) => rules.some((r) => r.key === key && r.value === value);
    assert.ok(has("disallow", "/otsing"));
    assert.ok(has("disallow", "/*?"));
    assert.ok(has("allow", "/favicon.svg")); // loaded as /favicon.svg?v=2
    assert.match(robots, /^Sitemap: https:\/\/www\.riigivaade\.me\/sitemap\.xml$/m);
  });
});
