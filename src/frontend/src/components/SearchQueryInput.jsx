import React from "react";

export function SearchQueryInput({
  groups,
  setGroups,
  inputValue,
  setInputValue,
  onSearch,
  loading = false,
}) {
  const handleAddAnd = () => {
    if (inputValue.trim()) {
      const newGroups = [...groups];
      newGroups[newGroups.length - 1] = [...newGroups[newGroups.length - 1], inputValue.trim()];
      setGroups(newGroups);
      setInputValue("");
    }
  };

  const handleAddOr = () => {
    if (inputValue.trim()) {
      const newGroups = [...groups];
      newGroups[newGroups.length - 1] = [...newGroups[newGroups.length - 1], inputValue.trim()];
      newGroups.push([]);
      setGroups(newGroups);
      setInputValue("");
    } else if (groups[groups.length - 1].length > 0) {
      setGroups([...groups, []]);
    }
  };

  const removeWord = (gIndex, wIndex) => {
    const newGroups = groups.map((g, gi) =>
      gi === gIndex ? g.filter((_, wi) => wi !== wIndex) : g
    );
    const cleaned = newGroups.filter((g) => g.length > 0);
    setGroups(cleaned.length === 0 ? [[]] : cleaned);
  };

  return (
    <form onSubmit={onSearch} className="search-section">
      <div className="search-query-row">
        <div
          className="search-groups-container"
          onClick={(e) => {
            if (!e.target.closest("button") && !e.target.classList.contains("search-input")) {
              const input = e.currentTarget.querySelector(".search-input");
              if (input) input.focus();
            }
          }}
        >
          {groups.map((group, gIndex) => (
            <React.Fragment key={gIndex}>
              {gIndex > 0 && <span className="or-divider">VÕI</span>}
              <div className="and-group-box">
                {group.map((word, wIndex) => (
                  <span key={wIndex} className="token-pill">
                    {word}
                    <button
                      type="button"
                      onClick={() => removeWord(gIndex, wIndex)}
                      title="Eemalda sõna"
                    >
                      &times;
                    </button>
                  </span>
                ))}
                {gIndex === groups.length - 1 && (
                  <input
                    type="text"
                    className="search-input"
                    placeholder={
                      group.length === 0 && groups.length === 1
                        ? "Sisesta otsisõna (nt kliima, mets, eelarve)..."
                        : "Lisa sõna..."
                    }
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                  />
                )}
              </div>
            </React.Fragment>
          ))}
        </div>
        <div className="logic-buttons" aria-label="Otsingutingimuste loogika">
          <button
            type="button"
            className="logic-btn and-btn"
            onClick={handleAddAnd}
            title="Lisa sõna samasse gruppi (mõlemad peavad esinema)"
          >
            + JA
          </button>
          <button
            type="button"
            className="logic-btn or-btn"
            onClick={handleAddOr}
            title="Alusta uut gruppi (üks või teine peab esinema)"
          >
            + VÕI
          </button>
        </div>
      </div>

      <div className="search-controls">
        <button type="submit" className="search-button" disabled={loading}>
          {loading ? "Otsin..." : "Otsi"}
        </button>
      </div>
    </form>
  );
}

export default SearchQueryInput;
