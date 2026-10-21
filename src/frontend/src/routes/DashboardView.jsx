import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { CalendarDays, ExternalLink } from "lucide-react";
import DateRangeCalendar from "../DateRangeCalendar";
import ActivityChart from "../components/ActivityChart";
import SpeakersPanel from "../components/SpeakersPanel";
import SearchQueryInput from "../components/SearchQueryInput";
import SearchFilters from "../components/SearchFilters";
import { usePageMeta } from "../lib/usePageMeta";
import {
  formatDateTime,
  mergeInputToGroups,
  normalizeSourceUrl,
  serializeGroupsToQuery,
  toRoman,
} from "../lib/formatters";

export function DashboardView({
  dashboardOverview,
  overviewError,
  overviewLoading = false,
  plenaryDates = [],
  theme = "light",
  memberships = [],
  searchFactionsList = [],
  systemStatus = null,
}) {
  usePageMeta(
    "Riigivaade — Riigikogu kõned, hääletused ja kohalolek",
    "Riigikogu stenogrammid, kõned, hääletused ja kohalolekukontrollid ühes otsitavas vaates."
  );

  const navigate = useNavigate();
  const totalSpeeches = systemStatus?.total_speeches ?? systemStatus?.totals?.speeches;
  const totalPersons = systemStatus?.total_persons ?? systemStatus?.totals?.persons;
  const memText =
    memberships && memberships.length > 0
      ? memberships.map((m) => toRoman(m.number || m.id)).join(" ja ") + " koosseis"
      : null;

  const statItems = [];
  if (totalSpeeches !== undefined && totalSpeeches !== null) {
    statItems.push(`${Number(totalSpeeches).toLocaleString("et-EE")} kõnet`);
  }
  if (totalPersons !== undefined && totalPersons !== null) {
    statItems.push(`${totalPersons} saadikut`);
  }
  if (memText) {
    statItems.push(memText);
  }
  const [groups, setGroups] = useState([[]]);
  const [inputValue, setInputValue] = useState("");
  const [searchMembership, setSearchMembership] = useState("all");
  const [searchFaction, setSearchFaction] = useState("");
  const [searchDateRange, setSearchDateRange] = useState({ startDate: "", endDate: "" });
  const [searchSpeaker, setSearchSpeaker] = useState("");
  const [searchSpeechCategory, setSearchSpeechCategory] = useState("");
  const [searchExcludeChair, setSearchExcludeChair] = useState(false);

  const recentSessions = dashboardOverview?.sessions || [];
  const overviewSpeakers = dashboardOverview?.speakers || [];

  const handleSearchSubmit = (e) => {
    if (e) e.preventDefault();
    let finalGroups = [...groups];
    if (inputValue.trim()) {
      finalGroups = mergeInputToGroups(finalGroups, inputValue.trim());
      setGroups(finalGroups);
      setInputValue("");
    }
    finalGroups = finalGroups.filter((g) => g.length > 0);
    const queryString = serializeGroupsToQuery(finalGroups);

    const params = new URLSearchParams();
    if (queryString) params.set("q", queryString);
    if (searchMembership && searchMembership !== "all") params.set("membership", searchMembership);
    if (searchFaction) params.set("faction", searchFaction);
    if (searchSpeaker.trim()) params.set("speaker", searchSpeaker.trim());
    if (searchDateRange.startDate) params.set("start_date", searchDateRange.startDate);
    if (searchDateRange.endDate) params.set("end_date", searchDateRange.endDate);
    if (searchExcludeChair) params.set("exclude_chair", "true");
    if (searchSpeechCategory) params.set("speech_category", searchSpeechCategory);

    const qs = params.toString();
    navigate(`/otsing${qs ? `?${qs}` : ""}`);
  };

  const handleResetFilters = () => {
    setSearchMembership("all");
    setSearchFaction("");
    setSearchDateRange({ startDate: "", endDate: "" });
    setSearchSpeaker("");
    setSearchSpeechCategory("");
    setSearchExcludeChair(false);
  };

  const handleTopicClick = (topic) => {
    navigate(`/otsing?q=${encodeURIComponent(topic)}`);
  };

  const handlePlenaryDateSelect = (date) => {
    navigate(`/istung/${date}`);
  };

  return (
    <>
      {statItems.length > 0 && (
        <div className="archive-stats-row" aria-label="Riigikogu arhiivi kokkuvõte">
          {statItems.map((item, idx) => (
            <React.Fragment key={idx}>
              {idx > 0 && (
                <span className="archive-stat-separator" aria-hidden="true">
                  •
                </span>
              )}
              <span className="archive-stat">{item}</span>
            </React.Fragment>
          ))}
        </div>
      )}

      <SearchQueryInput
        groups={groups}
        setGroups={setGroups}
        inputValue={inputValue}
        setInputValue={setInputValue}
        onSearch={handleSearchSubmit}
        loading={false}
      >
        <SearchFilters
          searchMembership={searchMembership}
          setSearchMembership={setSearchMembership}
          memberships={memberships}
          searchFaction={searchFaction}
          setSearchFaction={setSearchFaction}
          searchFactionsList={searchFactionsList}
          plenaryDates={plenaryDates}
          searchDateRange={searchDateRange}
          setSearchDateRange={setSearchDateRange}
          searchSpeaker={searchSpeaker}
          setSearchSpeaker={setSearchSpeaker}
          searchSpeechCategory={searchSpeechCategory}
          setSearchSpeechCategory={setSearchSpeechCategory}
          searchExcludeChair={searchExcludeChair}
          setSearchExcludeChair={setSearchExcludeChair}
          onResetFilters={handleResetFilters}
        />
      </SearchQueryInput>

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
        <div className="dashboard-main">
          <ActivityChart
            activity={dashboardOverview?.activity || []}
            loading={overviewLoading}
            error={overviewError}
            theme={theme}
            kicker="VIIMASED 24 KUUD"
            title="Sõnavõtud kuude kaupa"
            emptyMessage="Andmed puuduvad."
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
          </section>
        </div>

        <aside className="dashboard-rail">
          <SpeakersPanel
            speakers={overviewSpeakers}
            showingArchiveSpeakers={true}
            overviewError={overviewError}
          />

          <section className="glass-panel sessions-card" aria-labelledby="calendar-title">
            <div className="chart-header">
              <div>
                <span className="section-kicker">ISTUNGITE ARHIIV</span>
                <h2 id="calendar-title">Vali istung</h2>
              </div>
              <CalendarDays className="sessions-heading-icon" aria-hidden="true" />
            </div>
            <DateRangeCalendar
              compact
              dates={plenaryDates}
              memberships={memberships}
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
