import { FIXTURE_IDS } from "./api.js";

// Every app route with a selector that only exists once that view has rendered its data
export const ROUTES = [
  { path: "/", name: "Dashboard", contentSelector: ".dashboard-grid" },
  { path: "/otsing", name: "Otsing", contentSelector: ".search-section" },
  { path: `/istung/${FIXTURE_IDS.date}`, name: "Istung", contentSelector: ".speeches-view-title" },
  { path: "/kohalolek", name: "Kohalolek", contentSelector: ".attendance-filter-bar" },
  { path: `/kone/${FIXTURE_IDS.speechId}`, name: "Kõne", contentSelector: ".speech-card" },
  {
    path: `/saadik/${FIXTURE_IDS.personUuid}`,
    name: "Saadik",
    contentSelector: ".person-view-container",
  },
  { path: "/haaletused", name: "Hääletused", contentSelector: ".votings-view-container" },
  {
    path: `/haaletus/${FIXTURE_IDS.votingUuid}`,
    name: "Hääletus",
    contentSelector: ".voting-detail-container",
  },
  { path: `/eelnou/${FIXTURE_IDS.draftUuid}`, name: "Eelnõu", contentSelector: ".reading-card" },
  { path: "/andmed", name: "Andmed", contentSelector: "h1:has-text('Andmed ja privaatsus')" },
];
