import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  injectOpenGraphTags,
  isBotUserAgent,
  parseRouteInfo,
  resolveOgMetadata,
} from "../middleware.js";

describe("Open Graph middleware helpers", () => {
  describe("isBotUserAgent", () => {
    it("identifies social media bots and search engine crawlers", () => {
      assert.strictEqual(
        isBotUserAgent("facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"),
        true
      );
      assert.strictEqual(isBotUserAgent("Twitterbot/1.0"), true);
      assert.strictEqual(
        isBotUserAgent("Slackbot-LinkExpanding 1.0 (+https://api.slack.com/robots)"),
        true
      );
      assert.strictEqual(isBotUserAgent("LinkedInBot/1.0"), true);
      assert.strictEqual(
        isBotUserAgent("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"),
        true
      );
      assert.strictEqual(isBotUserAgent("TelegramBot (like TwitterBot)"), true);
    });

    it("rejects normal browser user agents", () => {
      assert.strictEqual(
        isBotUserAgent(
          "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        false
      );
      assert.strictEqual(
        isBotUserAgent(
          "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
        ),
        false
      );
      assert.strictEqual(isBotUserAgent(""), false);
      assert.strictEqual(isBotUserAgent(null), false);
    });
  });

  describe("parseRouteInfo", () => {
    it("extracts routeType and id for supported entities", () => {
      assert.deepStrictEqual(parseRouteInfo("/saadik/test-uuid-123"), {
        routeType: "saadik",
        id: "test-uuid-123",
      });
      assert.deepStrictEqual(parseRouteInfo("/kone/550405"), {
        routeType: "kone",
        id: "550405",
      });
      assert.deepStrictEqual(parseRouteInfo("/eelnou/draft-uuid-456/"), {
        routeType: "eelnou",
        id: "draft-uuid-456",
      });
      assert.deepStrictEqual(parseRouteInfo("/haaletus/vote-uuid-789"), {
        routeType: "haaletus",
        id: "vote-uuid-789",
      });
      assert.deepStrictEqual(parseRouteInfo("/istung/2024-03-15"), {
        routeType: "istung",
        id: "2024-03-15",
      });
    });

    it("returns null for non-supported paths", () => {
      assert.strictEqual(parseRouteInfo("/"), null);
      assert.strictEqual(parseRouteInfo("/otsing"), null);
      assert.strictEqual(parseRouteInfo("/kohalolek"), null);
      assert.strictEqual(parseRouteInfo("/andmed"), null);
    });
  });

  describe("resolveOgMetadata", () => {
    it("resolves saadik with photo_url as og:image", () => {
      const meta = resolveOgMetadata("saadik", "uuid-1", {
        full_name: "Kaja Kallas",
        photo_url: "https://api.riigikogu.ee/photo.jpg",
      });
      assert.strictEqual(meta.title, "Kaja Kallas — Riigivaade");
      assert.strictEqual(meta.type, "profile");
      assert.strictEqual(meta.url, "https://www.riigivaade.me/saadik/uuid-1");
      assert.strictEqual(meta.image, "https://api.riigikogu.ee/photo.jpg");
    });

    it("does NOT include og:image for other entity types", () => {
      const speechMeta = resolveOgMetadata("kone", "123", {
        speaker: "Jüri Ratas",
        date: "2024-02-10",
        text: "Austatud esimees! Head kolleegid!",
      });
      assert.strictEqual(speechMeta.image, null);

      const voteMeta = resolveOgMetadata("haaletus", "v-1", {
        description: "Seaduseelnõu lõpphääletus",
      });
      assert.strictEqual(voteMeta.image, null);

      const draftMeta = resolveOgMetadata("eelnou", "d-1", {
        title: "Riigieelarve seadus",
      });
      assert.strictEqual(draftMeta.image, null);

      const sessionMeta = resolveOgMetadata("istung", "2024-02-10", {});
      assert.strictEqual(sessionMeta.image, null);
    });
  });

  describe("injectOpenGraphTags", () => {
    const baseHtml = `<!doctype html><html><head><title>Orig</title></head><body><div id="root"></div></body></html>`;

    it("injects og tags before </head>", () => {
      const meta = {
        title: "Kaja Kallas — Riigivaade",
        description: "Kaja Kallase profiil",
        url: "https://www.riigivaade.me/saadik/uuid-1",
        type: "profile",
        image: "https://api.riigikogu.ee/photo.jpg",
      };

      const out = injectOpenGraphTags(baseHtml, meta);
      assert.ok(out.includes('<meta property="og:title" content="Kaja Kallas — Riigivaade" />'));
      assert.ok(out.includes('<meta property="og:description" content="Kaja Kallase profiil" />'));
      assert.ok(
        out.includes('<meta property="og:url" content="https://www.riigivaade.me/saadik/uuid-1" />')
      );
      assert.ok(out.includes('<meta property="og:type" content="profile" />'));
      assert.ok(out.includes('<meta property="og:site_name" content="Riigivaade" />'));
      assert.ok(
        out.includes('<meta property="og:image" content="https://api.riigikogu.ee/photo.jpg" />')
      );
      assert.ok(out.indexOf('<meta property="og:title"') < out.indexOf("</head>"));
    });

    it("escapes quotes and special characters in metadata", () => {
      const meta = {
        title: 'Hääletus "Maksuseadus & muudatused" <1> — Riigivaade',
        description: 'Kirjeldus "jutumärkidega"',
        url: "https://www.riigivaade.me/haaletus/1",
        type: "article",
      };

      const out = injectOpenGraphTags(baseHtml, meta);
      assert.ok(out.includes("&quot;Maksuseadus &amp; muudatused&quot; &lt;1&gt;"));
      assert.ok(out.includes("&quot;jutumärkidega&quot;"));
      assert.ok(!out.includes('<meta property="og:image"'));
    });
  });
});
