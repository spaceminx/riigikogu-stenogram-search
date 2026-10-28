import React, { useEffect, useRef, useState } from "react";
import { fetchSuggestions } from "../lib/api";
import { mergeInputToGroups } from "../lib/formatters";
import {
  formatSuggestionCount,
  getNextHighlightedIndex,
  isPrefixEligible,
} from "../lib/suggestHelpers";

const suggestionsCache = new Map();

export function SearchQueryInput({
  groups,
  setGroups,
  inputValue,
  setInputValue,
  onSearch,
  loading = false,
  children,
}) {
  const [suggestions, setSuggestions] = useState([]);
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);

  const containerRef = useRef(null);
  const inputRef = useRef(null);
  const abortControllerRef = useRef(null);

  useEffect(() => {
    if (!isPrefixEligible(inputValue)) {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      return;
    }

    const trimmed = inputValue.trim().toLowerCase();

    if (suggestionsCache.has(trimmed)) {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      const cached = suggestionsCache.get(trimmed);
      const timer = setTimeout(() => {
        setSuggestions(cached);
        setIsOpen(cached.length > 0);
        setHighlightedIndex(-1);
      }, 0);
      return () => clearTimeout(timer);
    }

    const timer = setTimeout(async () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      const controller = new AbortController();
      abortControllerRef.current = controller;

      try {
        const data = await fetchSuggestions(trimmed, {
          limit: 8,
          signal: controller.signal,
        });
        if (!controller.signal.aborted) {
          const results = Array.isArray(data) ? data : [];
          suggestionsCache.set(trimmed, results);
          setSuggestions(results);
          setIsOpen(results.length > 0);
          setHighlightedIndex(-1);
        }
      } catch (err) {
        if (err.name !== "AbortError") {
          setSuggestions([]);
          setIsOpen(false);
          setHighlightedIndex(-1);
        }
      }
    }, 200);

    return () => {
      clearTimeout(timer);
    };
  }, [inputValue]);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setIsOpen(false);
        setHighlightedIndex(-1);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  const handleInputChange = (e) => {
    const val = e.target.value;
    setInputValue(val);
    if (!isPrefixEligible(val)) {
      setSuggestions([]);
      setIsOpen(false);
      setHighlightedIndex(-1);
    }
  };

  const handleSelectSuggestion = (term) => {
    if (!term) return;
    const newGroups = mergeInputToGroups(groups, term);
    setGroups(newGroups);
    setInputValue("");
    setSuggestions([]);
    setHighlightedIndex(-1);
    setIsOpen(false);
    if (inputRef.current) {
      inputRef.current.focus();
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "ArrowDown") {
      if (suggestions.length > 0) {
        e.preventDefault();
        if (!isOpen) {
          setIsOpen(true);
          setHighlightedIndex(0);
        } else {
          setHighlightedIndex((prev) => getNextHighlightedIndex(prev, 1, suggestions.length));
        }
      }
    } else if (e.key === "ArrowUp") {
      if (suggestions.length > 0) {
        e.preventDefault();
        if (!isOpen) {
          setIsOpen(true);
          setHighlightedIndex(suggestions.length - 1);
        } else {
          setHighlightedIndex((prev) => getNextHighlightedIndex(prev, -1, suggestions.length));
        }
      }
    } else if (e.key === "Enter") {
      if (isOpen && highlightedIndex >= 0 && suggestions[highlightedIndex]) {
        e.preventDefault();
        e.stopPropagation();
        handleSelectSuggestion(suggestions[highlightedIndex].term);
      } else {
        setIsOpen(false);
      }
    } else if (e.key === "Escape") {
      if (isOpen) {
        e.preventDefault();
        setIsOpen(false);
        setHighlightedIndex(-1);
      }
    } else if (e.key === "Backspace" && inputValue === "") {
      // Backspace in an empty input removes the last pill
      if (groups.length > 0) {
        const lastGroupIdx = groups.length - 1;
        const lastGroup = groups[lastGroupIdx];
        if (lastGroup.length > 0) {
          e.preventDefault();
          removeWord(lastGroupIdx, lastGroup.length - 1);
        } else if (groups.length > 1) {
          e.preventDefault();
          // Remove empty trailing group
          setGroups(groups.slice(0, lastGroupIdx));
        }
      }
    }
  };

  const handleAddAnd = () => {
    setIsOpen(false);
    if (inputValue.trim()) {
      const newGroups = mergeInputToGroups(groups, inputValue.trim());
      setGroups(newGroups);
      setInputValue("");
    }
  };

  const handleAddOr = () => {
    setIsOpen(false);
    if (inputValue.trim()) {
      const newGroups = mergeInputToGroups(groups, inputValue.trim());
      setGroups([...newGroups, []]);
      setInputValue("");
    } else if (groups.length > 0 && groups[groups.length - 1].length > 0) {
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

  const showDropdown = isPrefixEligible(inputValue) && isOpen && suggestions.length > 0;

  return (
    <form onSubmit={onSearch} className="search-section">
      <div className="search-query-row">
        <div
          ref={containerRef}
          className="search-groups-container"
          role="presentation"
          onClick={(e) => {
            if (
              !e.target.closest("button") &&
              !e.target.closest(".search-suggestions-dropdown") &&
              !e.target.classList.contains("search-input")
            ) {
              if (inputRef.current) inputRef.current.focus();
            }
          }}
          onKeyDown={(e) => {
            if ((e.key === "Enter" || e.key === " ") && e.target === containerRef.current) {
              if (inputRef.current) inputRef.current.focus();
            }
          }}
        >
          {groups.map((group, gIndex) => (
            <React.Fragment key={gIndex}>
              {gIndex > 0 && <span className="or-divider">VÕI</span>}
              <div className="and-group-box">
                {group.map((word, wIndex) => {
                  const isPhrase = word.includes(" ") || word.includes(",");
                  return (
                    <span key={wIndex} className="token-pill">
                      {isPhrase ? `"${word}"` : word}
                      <button
                        type="button"
                        onClick={() => removeWord(gIndex, wIndex)}
                        title={isPhrase ? "Eemalda fraas" : "Eemalda sõna"}
                        aria-label={`Eemalda „${word}“`}
                      >
                        &times;
                      </button>
                    </span>
                  );
                })}
                {gIndex === groups.length - 1 && (
                  <input
                    ref={inputRef}
                    type="text"
                    className="search-input"
                    role="combobox"
                    aria-label="Otsingusõna"
                    aria-autocomplete="list"
                    aria-expanded={showDropdown}
                    aria-controls={showDropdown ? "search-suggestions-list" : undefined}
                    aria-activedescendant={
                      showDropdown && highlightedIndex >= 0
                        ? `suggestion-option-${highlightedIndex}`
                        : undefined
                    }
                    placeholder={
                      group.length === 0 && groups.length === 1
                        ? "Sisesta otsisõna (nt kliima, mets, eelarve)..."
                        : "Lisa sõna..."
                    }
                    value={inputValue}
                    onChange={handleInputChange}
                    onKeyDown={handleKeyDown}
                    onFocus={() => {
                      if (suggestions.length > 0) {
                        setIsOpen(true);
                      }
                    }}
                  />
                )}
              </div>
            </React.Fragment>
          ))}

          {showDropdown && (
            <ul
              id="search-suggestions-list"
              className="search-suggestions-dropdown"
              role="listbox"
              aria-label="Otsingusõnade soovitused"
            >
              {suggestions.map((item, idx) => (
                <li
                  key={`${item.lemma}-${idx}`}
                  id={`suggestion-option-${idx}`}
                  role="option"
                  aria-selected={idx === highlightedIndex}
                  className={`search-suggestion-item ${
                    idx === highlightedIndex ? "is-highlighted" : ""
                  }`}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    handleSelectSuggestion(item.term);
                  }}
                  onClick={() => {
                    handleSelectSuggestion(item.term);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      handleSelectSuggestion(item.term);
                    }
                  }}
                  onMouseEnter={() => setHighlightedIndex(idx)}
                >
                  <span className="suggestion-term">{item.term}</span>
                  <span className="suggestion-count">{formatSuggestionCount(item.df)}</span>
                </li>
              ))}
            </ul>
          )}
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

      <div className="search-hint">
        Iga plokk on eraldi otsingusõna või fraas. Mitmesõnaline plokk otsib täpset fraasi. Lisa
        plokke nuppudega „+ JA“ ja „+ VÕI“.
      </div>

      {children}
    </form>
  );
}

export default SearchQueryInput;
