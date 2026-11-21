import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { notFoundPagePlugin } from "./notFoundPage.js";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), notFoundPagePlugin()],
  build: {
    // Small font files would be inlined as data: URLs, which the CSP (font-src 'self') blocks
    assetsInlineLimit: (filePath) => (filePath.endsWith(".woff2") ? false : undefined),
  },
});
