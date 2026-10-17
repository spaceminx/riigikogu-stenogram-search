import React, { useEffect, useState } from "react";
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
import {
  fetchDashboardOverview,
  fetchFactionsList,
  fetchMemberships,
  fetchPlenarySessionDates,
  fetchSystemStatus,
} from "./lib/api";
import { toRoman } from "./lib/formatters";
import Header from "./components/Header";
import Footer from "./components/Footer";
import ErrorBoundary from "./components/ErrorBoundary";
import MethodologyModal from "./components/MethodologyModal";
import DashboardView from "./routes/DashboardView";
import SearchView from "./routes/SearchView";
import SessionView from "./routes/SessionView";
import AttendanceView from "./routes/AttendanceView";
import SpeechView from "./routes/SpeechView";
import PersonView from "./routes/PersonView";
import NotFoundView from "./routes/NotFoundView";
import "./App.css";

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
  } else if (pathname.startsWith("/otsing")) {
    title = "Otsingutulemused";
  } else if (pathname.startsWith("/istung")) {
    title = "Istungi stenogramm";
  } else if (pathname.startsWith("/kone")) {
    title = "Kõne stenogramm";
  } else if (pathname.startsWith("/saadik")) {
    title = "Saadiku profiil";
  }
  const memText =
    memberships && memberships.length > 0
      ? memberships.map((m) => toRoman(m.number || m.id)).join(" ja ") + " koosseis"
      : null;

  return (
    <div className="page-titlebar">
      <h1>{title}</h1>
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
  const [systemStatus, setSystemStatus] = useState(null);
  const [searchFactionsList, setSearchFactionsList] = useState([]);
  const [memberships, setMemberships] = useState([]);
  const [membershipsLoading, setMembershipsLoading] = useState(true);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("theme", theme);
    } catch {
      // Ignore write errors in private mode
    }
  }, [theme]);

  const {
    data: dashboardOverview,
    error: overviewError,
    isLoading: overviewLoading,
  } = useSWR("dashboard-overview", fetchDashboardOverview, {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });

  const { data: plenaryDatesData } = useSWR("plenary-session-dates", fetchPlenarySessionDates, {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });
  const plenaryDates = plenaryDatesData?.dates || [];

  useEffect(() => {
    fetchSystemStatus()
      .then((data) => setSystemStatus(data))
      .catch(() => {});

    fetchMemberships()
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          setMemberships(data.filter((m) => m.number >= 14));
        }
      })
      .catch(() => {})
      .finally(() => {
        setMembershipsLoading(false);
      });

    fetchFactionsList("all")
      .then((data) => {
        if (Array.isArray(data)) setSearchFactionsList(data);
      })
      .catch(() => {});
  }, []);

  return (
    <div className="app-container">
      <LegacyRedirectHandler />

      <Header
        theme={theme}
        setTheme={setTheme}
        systemStatus={systemStatus}
        overviewError={overviewError}
        overviewLoading={overviewLoading}
        onOpenMethodology={() => setShowMethodologyModal(true)}
      />

      <PageTitlebar memberships={memberships} />

      <main>
        <ErrorBoundary key={location.pathname}>
          <Routes>
            <Route
              path="/"
              element={
                <DashboardView
                  dashboardOverview={dashboardOverview}
                  overviewError={overviewError}
                  overviewLoading={overviewLoading}
                  plenaryDates={plenaryDates}
                  theme={theme}
                  memberships={memberships}
                  searchFactionsList={searchFactionsList}
                  systemStatus={systemStatus}
                />
              }
            />
            <Route
              path="/otsing"
              element={
                <SearchView
                  memberships={memberships}
                  searchFactionsList={searchFactionsList}
                  plenaryDates={plenaryDates}
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
            <Route path="/saadik/:uuid" element={<PersonRoute theme={theme} />} />
            <Route path="*" element={<NotFoundView />} />
          </Routes>
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
