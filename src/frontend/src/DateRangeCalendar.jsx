import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";

const WEEKDAYS = ["E", "T", "K", "N", "R", "L", "P"];
const MONTHS = [
  "jaanuar",
  "veebruar",
  "märts",
  "aprill",
  "mai",
  "juuni",
  "juuli",
  "august",
  "september",
  "oktoober",
  "november",
  "detsember",
];
const currentYear = new Date().getFullYear();
const YEARS = Array.from(
  { length: Math.max(8, currentYear - 2019 + 2) },
  (_, index) => 2019 + index
);
const CALENDAR_MIN_MONTH = new Date(2019, 0, 1);
const CALENDAR_MAX_MONTH = new Date(currentYear + 1, 11, 1);
const QUICK_PRESETS = [
  { id: "xv", label: "XV Riigikogu (2023–praegu)" },
  { id: "xiv", label: "XIV Riigikogu (2019–2023)" },
  { id: "year", label: "Viimane aasta" },
  { id: "archive", label: "Kogu arhiiv" },
];

function clampMonth(date) {
  if (date < CALENDAR_MIN_MONTH) return CALENDAR_MIN_MONTH;
  if (date > CALENDAR_MAX_MONTH) return CALENDAR_MAX_MONTH;
  return date;
}

function getPresetRange(presetId, dates) {
  const today = new Date();
  const todayKey = toDateKey(today);
  if (presetId === "xv") return { startDate: "2023-04-10", endDate: todayKey };
  if (presetId === "xiv") return { startDate: "2019-04-04", endDate: "2023-04-09" };
  if (presetId === "year") {
    const yearAgo = new Date(today);
    yearAgo.setFullYear(yearAgo.getFullYear() - 1);
    return { startDate: toDateKey(yearAgo), endDate: todayKey };
  }
  const orderedDates = [...dates].sort();
  return {
    startDate: orderedDates[0] || "2019-01-01",
    endDate: orderedDates.at(-1) || todayKey,
  };
}

function toDateKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function fromDateKey(value) {
  if (!value) return null;
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function shiftMonth(date, amount) {
  return new Date(date.getFullYear(), date.getMonth() + amount, 1);
}

function formatDate(value) {
  if (!value) return "";
  const [year, month, day] = value.split("-");
  return `${day}.${month}.${year}`;
}

function getMonthDays(month) {
  const first = new Date(month.getFullYear(), month.getMonth(), 1);
  const mondayOffset = (first.getDay() + 6) % 7;
  const gridStart = new Date(first);
  gridStart.setDate(first.getDate() - mondayOffset);
  return Array.from({ length: 42 }, (_, index) => {
    const date = new Date(gridStart);
    date.setDate(gridStart.getDate() + index);
    return date;
  });
}

function monthTitle(date) {
  return `${MONTHS[date.getMonth()]} ${date.getFullYear()}`;
}

export default function DateRangeCalendar({
  compact = false,
  dates = [],
  value = { startDate: "", endDate: "" },
  onChange,
  onSelectDate,
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [visibleMonth, setVisibleMonth] = useState(() => {
    const start = fromDateKey(value.startDate);
    const now = new Date();
    return clampMonth(
      new Date(start?.getFullYear() ?? now.getFullYear(), start?.getMonth() ?? now.getMonth(), 1)
    );
  });
  const rootRef = useRef(null);
  const popoverRef = useRef(null);
  const [popoverPosition, setPopoverPosition] = useState(null);
  const sessionDates = useMemo(() => new Set(dates), [dates]);
  const monthCount = compact ? 1 : 2;
  const months = Array.from({ length: monthCount }, (_, index) => shiftMonth(visibleMonth, index));

  const changeVisibleMonth = (amount) => {
    setVisibleMonth((month) => clampMonth(shiftMonth(month, amount)));
  };

  const applyPreset = (presetId) => {
    const nextRange = getPresetRange(presetId, dates);
    onChange?.(nextRange);
    setVisibleMonth(clampMonth(fromDateKey(nextRange.startDate)));
  };

  useLayoutEffect(() => {
    if (!isOpen) return undefined;

    const positionPopover = () => {
      const trigger = rootRef.current?.querySelector(
        compact ? ".compact-calendar-toggle" : ".date-range-trigger"
      );
      const popover = popoverRef.current;
      if (!trigger || !popover) return;

      const triggerRect = trigger.getBoundingClientRect();
      const popoverRect = popover.getBoundingClientRect();
      const availableBelow = window.innerHeight - triggerRect.bottom - 9;
      const availableAbove = triggerRect.top - 9;
      const maxHeight = Math.max(0, window.innerHeight - 32);

      let top;
      if (compact) {
        // Compact calendar is located near the bottom of the sidebar - open upwards if space permits or if more room is above
        if (availableAbove >= popoverRect.height || availableAbove >= availableBelow) {
          top = Math.max(16, triggerRect.top - popoverRect.height - 8);
        } else {
          top = triggerRect.bottom + 8;
        }
      } else {
        top =
          popoverRect.height <= availableBelow
            ? triggerRect.bottom + 9
            : popoverRect.height <= availableAbove
              ? triggerRect.top - popoverRect.height - 9
              : 16;
      }

      const left = Math.max(
        16,
        Math.min(triggerRect.right - popoverRect.width, window.innerWidth - popoverRect.width - 16)
      );

      setPopoverPosition({
        position: "fixed",
        left: `${left}px`,
        top: `${top}px`,
        right: "auto",
        bottom: "auto",
        maxHeight: `${maxHeight}px`,
        zIndex: 1000,
      });
    };

    positionPopover();
    window.addEventListener("resize", positionPopover);
    window.addEventListener("scroll", positionPopover);
    return () => {
      window.removeEventListener("resize", positionPopover);
      window.removeEventListener("scroll", positionPopover);
    };
  }, [compact, isOpen]);

  useEffect(() => {
    if (!isOpen) return undefined;
    const handlePointerDown = (event) => {
      if (!rootRef.current?.contains(event.target)) setIsOpen(false);
    };
    const handleKeyDown = (event) => {
      if (event.key === "Escape") setIsOpen(false);
    };
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  const selectRangeDate = (dateKey) => {
    const { startDate, endDate } = value;
    if (!startDate || endDate) {
      onChange?.({ startDate: dateKey, endDate: "" });
      return;
    }
    if (dateKey < startDate) {
      onChange?.({ startDate: dateKey, endDate: startDate });
    } else {
      onChange?.({ startDate, endDate: dateKey });
    }
  };

  const renderCalendarHeader = () => (
    <div className="calendar-popover-header">
      <button
        type="button"
        className="calendar-nav-button"
        aria-label={compact ? "Eelmine kuu" : "Eelmised kuud"}
        disabled={visibleMonth <= CALENDAR_MIN_MONTH}
        onClick={() => changeVisibleMonth(-1)}
      >
        <ChevronLeft aria-hidden="true" />
      </button>
      <div className="calendar-selectors">
        <label
          className="calendar-select-label"
          htmlFor={compact ? "compact-calendar-month" : "date-range-month"}
        >
          Kuu
        </label>
        <select
          id={compact ? "compact-calendar-month" : "date-range-month"}
          className="calendar-select calendar-month-select"
          value={visibleMonth.getMonth()}
          onChange={(event) =>
            setVisibleMonth((month) => new Date(month.getFullYear(), Number(event.target.value), 1))
          }
        >
          {MONTHS.map((month, index) => (
            <option key={month} value={index}>
              {month}
            </option>
          ))}
        </select>
        <label
          className="calendar-select-label"
          htmlFor={compact ? "compact-calendar-year" : "date-range-year"}
        >
          Aasta
        </label>
        <select
          id={compact ? "compact-calendar-year" : "date-range-year"}
          className="calendar-select calendar-year-select"
          value={visibleMonth.getFullYear()}
          onChange={(event) =>
            setVisibleMonth((month) => new Date(Number(event.target.value), month.getMonth(), 1))
          }
        >
          {YEARS.map((year) => (
            <option key={year} value={year}>
              {year}
            </option>
          ))}
        </select>
      </div>
      <button
        type="button"
        className="calendar-nav-button"
        aria-label={compact ? "Järgmine kuu" : "Järgmised kuud"}
        disabled={visibleMonth >= CALENDAR_MAX_MONTH}
        onClick={() => changeVisibleMonth(1)}
      >
        <ChevronRight aria-hidden="true" />
      </button>
    </div>
  );

  const renderMonth = (month) => {
    const days = getMonthDays(month);
    const start = fromDateKey(value.startDate);
    const end = fromDateKey(value.endDate);
    const monthKey = `${month.getFullYear()}-${month.getMonth()}`;

    return (
      <section className="calendar-month" key={monthKey} aria-label={monthTitle(month)}>
        <div className="calendar-month-title">{monthTitle(month)}</div>
        <div className="calendar-weekdays" aria-hidden="true">
          {WEEKDAYS.map((weekday, index) => (
            <span key={`${weekday}-${index}`}>{weekday}</span>
          ))}
        </div>
        <div className="calendar-days">
          {days.map((date) => {
            const dateKey = toDateKey(date);
            const isInMonth = date.getMonth() === month.getMonth();
            const hasSession = sessionDates.has(dateKey);
            const isStart = dateKey === value.startDate;
            const isEnd = dateKey === value.endDate;
            const isBetween = Boolean(start && end && date > start && date < end);
            const tooltip = `${formatDate(dateKey)} – Täiskogu istung`;
            const classes = [
              "calendar-day",
              !isInMonth && "is-outside-month",
              !hasSession && "is-inactive",
              hasSession && "has-session",
              isStart && "is-range-start",
              isEnd && "is-range-end",
              isBetween && "is-in-range",
            ]
              .filter(Boolean)
              .join(" ");

            return (
              <button
                className={classes}
                type="button"
                disabled={compact && !hasSession}
                key={dateKey}
                aria-label={
                  hasSession
                    ? tooltip
                    : `${date.getDate()}. ${MONTHS[date.getMonth()]} ${date.getFullYear()}`
                }
                aria-describedby={hasSession ? `session-tooltip-${monthKey}-${dateKey}` : undefined}
                aria-pressed={isStart || isEnd}
                onClick={() => {
                  if (compact) {
                    onSelectDate?.(dateKey);
                    setIsOpen(false);
                  } else {
                    selectRangeDate(dateKey);
                  }
                }}
              >
                <span>{date.getDate()}</span>
                {hasSession && <i className="calendar-session-dot" aria-hidden="true" />}
                {hasSession && (
                  <span
                    id={`session-tooltip-${monthKey}-${dateKey}`}
                    className="calendar-day-tooltip"
                    role="tooltip"
                  >
                    {tooltip}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </section>
    );
  };

  if (compact) {
    return (
      <div className="compact-calendar" ref={rootRef}>
        <button
          type="button"
          className="compact-calendar-toggle"
          aria-expanded={isOpen}
          onClick={() => setIsOpen((open) => !open)}
        >
          <CalendarDays aria-hidden="true" />
          {isOpen ? "Peida kalender" : "Ava kalendrivaade"}
          <span aria-hidden="true">{isOpen ? "−" : "+"}</span>
        </button>
        {isOpen && (
          <div
            ref={popoverRef}
            style={popoverPosition || undefined}
            className="calendar-popover compact-calendar-popover"
            role="dialog"
            aria-label="Riigikogu istungite kalender"
          >
            {renderCalendarHeader()}
            {renderMonth(visibleMonth)}
            <p className="calendar-hint">Vali istungipäev, et avada selle kuupäeva kõned.</p>
          </div>
        )}
      </div>
    );
  }

  const rangeLabel = value.startDate
    ? `${formatDate(value.startDate)}${value.endDate ? ` – ${formatDate(value.endDate)}` : " – …"}`
    : "Vali kuupäevad (Algus – Lõpp)";

  return (
    <div className="date-range-picker" ref={rootRef}>
      <label className="filter-label" htmlFor="date-range-trigger">
        Kuupäevad:
      </label>
      <button
        id="date-range-trigger"
        type="button"
        className={`date-range-trigger${value.startDate ? " has-value" : ""}`}
        aria-expanded={isOpen}
        aria-haspopup="dialog"
        onClick={() => setIsOpen((open) => !open)}
      >
        <CalendarDays aria-hidden="true" />
        <span>{rangeLabel}</span>
      </button>
      {isOpen && (
        <div
          className="calendar-popover date-range-popover"
          ref={popoverRef}
          style={popoverPosition || undefined}
          role="dialog"
          aria-label="Kuupäevavahemiku valimine"
        >
          <div className="calendar-quick-presets" role="group" aria-label="Kiirvalikud">
            {QUICK_PRESETS.map((preset) => (
              <button
                type="button"
                className="calendar-preset-button"
                key={preset.id}
                onClick={() => applyPreset(preset.id)}
              >
                {preset.label}
              </button>
            ))}
          </div>
          {renderCalendarHeader()}
          <div className="calendar-months">{months.map(renderMonth)}</div>
          <div className="calendar-popover-footer">
            <span>
              {value.startDate
                ? `${formatDate(value.startDate)}${value.endDate ? ` – ${formatDate(value.endDate)}` : " – vali lõpp"}`
                : "Vali algus- ja lõppkuupäev"}
            </span>
            <div>
              <button
                type="button"
                className="calendar-clear-button"
                onClick={() => onChange?.({ startDate: "", endDate: "" })}
              >
                Tühjenda
              </button>
              <button
                type="button"
                className="calendar-done-button"
                onClick={() => setIsOpen(false)}
              >
                Valmis
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
