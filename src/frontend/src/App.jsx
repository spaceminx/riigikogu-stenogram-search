import React, { useState } from "react";
import { XAxis, YAxis, Tooltip, ResponsiveContainer, AreaChart, Area } from "recharts";
import { fetchSearch, fetchActivity, fetchSpeakers } from "./api";
import "./App.css";

function formatDateTime(dateStr, timeStr) {
  if (!dateStr) return "";
  const months = ["jaanuar", "veebruar", "märts", "aprill", "mai", "juuni", "juuli", "august", "september", "oktoober", "november", "detsember"];
  let formattedDate = dateStr;
  try {
    const parts = dateStr.split("-");
    if (parts.length === 3) {
      const year = parts[0];
      const month = parseInt(parts[1], 10) - 1;
      const day = parseInt(parts[2], 10);
      formattedDate = `${day}. ${months[month]} ${year}`;
    }
  } catch (e) {}

  let formattedTime = "";
  if (timeStr) {
    if (timeStr.length === 4 && !timeStr.includes(":")) {
      formattedTime = ` kell ${timeStr.slice(0,2)}:${timeStr.slice(2,4)}`;
    } else {
      const tParts = timeStr.split(":");
      if (tParts.length >= 2) {
         formattedTime = ` kell ${tParts[0]}:${tParts[1]}`;
      } else {
         formattedTime = ` kell ${timeStr}`;
      }
    }
  }
  return `${formattedDate}${formattedTime}`;
}

