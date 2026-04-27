import { useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar } from "recharts";
import { fetchSearch, fetchActivity, fetchSpeakers } from "./api";
import "./App.css";

function App() {
  const [query, setQuery] = useState("");
  const [interval, setSelectedInterval] = useState("monthly");
  const [speeches, setSpeeches] = useState([]);
  const [activity, setActivity] = useState([]);
  const [speakers, setSpeakers] = useState([]);
  const [darkMode, setDarkMode] = useState(true);


  async function handleSearch(e) {
  e.preventDefault();

  if (!query.trim()) return;

  try {
    const searchData = await fetchSearch(query);
    const activityData = await fetchActivity(query, interval);
    const speakersData = await fetchSpeakers(query);

    console.log("searchData", searchData);
    console.log("activityData", activityData);
    console.log("speakersData", speakersData);

    setSpeeches(searchData.results || []);
    setActivity(activityData.activity || []);
    setSpeakers(speakersData.speakers || []);
  } catch (error) {
    console.error("Frontend request failed:", error);
  }
}

  return (
  <div className={darkMode ? "app dark" : "app light"}>
    <div className="header">
      <h1>Riigikogu stenogrammide otsing</h1>

      <button
        className="theme-toggle"
        onClick={() => setDarkMode(!darkMode)}
      >
        {darkMode ? "Light mode" : "Dark mode"}
      </button>
    </div>
      <form onSubmit={handleSearch}>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Sisesta märksõna, nt kliima"
          style={{ padding: "0.75rem", width: "300px" }}
        />

        <select
          value={interval}
          onChange={(e) => setSelectedInterval(e.target.value)}
          style={{ padding: "0.75rem", marginLeft: "0.5rem" }}
        >
          <option value="daily">Päev</option>
          <option value="weekly">Nädal</option>
          <option value="monthly">Kuu</option>
        </select>

        <button
          style={{ padding: "0.75rem", marginLeft: "0.5rem" }}
        >
          Otsi
        </button>
      </form>

      <h2>Aktiivsus ajas</h2>
      <div style={{ width: "100%", height: 300 }}>
        <ResponsiveContainer>
          <LineChart data={activity}>
            <XAxis dataKey={interval === "daily" ? "date" : interval === "weekly" ? "week" : "month"} />
            <YAxis />
            <Tooltip />
            <Line type="monotone" dataKey="count" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <h2>Top kõnelejad</h2>
      <div style={{ width: "100%", height: 300 }}>
        <ResponsiveContainer>
          <BarChart data={speakers}>
            <XAxis dataKey="speaker" />
            <YAxis />
            <Tooltip />
            <Bar dataKey="count" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <h2>Kõned</h2>
      {speeches.map((speech, index) => (
        <div key={index} className="speech-card">
          <strong>{speech.date} {speech.time} — {speech.speaker}</strong>
          <p>{speech.text.slice(0, 700)}...</p>
          <a href={speech.source_url} target="_blank">Ava stenogramm</a>
        </div>
      ))}
  </div>
  );
}

export default App;
