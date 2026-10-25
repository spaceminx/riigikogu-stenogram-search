import React from "react";
import { Link, useLocation } from "react-router-dom";
import {
  Activity,
  CalendarDays,
  Database,
  ExternalLink,
  FileText,
  Info,
  Landmark,
  Menu,
  Moon,
  RefreshCw,
  Sun,
  Users,
  Vote,
} from "lucide-react";
import { formatDate } from "../lib/calendarUtils";
import { formatSyncTime, isSyncStale } from "../lib/formatters";

export function Header({
  theme,
  setTheme,
  systemStatus,
  systemStatusError,
  systemStatusLoading,
  overviewError,
  overviewLoading,
  onOpenMethodology,
}) {
  const isOffline = Boolean(systemStatusError ?? overviewError);
  const isLoading = Boolean(systemStatusLoading ?? overviewLoading);
  const location = useLocation();
  const pathname = location.pathname;

  const isVotings = pathname.startsWith("/haaletused") || pathname.startsWith("/haaletus");
  const isAttendance = pathname.startsWith("/kohalolek");
  const isSearchOrDashboard = pathname === "/" || pathname.startsWith("/otsing");

  return (
    <header className="header">
      <Link to="/" className="brand-lockup" aria-label="Riigivaade">
        <span className="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 40 40">
            <rect className="brand-tile" width="40" height="40" rx="6" />
            <path
              className="brand-comma"
              d="M14 21a5 5 0 1 1 0 10c0 3.4-2 6-5 7.4l-.9-1.8c1.7-1 2.8-2.6 3.1-4.5A5 5 0 0 1 14 21z"
            />
            <path
              className="brand-comma-editor"
              d="M27 21a5 5 0 1 1 0 10c0 3.4-2 6-5 7.4l-.9-1.8c1.7-1 2.8-2.6 3.1-4.5A5 5 0 0 1 27 21z"
            />
          </svg>
        </span>
        <span className="brand-copy">
          <strong>Riigivaade</strong>
          <span>Kõned ja andmed</span>
        </span>
      </Link>
      <nav className="nav-links" aria-label="Põhinavigatsioon">
        <Link
          to="/"
          className={`nav-btn ${isSearchOrDashboard ? "active" : ""}`}
          aria-current={isSearchOrDashboard ? "page" : undefined}
        >
          Kõneotsing
        </Link>
        <Link
          to="/kohalolek"
          className={`nav-btn ${isAttendance ? "active" : ""}`}
          aria-current={isAttendance ? "page" : undefined}
        >
          Kohalolek
        </Link>
        <Link
          to="/haaletused"
          className={`nav-btn ${isVotings ? "active" : ""}`}
          aria-current={isVotings ? "page" : undefined}
        >
          Hääletused
        </Link>
      </nav>
      <details className="header-menu">
        <summary className="header-menu-trigger" aria-label="Ava andmevaate menüü">
          <Menu aria-hidden="true" />
          <span>Menüü</span>
        </summary>
        <div className="header-menu-panel">
          <div className="mobile-menu-nav">
            <div className="menu-section-label">Navigatsioon</div>
            <Link
              to="/"
              className={`menu-link ${isSearchOrDashboard ? "active" : ""}`}
              onClick={() => {
                const details = document.querySelector(".header-menu");
                if (details) details.removeAttribute("open");
              }}
            >
              <FileText aria-hidden="true" />
              <span>Kõneotsing</span>
            </Link>
            <Link
              to="/kohalolek"
              className={`menu-link ${isAttendance ? "active" : ""}`}
              onClick={() => {
                const details = document.querySelector(".header-menu");
                if (details) details.removeAttribute("open");
              }}
            >
              <Users aria-hidden="true" />
              <span>Kohalolek</span>
            </Link>
            <Link
              to="/haaletused"
              className={`menu-link ${isVotings ? "active" : ""}`}
              onClick={() => {
                const details = document.querySelector(".header-menu");
                if (details) details.removeAttribute("open");
              }}
            >
              <Vote aria-hidden="true" />
              <span>Hääletused</span>
            </Link>
            <div className="menu-divider" />
          </div>
          <div className="menu-section-label">Välimus</div>
          <button
            type="button"
            className="menu-action"
            aria-pressed={theme === "dark"}
            onClick={() => setTheme((current) => (current === "dark" ? "light" : "dark"))}
          >
            {theme === "dark" ? <Sun aria-hidden="true" /> : <Moon aria-hidden="true" />}
            <span>{theme === "dark" ? "Hele kujundus" : "Tume kujundus"}</span>
          </button>
          <div className="menu-divider" />
          <div className="menu-section-label">Andmed ja teenused</div>
          <div className="menu-status-row">
            <Database aria-hidden="true" />
            <span>Arhiiv</span>
            <span className={`menu-status ${isOffline ? "is-offline" : ""}`}>
              <i />
              {isOffline ? "Pole ühendust" : isLoading ? "Ühendun…" : "Valmis"}
            </span>
          </div>
          {systemStatus?.data_as_of && (
            <div
              className="menu-status-row"
              title={
                systemStatus.latest_session_status === "UNEDITED"
                  ? `Viimane istung: ${formatDate(systemStatus.data_as_of)} (esialgne stenogramm)`
                  : `Viimane istung: ${formatDate(systemStatus.data_as_of)}`
              }
            >
              <CalendarDays aria-hidden="true" />
              <span>Viimane istung</span>
              <span className="menu-status" style={{ fontSize: "0.75rem", textTransform: "none" }}>
                {formatDate(systemStatus.data_as_of)}
                {systemStatus.latest_session_status === "UNEDITED" ? " (esialgne)" : ""}
              </span>
            </div>
          )}
          {systemStatus?.last_sync_at && (
            <div
              className="menu-status-row"
              title={
                isSyncStale(systemStatus.last_sync_at)
                  ? "Automaatne sünkroonimine võib olla peatunud."
                  : undefined
              }
            >
              <RefreshCw aria-hidden="true" />
              <span>Uuendatud</span>
              <span
                className={`menu-status ${isSyncStale(systemStatus.last_sync_at) ? "is-offline" : ""}`}
                style={{ fontSize: "0.75rem", textTransform: "none" }}
              >
                {formatSyncTime(systemStatus.last_sync_at)}
              </span>
            </div>
          )}
          {systemStatus?.last_sync_at && isSyncStale(systemStatus.last_sync_at) && (
            <div
              className="menu-warning-notice"
              style={{
                fontSize: "0.72rem",
                color: "#eab308",
                padding: "0.25rem 0.75rem",
                lineHeight: 1.3,
              }}
            >
              Automaatne sünkroonimine võib olla peatunud.
            </div>
          )}
          <div className="menu-status-row">
            <Activity aria-hidden="true" />
            <span>API olek</span>
            <span className={`menu-status ${isOffline ? "is-offline" : ""}`}>
              <i />
              {isOffline ? "Pole saadaval" : isLoading ? "Kontrollin…" : "Aktiivne"}
            </span>
          </div>
          <button
            type="button"
            className="menu-action"
            onClick={() => {
              onOpenMethodology();
              const details = document.querySelector(".header-menu");
              if (details) details.removeAttribute("open");
            }}
          >
            <Info aria-hidden="true" />
            <span>Metoodika ja andmed</span>
          </button>
          <div className="menu-divider" />
          <a
            className="menu-link"
            href="https://www.riigikogu.ee/"
            target="_blank"
            rel="noreferrer"
          >
            <Landmark aria-hidden="true" />
            <span>Riigikogu ametlik arhiiv</span>
            <ExternalLink aria-hidden="true" />
          </a>
          <a
            className="menu-link"
            href="https://github.com/spaceminx/riigikogu-stenogram-search"
            target="_blank"
            rel="noreferrer"
          >
            <span className="github-mark" aria-hidden="true">
              GH
            </span>
            <span>Lähtekood GitHubis</span>
            <ExternalLink aria-hidden="true" />
          </a>
        </div>
      </details>
    </header>
  );
}

export default Header;
