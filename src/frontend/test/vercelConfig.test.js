import { describe, it } from "node:test";
import assert from "node:assert";
import fs from "node:fs";

const config = JSON.parse(fs.readFileSync(new URL("../vercel.json", import.meta.url), "utf-8"));

function cacheControlFor(source) {
  const rule = config.headers.find((r) => r.source === source);
  return rule?.headers.find((h) => h.key === "Cache-Control")?.value;
}

describe("vercel.json", () => {
  it("caches hashed assets for a year", () => {
    // File names under /assets/ carry a content hash, so a changed file gets a new URL
    assert.strictEqual(cacheControlFor("/assets/(.*)"), "public, max-age=31536000, immutable");
  });

  it("caches icons and the share image for a day", () => {
    const rule = config.headers.find((r) => r.source.includes("favicon.ico"));
    assert.ok(rule, "icon rule missing");
    for (const file of ["favicon.ico", "favicon.svg", "apple-touch-icon.png", "og-image.png"]) {
      assert.ok(rule.source.includes(file), `${file} not covered`);
      assert.ok(fs.existsSync(new URL(`../public/${file}`, import.meta.url)), `${file} missing`);
    }
    assert.strictEqual(
      rule.headers.find((h) => h.key === "Cache-Control").value,
      "public, max-age=86400"
    );
  });

  it("never marks index.html or routes as long-lived", () => {
    // The HTML names the current asset hashes; caching it would pin users to an old build
    const longLived = config.headers.filter((r) =>
      r.headers.some((h) => h.key === "Cache-Control" && /max-age=[1-9]/.test(h.value))
    );
    for (const rule of longLived) {
      assert.ok(!["/(.*)", "/", "/index.html"].includes(rule.source), rule.source);
    }
  });
});
