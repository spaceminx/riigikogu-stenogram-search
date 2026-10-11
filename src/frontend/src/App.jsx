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

function PageTitlebar() {
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
  }

  return (
    <div className="page-titlebar">
      <h1>{title}</h1>
      <span>Riigikogu stenogrammid · XV ja XIV koosseis</span>
    </div>
  );
}

function AppContent() {
  const [theme, setTheme] = useState("light");
  const [showMethodologyModal, setShowMethodologyModal] = useState(false);
  const [systemStatus, setSystemStatus] = useState(null);
  const [searchFactionsList, setSearchFactionsList] = useState([]);
  const [memberships, setMemberships] = useState([
    { id: "15", number: 15, name: "XV Riigikogu (2023–praegu)" },
    { id: "14", number: 14, name: "XIV Riigikogu (2019–2023)" },
  ]);

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
        if (data && data.memberships && data.memberships.length > 0) {
          setMemberships(data.memberships);
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

      <PageTitlebar />

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
