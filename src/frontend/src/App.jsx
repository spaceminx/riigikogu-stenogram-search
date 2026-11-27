import React, { Suspense, lazy, useEffect, useMemo, useState } from "react";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import useSWR from "swr";
import { fetchMemberships, fetchSystemStatus } from "./lib/api";
import { archiveStartYear, visibleMemberships } from "./lib/calendarUtils";
import Header from "./components/Header";
import Footer from "./components/Footer";
import ErrorBoundary from "./components/ErrorBoundary";
import MethodologyModal from "./components/MethodologyModal";
import "./styles/index.css";

const DashboardView = lazy(() => import("./routes/DashboardView"));
const SearchView = lazy(() => import("./routes/SearchView"));
const SessionView = lazy(() => import("./routes/SessionView"));
const AttendanceView = lazy(() => import("./routes/AttendanceView"));
const FactionsView = lazy(() => import("./routes/FactionsView"));
const MembersView = lazy(() => import("./routes/MembersView"));
const SpeechView = lazy(() => import("./routes/SpeechView"));
const PersonView = lazy(() => import("./routes/PersonView"));
const PrivacyView = lazy(() => import("./routes/PrivacyView"));
const VotingsView = lazy(() => import("./routes/VotingsView"));
const VotingView = lazy(() => import("./routes/VotingView"));
const DraftsView = lazy(() => import("./routes/DraftsView"));
const DraftView = lazy(() => import("./routes/DraftView"));
const NotFoundView = lazy(() => import("./routes/NotFoundView"));

function LegacyRedirectHandler() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    if (location.pathname !== "/") return;
    const view = searchParams.get("view");
    if (!view) return;

    const nextParams = new URLSearchParams(searchParams);
    nextParams.delete("view");
    const q = searchParams.get("q");
    const startDate = searchParams.get("start_date");
    const endDate = searchParams.get("end_date");

    if (view === "speeches") {
      if (startDate && startDate === endDate && !q) {
        navigate(`/istung/${startDate}`, { replace: true });
      } else {
        // Old links searched every membership; the search now opens on the current one
        if (!nextParams.has("membership")) nextParams.set("membership", "all");
        const qs = nextParams.toString();
        navigate(`/otsing${qs ? `?${qs}` : ""}`, { replace: true });
      }
    } else if (view === "attendance") {
      const qs = nextParams.toString();
      navigate(`/kohalolek${qs ? `?${qs}` : ""}`, { replace: true });
    } else if (view === "dashboard") {
      const qs = nextParams.toString();
      navigate(`/${qs ? `?${qs}` : ""}`, { replace: true });
    }
  }, [location.pathname, searchParams, navigate]);

  return null;
}

// Paths with a route of their own; anything else is the 404 page
const KNOWN_PATH =
  /^\/(otsing|kohalolek|haaletused|fraktsioonid|saadikud|eelnoud|andmed|(istung|kone|saadik|haaletus|eelnou)\/[^/]+)?\/?$/i;

function PageTitlebar({ memberships = [] }) {
  const location = useLocation();
  const pathname = location.pathname;

  let title = "Kõnede analüüs";
  if (pathname.startsWith("/kohalolek")) {
    title = "Kohaloleku andmed";
  } else if (pathname.startsWith("/fraktsioonid")) {
    title = "Fraktsioonid";
  } else if (pathname.startsWith("/saadikud")) {
    title = "Saadikud";
  } else if (pathname.startsWith("/andmed")) {
    title = "Andmed ja privaatsus";
  } else if (pathname.startsWith("/otsing")) {
    title = "Otsingutulemused";
  } else if (pathname.startsWith("/istung")) {
    title = "Istungi stenogramm";
  } else if (pathname.startsWith("/kone")) {
    title = "Kõne stenogramm";
  } else if (pathname.startsWith("/saadik")) {
    title = "Saadiku profiil";
  } else if (pathname.startsWith("/haaletused")) {
    title = "Hääletused";
  } else if (pathname.startsWith("/haaletus")) {
    title = "Hääletus";
  } else if (pathname.startsWith("/eelnoud")) {
    title = "Eelnõud";
  } else if (pathname.startsWith("/eelnou")) {
    title = "Eelnõu";
  }
  const memText =
    memberships && memberships.length > 0 ? `alates ${archiveStartYear(memberships)}` : null;

  // The 404 page names itself; this label would otherwise call it "Kõnede analüüs"
  const isKnownPath = KNOWN_PATH.test(pathname);
  if (!isKnownPath) title = "Lehekülge ei leitud";

  // Detail views render their own <h1> (person, speech, vote, bill, privacy page), so the
  // section label here must not be a second one. Neither must it on the 404 page.
  const viewHasOwnHeading =
    !isKnownPath ||
    /^\/(kone|saadik|haaletus|eelnou)\//.test(pathname) ||
    pathname.startsWith("/andmed");
  const TitleTag = viewHasOwnHeading ? "p" : "h1";

  return (
    // The skip link's target: the page heading, then the content
    <div className="page-titlebar" id="sisu" tabIndex={-1}>
      <TitleTag className="page-title">{title}</TitleTag>
      <span>Riigikogu stenogrammid{memText ? ` · ${memText}` : ""}</span>
    </div>
  );
}

