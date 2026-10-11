import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { CalendarDays, ExternalLink } from "lucide-react";
import DateRangeCalendar from "../DateRangeCalendar";
import ActivityChart from "../components/ActivityChart";
import SpeakersPanel from "../components/SpeakersPanel";
import { formatDateTime, normalizeSourceUrl } from "../lib/formatters";

export function DashboardView({
  dashboardOverview,
  overviewError,
  plenaryDates = [],
  theme = "light",
}) {
  const navigate = useNavigate();
  const [inputValue, setInputValue] = useState("");
  const [interval, setInterval] = useState("monthly");

  const recentSessions = dashboardOverview?.sessions || [];
  const overviewSpeakers = dashboardOverview?.speakers || [];

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    if (inputValue.trim()) {
      navigate(`/otsing?q=${encodeURIComponent(inputValue.trim())}`);
    } else {
      navigate("/otsing");
    }
  };

  const handleTopicClick = (topic) => {
    navigate(`/otsing?q=${encodeURIComponent(topic)}`);
  };

  const handlePlenaryDateSelect = (date) => {
    navigate(`/istung/${date}`);
  };

  return (
    <>
      <div className="archive-stats-row" aria-label="Riigikogu arhiivi kokkuvõte">
        <span className="archive-stat">120 000+ kõnet</span>
        <span className="archive-stat-separator" aria-hidden="true">
          •
        </span>
        <span className="archive-stat">101 saadikut</span>
        <span className="archive-stat-separator" aria-hidden="true">
          •
        </span>
        <span className="archive-stat">XIV ja XV koosseis</span>
      </div>

      <form onSubmit={handleSearchSubmit} className="search-section">
        <div className="search-query-row">
          <div className="search-groups-container">
            <div className="and-group-box">
              <input
                type="text"
                className="search-input"
                placeholder="Sisesta otsisõna (nt kliima, mets, eelarve)..."
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
              />
            </div>
          </div>
        </div>
        <div className="search-controls">
          <button type="submit" className="search-button">
            Otsi
          </button>
        </div>
      </form>

      <section className="topic-suggestions" aria-label="Populaarsed otsinguteemad">
        <span className="topic-suggestions-label">Populaarsed teemad</span>
        {["Kaitsekulud", "Riigieelarve", "Maksupoliitika", "Õpetajate palgad", "Energeetika"].map(
          (topic) => (
            <button
              className="topic-pill"
              key={topic}
              type="button"
              onClick={() => handleTopicClick(topic)}
            >
              {topic}
            </button>
          )
        )}
      </section>

      <div className="dashboard-grid">
        <ActivityChart
          activity={[]}
          interval={interval}
          onIntervalChange={setInterval}
          loading={false}
          theme={theme}
        />

        <aside className="dashboard-rail">
          <SpeakersPanel
            speakers={overviewSpeakers}
            showingArchiveSpeakers={true}
            overviewError={overviewError}
          />

          <section className="glass-panel sessions-card" aria-labelledby="sessions-title">
            <div className="chart-header">
              <div>
                <span className="section-kicker">ARHIIVI VÄRSKEIMAD</span>
                <h2 id="sessions-title">Viimased istungid</h2>
              </div>
              <CalendarDays className="sessions-heading-icon" aria-hidden="true" />
            </div>
            {recentSessions.length > 0 ? (
              <div className="sessions-list">
                {recentSessions.slice(0, 3).map((session, idx) => (
                  <article className="session-item" key={`${session.date}-${idx}`}>
                    <span className="session-marker" aria-hidden="true" />
                    <div className="session-content">
                      <Link
                        to={`/istung/${session.date}`}
                        style={{ color: "inherit", textDecoration: "none" }}
                      >
                        <strong>{formatDateTime(session.date)}</strong>
                      </Link>
                      <div className="session-topics">
                        {(session.topics || []).slice(0, 3).map((topic) => (
                          <span className="session-topic" key={topic}>
                            {topic}
                          </span>
                        ))}
                        {session.source_url && (
                          <a
                            className="session-source-link"
                            href={normalizeSourceUrl(session.source_url)}
                            target="_blank"
                            rel="noreferrer"
                            aria-label="Ava istungi allikas"
                          >
                            <ExternalLink aria-hidden="true" />
                          </a>
                        )}
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <p className="sidebar-empty-state">
                {overviewError
                  ? "Istungite andmed pole praegu kättesaadavad."
                  : "Värskeimad istungid laaditakse arhiivist."}
              </p>
            )}
            <DateRangeCalendar
              compact
              dates={plenaryDates}
              value={{ startDate: "", endDate: "" }}
              onChange={() => {}}
              onSelectDate={handlePlenaryDateSelect}
            />
          </section>
        </aside>
      </div>
    </>
  );
}

export default DashboardView;
