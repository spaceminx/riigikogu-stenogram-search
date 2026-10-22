import { describe, it } from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToString } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { createServer } from "vite";

describe("SearchView SSR regression tests", () => {
  it("renders /otsing?q=eelarve without throwing and displays the RSS feed link", async () => {
    const server = await createServer({
      server: { middlewareMode: true },
      appType: "custom",
    });

    try {
      const { SWRConfig } = await server.ssrLoadModule("swr");
      const { default: SearchView } = await server.ssrLoadModule("src/routes/SearchView.jsx");

      const mockSearchData = {
        total_count: 1,
        count: 1,
        offset: 0,
        limit: 50,
        results: [
          {
            id: 99901,
            speaker: "Jaan Tamm",
            speaker_faction: "Eesti 200 fraktsioon",
            date: "2026-10-15",
            time: "1000",
            agenda_title: "Riigieelarve arutelu",
            text: "Riigi eelarve arutelu stenogrammis.",
            matched_words: ["eelarve"],
          },
        ],
      };

      const fallback = {
        "/search?q=eelarve&membership=all&sort_by=date_desc&limit=50&offset=0": mockSearchData,
      };

      // Assert render does not throw (guards against temporal dead zone / reference errors)
      let html = "";
      assert.doesNotThrow(() => {
        html = renderToString(
          React.createElement(
            SWRConfig,
            { value: { provider: () => new Map(), fallback } },
            React.createElement(
              MemoryRouter,
              { initialEntries: ["/otsing?q=eelarve"] },
              React.createElement(SearchView, { isOnline: true })
            )
          )
        );
      });

      assert.ok(html.length > 0, "Rendered output should not be empty");
      assert.ok(html.includes("Telli RSS-voog"), "Rendered output should include 'Telli RSS-voog'");
      assert.ok(
        html.includes("/rss/search?q=eelarve"),
        "Rendered output should include RSS link with query param"
      );
    } finally {
      await server.close();
    }
  });
});
