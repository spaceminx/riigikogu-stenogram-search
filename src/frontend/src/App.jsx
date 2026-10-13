import React, { useEffect, useState } from "react";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
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
import Header from "./components/Header";
import Footer from "./components/Footer";
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

  const toRoman = (num) => {
    const romanMap = { 15: "XV", 14: "XIV", 13: "XIII", 12: "XII", 11: "XI" };
    return romanMap[num] || String(num);
  };

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

function AppContent() {
  const [theme, setTheme] = useState(() => {
    try {
      const fromUrl = new URLSearchParams(window.location.search).get("theme");
      if (fromUrl === "dark" || fromUrl === "light") return fromUrl;
      return localStorage.getItem("theme") || "light";
    } catch {
      return "light";
    }
  });
  const [showMethodologyModal, setShowMethodologyModal] = useState(false);
  const [systemStatus, setSystemStatus] = useState(null);
  const [searchFactionsList, setSearchFactionsList] = useState([]);
  const [memberships, setMemberships] = useState([]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
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
      .catch(() => {});

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
          <Route path="/kohalolek" element={<AttendanceView memberships={memberships} />} />
          <Route path="/kone/:id" element={<SpeechView />} />
          <Route path="/saadik/:uuid" element={<PersonView theme={theme} />} />
          <Route path="*" element={<NotFoundView />} />
        </Routes>
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