function PersonRoute({ theme, onOpenMethodology }) {
  const { uuid } = useParams();
  return <PersonView key={uuid} theme={theme} onOpenMethodology={onOpenMethodology} />;
}

function getInitialTheme() {
  try {
    const saved = localStorage.getItem("theme");
    if (saved === "light" || saved === "dark") {
      return saved;
    }
  } catch {
    // localStorage may be unavailable or throw in private browsing mode
  }
  return "light";
}

function AppContent() {
  const location = useLocation();
  const [theme, setTheme] = useState(getInitialTheme);
  const [showMethodologyModal, setShowMethodologyModal] = useState(false);

  useEffect(() => {
    const root = document.documentElement;
    // Switch every color at once: hover transitions would otherwise make small controls lag
    root.classList.add("theme-switching");
    root.dataset.theme = theme;
    // Force a layout so the new colors apply while transitions are off
    void document.body.offsetHeight;
    const timer = setTimeout(() => root.classList.remove("theme-switching"), 0);
    try {
      localStorage.setItem("theme", theme);
    } catch {
      // Ignore write errors in private mode
    }
    return () => {
      clearTimeout(timer);
      root.classList.remove("theme-switching");
    };
  }, [theme]);

  const {
    data: systemStatus,
    error: systemStatusError,
    isLoading: systemStatusLoading,
  } = useSWR("system-status", fetchSystemStatus, {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });

  const { data: membershipsData, isLoading: membershipsLoading } = useSWR(
    "parliament-memberships",
    fetchMemberships,
    {
      revalidateOnFocus: false,
      shouldRetryOnError: false,
    }
  );

  const memberships = useMemo(() => visibleMemberships(membershipsData), [membershipsData]);

  return (
    <div className="app-container">
      <LegacyRedirectHandler />

      {/* Focus moves without a "#sisu" in the address, which the router would take as navigation */}
      <a
        href="#sisu"
        className="skip-link"
        onClick={(e) => {
          e.preventDefault();
          document.getElementById("sisu")?.focus();
        }}
      >
        Liigu sisu juurde
      </a>

      <Header
        theme={theme}
        setTheme={setTheme}
        systemStatus={systemStatus}
        systemStatusError={systemStatusError}
        systemStatusLoading={systemStatusLoading}
        onOpenMethodology={() => setShowMethodologyModal(true)}
      />

      <PageTitlebar memberships={memberships} />

      <main>
        <ErrorBoundary key={location.pathname}>
          <Suspense fallback={<div className="empty-state">Laen…</div>}>
            <Routes>
              <Route
                path="/"
                element={
                  <DashboardView
                    theme={theme}
                    memberships={memberships}
                    systemStatus={systemStatus}
                  />
                }
              />
              <Route
                path="/otsing"
                element={
                  <SearchView
                    memberships={memberships}
                    membershipsLoading={membershipsLoading}
                    theme={theme}
                  />
                }
              />
              <Route path="/istung/:date" element={<SessionView />} />
              <Route
                path="/kohalolek"
                element={
                  <AttendanceView
                    memberships={memberships}
                    membershipsLoading={membershipsLoading}
                    onOpenMethodology={() => setShowMethodologyModal(true)}
                  />
                }
              />
              <Route path="/kone/:id" element={<SpeechView />} />
              <Route
                path="/saadik/:uuid"
                element={
                  <PersonRoute
                    theme={theme}
                    onOpenMethodology={() => setShowMethodologyModal(true)}
                  />
                }
              />
              <Route
                path="/saadikud"
                element={
                  <MembersView memberships={memberships} membershipsLoading={membershipsLoading} />
                }
              />
              <Route path="/haaletused" element={<VotingsView memberships={memberships} />} />
              <Route
                path="/fraktsioonid"
                element={
                  <FactionsView memberships={memberships} membershipsLoading={membershipsLoading} />
                }
              />
              <Route path="/haaletus/:uuid" element={<VotingView />} />
              <Route
                path="/eelnoud"
                element={
                  <DraftsView memberships={memberships} membershipsLoading={membershipsLoading} />
                }
              />
              <Route path="/eelnou/:uuid" element={<DraftView />} />
              <Route
                path="/andmed"
                element={<PrivacyView onOpenMethodology={() => setShowMethodologyModal(true)} />}
              />
              <Route path="*" element={<NotFoundView />} />
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </main>

      <Footer onOpenMethodology={() => setShowMethodologyModal(true)} />

      <MethodologyModal
        isOpen={showMethodologyModal}
        onClose={() => setShowMethodologyModal(false)}
        systemStatus={systemStatus}
      />
    </div>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  );
}

export default App;
