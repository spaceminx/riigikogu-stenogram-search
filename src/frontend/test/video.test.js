import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { parseVideoUrl, buildEmbedUrl } from "../src/lib/video.js";

describe("parseVideoUrl", () => {
  it("parses standard watch URL with t in seconds", () => {
    const res = parseVideoUrl("https://www.youtube.com/watch?v=Z5U3uEXFBC8&t=133");
    assert.deepEqual(res, { videoId: "Z5U3uEXFBC8", start: 133 });
  });

  it("parses watch URL with start param", () => {
    const res = parseVideoUrl("https://www.youtube.com/watch?v=Z5U3uEXFBC8&start=200");
    assert.deepEqual(res, { videoId: "Z5U3uEXFBC8", start: 200 });
  });

  it("parses watch URL without t param, defaulting start to 0", () => {
    const res = parseVideoUrl("https://www.youtube.com/watch?v=Z5U3uEXFBC8");
    assert.deepEqual(res, { videoId: "Z5U3uEXFBC8", start: 0 });
  });

  it("parses youtu.be short URL", () => {
    const res = parseVideoUrl("https://youtu.be/Z5U3uEXFBC8?t=45");
    assert.deepEqual(res, { videoId: "Z5U3uEXFBC8", start: 45 });
  });

  it("handles time with trailing s (e.g. 133s)", () => {
    const res = parseVideoUrl("https://www.youtube.com/watch?v=Z5U3uEXFBC8&t=133s");
    assert.deepEqual(res, { videoId: "Z5U3uEXFBC8", start: 133 });
  });

  it("returns null for invalid / non-youtube URLs", () => {
    assert.equal(parseVideoUrl(null), null);
    assert.equal(parseVideoUrl(""), null);
    assert.equal(parseVideoUrl("not a url"), null);
    assert.equal(parseVideoUrl("https://example.com/watch?v=Z5U3uEXFBC8"), null);
    assert.equal(parseVideoUrl("https://www.youtube.com/watch?v=short"), null); // < 11 chars
    assert.equal(parseVideoUrl("https://www.youtube.com/watch?v=too_long_video_id_here"), null);
    assert.equal(parseVideoUrl("https://www.youtube.com/channel/UC1234567890"), null);
  });
});

describe("buildEmbedUrl", () => {
  it("builds embed URL without end when end is omitted or null", () => {
    const url = buildEmbedUrl({ videoId: "Z5U3uEXFBC8", start: 133 });
    assert.equal(
      url,
      "https://www.youtube-nocookie.com/embed/Z5U3uEXFBC8?start=133&autoplay=1&rel=0"
    );
  });

  it("builds embed URL with end when duration is provided", () => {
    const url = buildEmbedUrl({ videoId: "Z5U3uEXFBC8", start: 133, end: 250 });
    assert.equal(
      url,
      "https://www.youtube-nocookie.com/embed/Z5U3uEXFBC8?start=133&end=250&autoplay=1&rel=0"
    );
  });

  it("omits end if end <= start", () => {
    const url = buildEmbedUrl({ videoId: "Z5U3uEXFBC8", start: 133, end: 100 });
    assert.equal(
      url,
      "https://www.youtube-nocookie.com/embed/Z5U3uEXFBC8?start=133&autoplay=1&rel=0"
    );
  });

  it("defaults start to 0 if not provided", () => {
    const url = buildEmbedUrl({ videoId: "Z5U3uEXFBC8" });
    assert.equal(
      url,
      "https://www.youtube-nocookie.com/embed/Z5U3uEXFBC8?start=0&autoplay=1&rel=0"
    );
  });

  it("throws error if videoId is invalid", () => {
    assert.throws(() => buildEmbedUrl({ videoId: "invalid" }));
  });
});
