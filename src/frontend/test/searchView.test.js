import { describe, it } from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToString } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { createServer } from "vite";

// Effects do not run in renderToString, so no search is made and no results are shown: this
// only guards the first render (e.g. a temporal dead zone or reference error). The result list
// and the filters are tested in e2e/filters.spec.js.
describe("SearchView first render", () => {
  it("renders /otsing?q=eelarve without throwing and offers no RSS feed", async () => {
    const server = await createServer({
      server: { middlewareMode: true },
      appType: "custom",
    });

    try {
      const { SWRConfig } = await server.ssrLoadModule("swr");
      const { default: SearchView } = await server.ssrLoadModule("src/routes/SearchView.jsx");

      let html = "";
      assert.doesNotThrow(() => {
        html = renderToString(
          React.createElement(
            SWRConfig,
            { value: { provider: () => new Map() } },
            React.createElement(
              MemoryRouter,
              { initialEntries: ["/otsing?q=eelarve"] },
              React.createElement(SearchView, {})
            )
          )
        );
      });

      assert.ok(html.includes("Leitud stenogrammid"), "the result header renders");
      assert.ok(!html.includes("/rss/"), "no RSS feed link");
    } finally {
      await server.close();
    }
  });
});
