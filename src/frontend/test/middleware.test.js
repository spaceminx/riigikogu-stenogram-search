import { describe, it } from "node:test";
import assert from "node:assert/strict";
import middleware, {
  injectOpenGraphTags,
  isBotUserAgent,
  isValidSittingDate,
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
      assert.strictEqual(
        isBotUserAgent("Mozilla/5.0 (compatible; redditbot/1.0; +http://www.reddit.com/feedback)"),
        true
      );
      assert.strictEqual(
        isBotUserAgent("http.rb/5.1.1 (Mastodon/4.3.0; +https://mstdn.ee/)"),
        true
      );
      assert.strictEqual(isBotUserAgent("Mozilla/5.0 (compatible; Bluesky Cardyb/1.1)"), true);
      assert.strictEqual(isBotUserAgent("Mozilla/5.0 (compatible; Embedly/0.2)"), true);
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

  describe("isValidSittingDate", () => {
    it("accepts valid YYYY-MM-DD dates", () => {
      assert.strictEqual(isValidSittingDate("2026-10-14"), true);
      assert.strictEqual(isValidSittingDate("2024-02-29"), true); // leap year
      assert.strictEqual(isValidSittingDate("2019-01-01"), true);
    });

    it("rejects invalid or non-date strings", () => {
      assert.strictEqual(isValidSittingDate("2023-02-29"), false); // not leap year
      assert.strictEqual(isValidSittingDate("2026-13-01"), false); // invalid month
      assert.strictEqual(isValidSittingDate("2026-00-10"), false);
      assert.strictEqual(isValidSittingDate("2026-05-32"), false);
      assert.strictEqual(isValidSittingDate("invalid-date"), false);
      assert.strictEqual(isValidSittingDate("../attack"), false);
      assert.strictEqual(isValidSittingDate(""), false);
      assert.strictEqual(isValidSittingDate(null), false);
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

      const sessionMeta = resolveOgMetadata("istung", "2024-02-10", null);
      assert.strictEqual(sessionMeta.image, null);
      assert.strictEqual(sessionMeta.title, "Istung 10.02.2024 — Riigivaade");
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

    it("keeps $ replacement patterns in API text literal", () => {
      const out = injectOpenGraphTags(baseHtml, {
        title: "Hind $& ja $' — Riigivaade",
        description: "Kulu 5$` eurot",
      });
      assert.ok(out.includes('content="Hind $&amp; ja $&#39; — Riigivaade"'));
      assert.ok(out.includes('content="Kulu 5$` eurot"'));
      assert.strictEqual(out.match(/<\/head>/g).length, 1);
      assert.ok(out.endsWith("</html>"));
    });

    it("replaces the page title and description for previews", () => {
      const html = `<!doctype html><html><head>
    <meta
      name="description"
      content="Üldine kirjeldus"
    />
    <title>Riigivaade — üldine</title>
  </head><body></body></html>`;
      const out = injectOpenGraphTags(html, {
        title: "Kaja Kallas — Riigivaade",
        description: "Kaja Kallase profiil",
      });
      assert.ok(out.includes("<title>Kaja Kallas — Riigivaade</title>"));
      assert.ok(out.includes('<meta name="description" content="Kaja Kallase profiil" />'));
      assert.ok(!out.includes("Üldine kirjeldus"));
      assert.ok(!out.includes("Riigivaade — üldine"));
    });
  });

  describe("middleware execution", () => {
    const originalFetch = globalThis.fetch;

    it("handles /istung/:date without calling any API endpoint", async () => {
      const fetchCalls = [];
      globalThis.fetch = async (url) => {
        const urlStr = String(url);
        fetchCalls.push(urlStr);
        if (urlStr.includes("/index.html")) {
          return new Response("<html><head><title>App</title></head><body></body></html>", {
            status: 200,
            headers: { "content-type": "text/html" },
          });
        }
        throw new Error(`Unexpected fetch call: ${urlStr}`);
      };

      try {
        const req = new Request("https://www.riigivaade.me/istung/2026-10-14", {
          headers: { "user-agent": "facebookexternalhit/1.1" },
        });

        const resp = await middleware(req);
        assert.ok(resp);
        assert.strictEqual(resp.status, 200);

        const body = await resp.text();
        assert.ok(
          body.includes('<meta property="og:title" content="Istung 14.10.2026 — Riigivaade" />')
        );
        assert.ok(!body.includes("sessions/2026-10-14"));

        // Verify only index.html was fetched, zero API calls
        assert.strictEqual(fetchCalls.length, 1);
        assert.ok(fetchCalls[0].endsWith("/index.html"));
      } finally {
        globalThis.fetch = originalFetch;
      }
    });

    it("returns 404 with 404.html when API returns 404 for saadik", async () => {
      globalThis.fetch = async (url) => {
        const urlStr = String(url);
        if (urlStr.includes("/index.html")) {
          return new Response("<html><head></head><body></body></html>", { status: 200 });
        }
        if (urlStr.includes("/persons/non-existent-uuid")) {
          return new Response(JSON.stringify({ detail: "Not found" }), { status: 404 });
        }
        if (urlStr.includes("/404.html")) {
          return new Response(
            "<html><head><title>404</title></head><body>Page not found</body></html>",
            {
              status: 200,
            }
          );
        }
        throw new Error(`Unexpected fetch: ${urlStr}`);
      };

      try {
        const req = new Request("https://www.riigivaade.me/saadik/non-existent-uuid", {
          headers: { "user-agent": "Twitterbot/1.0" },
        });

        const resp = await middleware(req);
        assert.ok(resp);
        assert.strictEqual(resp.status, 404);

        const body = await resp.text();
        assert.ok(body.includes("Page not found"));
        // Ensure no OG tags were injected into 404 response
        assert.ok(!body.includes('property="og:title"'));
      } finally {
        globalThis.fetch = originalFetch;
      }
    });

    it("returns 404 when the API rejects a malformed id with 422", async () => {
      globalThis.fetch = async (url) => {
        const urlStr = String(url);
        if (urlStr.includes("/index.html")) {
          return new Response("<html><head></head><body></body></html>", { status: 200 });
        }
        if (urlStr.includes("/speeches/abc")) {
          return new Response(JSON.stringify({ detail: [] }), { status: 422 });
        }
        if (urlStr.includes("/404.html")) {
          return new Response("<html><body>Page not found</body></html>", { status: 200 });
        }
        throw new Error(`Unexpected fetch: ${urlStr}`);
      };

      try {
        const req = new Request("https://www.riigivaade.me/kone/abc", {
          headers: { "user-agent": "Twitterbot/1.0" },
        });
        const resp = await middleware(req);
        assert.strictEqual(resp.status, 404);
        assert.ok((await resp.text()).includes("Page not found"));
      } finally {
        globalThis.fetch = originalFetch;
      }
    });

    it("returns 404 with 404.html for invalid sitting date format", async () => {
      globalThis.fetch = async (url) => {
        const urlStr = String(url);
        if (urlStr.includes("/404.html")) {
          return new Response(
            "<html><head><title>404</title></head><body>Page not found</body></html>",
            {
              status: 200,
            }
          );
        }
        throw new Error(`Unexpected fetch: ${urlStr}`);
      };

      try {
        const req = new Request("https://www.riigivaade.me/istung/invalid-date", {
          headers: { "user-agent": "Slackbot 1.0" },
        });

        const resp = await middleware(req);
        assert.ok(resp);
        assert.strictEqual(resp.status, 404);
        const body = await resp.text();
        assert.ok(body.includes("Page not found"));
      } finally {
        globalThis.fetch = originalFetch;
      }
    });
  });
});
