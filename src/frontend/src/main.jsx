import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/source-code-pro";
import "@fontsource-variable/source-sans-3";
import "@fontsource-variable/source-serif-4";
import "./index.css";
import App from "./App.jsx";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>
);
