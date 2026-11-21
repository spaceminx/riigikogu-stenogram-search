import { describe, it } from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import { buildNotFoundHtml, NOT_FOUND_TITLE } from "../notFoundPage.js";

const indexHtml = fs.readFileSync(new URL("../index.html", import.meta.url), "utf-8");

describe("buildNotFoundHtml", () => {
  const html = buildNotFoundHtml(indexHtml);

  it("keeps the app shell so React renders the 404 view", () => {
    assert.ok(html.includes('<div id="root"></div>'));
    assert.ok(html.includes('<script type="module"'));
  });

  it("sets the 404 title once and marks the page noindex", () => {
    assert.strictEqual(html.match(/<title>/g).length, 1);
    assert.ok(html.includes(`<title>${NOT_FOUND_TITLE}</title>`));
    assert.strictEqual(html.match(/name="robots"/g).length, 1);
    assert.ok(html.includes('<meta name="robots" content="noindex" />'));
  });

  it("drops og:url and keeps the other site metadata", () => {
    assert.ok(!html.includes('property="og:url"'));
    assert.ok(html.includes('property="og:image"'));
    assert.ok(html.includes('rel="icon"'));
  });

  it("fails loudly when the shell has no title", () => {
    assert.throws(() => buildNotFoundHtml("<html><head></head><body></body></html>"));
  });
});