function App() {
  const [groups, setGroups] = useState([[]]); // Array of arrays of strings
  const [inputValue, setInputValue] = useState("");
  const [interval, setSelectedInterval] = useState("monthly");
  const [speeches, setSpeeches] = useState([]);
  const [activity, setActivity] = useState([]);
  const [speakers, setSpeakers] = useState([]);
  const [view, setView] = useState("dashboard");
  
  const tooltipStyle = {
    contentStyle: {
      backgroundColor: "rgba(15, 23, 42, 0.9)",
      backdropFilter: "blur(8px)",
      color: "#f8fafc",
      border: "1px solid rgba(255, 255, 255, 0.1)",
      borderRadius: "12px",
      boxShadow: "0 10px 15px -3px rgba(0, 0, 0, 0.5)"
    },
    itemStyle: { color: "#8b5cf6", fontWeight: 600 },
    labelStyle: { color: "#cbd5e1", marginBottom: '4px' }
  };

  const handleAddAnd = () => {
    if (inputValue.trim()) {
      const newGroups = [...groups];
      newGroups[newGroups.length - 1] = [...newGroups[newGroups.length - 1], inputValue.trim()];
      setGroups(newGroups);
      setInputValue("");
    }
  };

  const handleAddOr = () => {
    const newGroups = [...groups];
    if (inputValue.trim()) {
      newGroups[newGroups.length - 1] = [...newGroups[newGroups.length - 1], inputValue.trim()];
    }
    // Only add a new group if the last one isn't already empty
    if (newGroups[newGroups.length - 1].length > 0) {
      newGroups.push([]);
    }
    setGroups(newGroups);
    setInputValue("");
  };

  const removeWord = (gIndex, wIndex) => {
    const newGroups = [...groups];
    newGroups[gIndex] = [...newGroups[gIndex]];
    newGroups[gIndex].splice(wIndex, 1);
    
    // If a group becomes completely empty and it's not the only group, remove it
    if (newGroups[gIndex].length === 0 && newGroups.length > 1) {
      newGroups.splice(gIndex, 1);
    }
    setGroups(newGroups);
  };

  const buildBackendQuery = () => {
    let finalGroups = [...groups];
    if (inputValue.trim()) {
      finalGroups[finalGroups.length - 1] = [...finalGroups[finalGroups.length - 1], inputValue.trim()];
    }
    
    // Filter out completely empty groups
    finalGroups = finalGroups.filter(g => g.length > 0);
    
    // Convert to string: group words are joined by space (AND), groups are joined by comma (OR)
    return finalGroups.map(g => g.join(" ")).join(", ");
  };

  async function handleSearch(e) {
    e.preventDefault();
    const finalQuery = buildBackendQuery();
    if (!finalQuery) return;
    
    try {
      const searchData = await fetchSearch(finalQuery);
      const activityData = await fetchActivity(finalQuery, interval);
      const speakersData = await fetchSpeakers(finalQuery);

      setSpeeches(searchData.results || []);
      setActivity(activityData.activity || []);
      setSpeakers(speakersData.speakers || []);
      setView("dashboard");
      
      // Auto-commit the input into the active group
      if (inputValue.trim()) {
        const newGroups = [...groups];
        newGroups[newGroups.length - 1] = [...newGroups[newGroups.length - 1], inputValue.trim()];
        setGroups(newGroups);
        setInputValue("");
      }
    } catch (error) {
      console.error("Frontend request failed:", error);
    }
  }

  const handleKeyDown = (e) => {
    // If they press space, we could auto-trigger "AND", but standard form submit is enter
    if (e.key === 'Enter') {
      // Let form submit naturally
    }
  };

  return (
    <div className="app-container">
      <div className="header">
        <h1>
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="url(#paint0_linear)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M2 17L12 22L22 17" stroke="url(#paint1_linear)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M2 12L12 17L22 12" stroke="url(#paint2_linear)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            <defs>
              <linearGradient id="paint0_linear" x1="2" y1="7" x2="22" y2="7" gradientUnits="userSpaceOnUse">
                <stop stopColor="#3b82f6" />
                <stop offset="1" stopColor="#8b5cf6" />
              </linearGradient>
              <linearGradient id="paint1_linear" x1="2" y1="19.5" x2="22" y2="19.5" gradientUnits="userSpaceOnUse">
                <stop stopColor="#3b82f6" />
                <stop offset="1" stopColor="#8b5cf6" />
              </linearGradient>
              <linearGradient id="paint2_linear" x1="2" y1="14.5" x2="22" y2="14.5" gradientUnits="userSpaceOnUse">
                <stop stopColor="#3b82f6" />
                <stop offset="1" stopColor="#8b5cf6" />
              </linearGradient>
            </defs>
          </svg>
          Riigikogu Search
        </h1>
      </div>

      <form onSubmit={handleSearch} className="search-section">
        <div className="search-groups-container">
          {groups.map((group, gIndex) => (
            <React.Fragment key={gIndex}>
              {gIndex > 0 && <div className="or-divider">OR</div>}
              
              <div className="and-group-box">
                {group.map((word, wIndex) => (
                   <span key={wIndex} className="token-pill word">
                     {word}
                     <button type="button" onClick={() => removeWord(gIndex, wIndex)}>&times;</button>
                   </span>
                ))}
                
                {/* Show input only in the last active group */}
                {gIndex === groups.length - 1 && (
                   <input
                     className="search-input"
                     value={inputValue}
                     onChange={(e) => setInputValue(e.target.value)}
                     onKeyDown={handleKeyDown}
                     placeholder={group.length === 0 && gIndex === 0 ? "Sisesta märksõna (nt kliima)..." : "Lisa sõna (AND)..."}
                   />
                )}
              </div>
            </React.Fragment>
          ))}
        </div>

        <div className="search-controls">
          <div className="logic-buttons">
            <button type="button" className="logic-btn and-btn" onClick={handleAddAnd}>+ AND (koos)</button>
            <button type="button" className="logic-btn or-btn" onClick={handleAddOr}>+ OR (uus grupp)</button>
          </div>
          
          <div style={{ flex: 1 }}></div>

          <select
            className="search-select"
            value={interval}
            onChange={(e) => setSelectedInterval(e.target.value)}
          >
            <option value="daily">Päev</option>
            <option value="weekly">Nädal</option>
            <option value="monthly">Kuu</option>
          </select>
          <button type="submit" className="search-button">
            Otsi
          </button>
        </div>
      </form>

      {speeches.length === 0 && activity.length === 0 && (
        <div style={{ textAlign: 'center', marginTop: '4rem', color: '#64748b' }}>
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style={{marginBottom: '1rem', opacity: 0.5}}>
            <path d="M21 21L15 15M17 10C17 13.866 13.866 17 10 17C6.13401 17 3 13.866 3 10C3 6.13401 6.13401 3 10 3C13.866 3 17 6.13401 17 10Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          <p>Alustamiseks sisesta märksõna ja vajuta "Otsi"</p>
        </div>
      )}

      {view === "dashboard" && activity.length > 0 && (
        <>
          <div className="dashboard-grid">
            <div className="glass-panel">
              <div className="chart-header">
                <h2>Aktiivsus ajas</h2>
              </div>
              <div style={{ width: "100%", height: 350 }}>
                <ResponsiveContainer>
                  <AreaChart data={activity} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                    <defs>
                      <linearGradient id="colorCount" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.6}/>
                        <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <XAxis 
                      dataKey={interval === "daily" ? "date" : interval === "weekly" ? "week" : "month"} 
                      stroke="#4b5563"
                      tick={{fill: '#9ca3af', fontSize: 12}}
                      tickLine={false}
                      axisLine={false}
                    />
                    <YAxis 
                      stroke="#4b5563"
                      tick={{fill: '#9ca3af', fontSize: 12}}
                      tickLine={false}
                      axisLine={false}
                    />
                    <Tooltip {...tooltipStyle} cursor={{ stroke: 'rgba(255,255,255,0.1)', strokeWidth: 2 }} />
                    <Area type="monotone" dataKey="count" name="Mainimisi" stroke="#8b5cf6" strokeWidth={3} fillOpacity={1} fill="url(#colorCount)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="glass-panel">
              <div className="chart-header">
                <h2>Top kõnelejad</h2>
              </div>
              <div className="speakers-list">
                {speakers.slice(0, 8).map((sp, idx) => (
                  <div key={idx} className="speaker-item">
                    <div className="speaker-info">
                      <span className="speaker-rank">{idx + 1}</span>
                      <div style={{ display: 'flex', flexDirection: 'column' }}>
                        <span className="speaker-name">{sp.speaker}</span>
                      </div>
                    </div>
                    <span className="speaker-count">{sp.count}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {speeches.length > 0 && (
            <div style={{ display: 'flex', justifyContent: 'center', marginTop: '2.5rem' }}>
              <button 
                className="search-button" 
                style={{ padding: '1rem 3rem', fontSize: '1.1rem' }}
                onClick={() => setView("speeches")}
              >
                Vaata leitud stenogramme ({speeches.length}) &rarr;
              </button>
            </div>
          )}
        </>
      )}

      {view === "speeches" && speeches.length > 0 && (
        <div className="glass-panel" style={{ marginTop: '0.5rem' }}>
          <div className="chart-header" style={{ marginBottom: '1.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
              <button 
                onClick={() => setView("dashboard")} 
                style={{ background: 'transparent', border: 'none', color: '#8b5cf6', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '1rem', fontWeight: 600, padding: 0 }}
              >
                &larr; Tagasi töölauale
              </button>
              <h2 style={{ margin: 0, paddingLeft: '1rem', borderLeft: '1px solid rgba(255,255,255,0.1)' }}>Leitud stenogrammid</h2>
            </div>
          </div>
          <div className="speeches-list">
            {speeches.map((speech, index) => (
              <div key={index} className="glass-panel speech-card">
                <div className="speech-meta">
                  <span style={{color: '#f8fafc', fontWeight: 500}}>{speech.speaker}</span>
                  <span>•</span>
                  <span style={{color: '#94a3b8'}}>{formatDateTime(speech.date, speech.time)}</span>
                </div>
                <p className="speech-text">{speech.text.slice(0, 350)}...</p>
                <a href={speech.source_url} target="_blank" rel="noreferrer" className="speech-link">
                  Ava stenogramm 
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style={{marginLeft: '4px'}}>
                    <path d="M7 17L17 7M17 7H7M17 7V17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </a>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
