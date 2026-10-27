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
import { toRoman } from "./lib/formatters";
import { visibleMemberships } from "./lib/calendarUtils";
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
const SpeechView = lazy(() => import("./routes/SpeechView"));
const PersonView = lazy(() => import("./routes/PersonView"));
const PrivacyView = lazy(() => import("./routes/PrivacyView"));
const VotingsView = lazy(() => import("./routes/VotingsView"));
const VotingView = lazy(() => import("./routes/VotingView"));
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

function PageTitlebar({ memberships = [] }) {
  const location = useLocation();
  const pathname = location.pathname;

  let title = "Kõnede analüüs";
  if (pathname.startsWith("/kohalolek")) {
    title = "Kohaloleku andmed";
  } else if (pathname.startsWith("/fraktsioonid")) {
    title = "Fraktsioonid";
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
  } else if (pathname.startsWith("/eelnou")) {
    title = "Eelnõu";
  }
  const memText =
    memberships && memberships.length > 0
      ? memberships.map((m) => toRoman(m.number || m.id)).join(" ja ") + " koosseis"
      : null;

  // Detail views render their own <h1> (person, speech, vote, bill, privacy page), so the
  // section label here must not be a second one.
  const viewHasOwnHeading =
    /^\/(kone|saadik|haaletus|eelnou)\//.test(pathname) || pathname.startsWith("/andmed");
  const TitleTag = viewHasOwnHeading ? "p" : "h1";

  return (
    <div className="page-titlebar">
      <TitleTag className="page-title">{title}</TitleTag>
      <span>Riigikogu stenogrammid{memText ? ` · ${memText}` : ""}</span>
    </div>
  );
}

function PersonRoute({ theme }) {
  const { uuid } = useParams();
  return <PersonView key={uuid} theme={theme} />;
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
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("theme", theme);
    } catch {
      // Ignore write errors in private mode
    }
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
                element={<SearchView memberships={memberships} theme={theme} />}
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
              <Route path="/saadik/:uuid" element={<PersonRoute theme={theme} />} />
              <Route path="/haaletused" element={<VotingsView memberships={memberships} />} />
              <Route
                path="/fraktsioonid"
                element={
                  <FactionsView memberships={memberships} membershipsLoading={membershipsLoading} />
                }
              />
              <Route path="/haaletus/:uuid" element={<VotingView />} />
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
