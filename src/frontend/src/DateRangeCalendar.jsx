import { useEffect, useMemo, useRef, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";

const WEEKDAYS = ["E", "T", "K", "N", "R", "L", "P"];
const MONTHS = [
  "jaanuar", "veebruar", "märts", "aprill", "mai", "juuni",
  "juuli", "august", "september", "oktoober", "november", "detsember",
];

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
    return new Date(start?.getFullYear() ?? now.getFullYear(), start?.getMonth() ?? now.getMonth(), 1);
  });
  const rootRef = useRef(null);
  const sessionDates = useMemo(() => new Set(dates), [dates]);
  const monthCount = compact ? 1 : 2;
  const months = Array.from({ length: monthCount }, (_, index) => shiftMonth(visibleMonth, index));

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

  const renderMonth = (month) => {
    const days = getMonthDays(month);
    const start = fromDateKey(value.startDate);
    const end = fromDateKey(value.endDate);
    const monthKey = `${month.getFullYear()}-${month.getMonth()}`;

    return (
      <section className="calendar-month" key={monthKey} aria-label={monthTitle(month)}>
        <div className="calendar-month-title">{monthTitle(month)}</div>
        <div className="calendar-weekdays" aria-hidden="true">
          {WEEKDAYS.map((weekday, index) => <span key={`${weekday}-${index}`}>{weekday}</span>)}
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
            ].filter(Boolean).join(" ");

            return (
              <button
                className={classes}
                type="button"
                disabled={compact && !hasSession}
                key={dateKey}
                aria-label={hasSession ? tooltip : `${date.getDate()}. ${MONTHS[date.getMonth()]} ${date.getFullYear()}`}
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
                {hasSession && <span id={`session-tooltip-${monthKey}-${dateKey}`} className="calendar-day-tooltip" role="tooltip">{tooltip}</span>}
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
          <div className="calendar-popover compact-calendar-popover" role="dialog" aria-label="Riigikogu istungite kalender">
            <div className="calendar-popover-header">
              <button type="button" className="calendar-nav-button" aria-label="Eelmine kuu" onClick={() => setVisibleMonth((month) => shiftMonth(month, -1))}>
                <ChevronLeft aria-hidden="true" />
              </button>
              <strong>{monthTitle(visibleMonth)}</strong>
              <button type="button" className="calendar-nav-button" aria-label="Järgmine kuu" onClick={() => setVisibleMonth((month) => shiftMonth(month, 1))}>
                <ChevronRight aria-hidden="true" />
              </button>
            </div>
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
      <label className="filter-label" htmlFor="date-range-trigger">Kuupäevad:</label>
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
        <div className="calendar-popover date-range-popover" role="dialog" aria-label="Kuupäevavahemiku valimine">
          <div className="calendar-popover-header">
            <button type="button" className="calendar-nav-button" aria-label="Eelmised kuud" onClick={() => setVisibleMonth((month) => shiftMonth(month, -1))}>
              <ChevronLeft aria-hidden="true" />
            </button>
            <strong>Vali istungite ajavahemik</strong>
            <button type="button" className="calendar-nav-button" aria-label="Järgmised kuud" onClick={() => setVisibleMonth((month) => shiftMonth(month, 1))}>
              <ChevronRight aria-hidden="true" />
            </button>
          </div>
          <div className="calendar-months">{months.map(renderMonth)}</div>
          <div className="calendar-popover-footer">
            <span>{value.startDate ? `${formatDate(value.startDate)}${value.endDate ? ` – ${formatDate(value.endDate)}` : " – vali lõpp"}` : "Vali algus- ja lõppkuupäev"}</span>
            <div>
              <button type="button" className="calendar-clear-button" onClick={() => onChange?.({ startDate: "", endDate: "" })}>Tühjenda</button>
              <button type="button" className="calendar-done-button" onClick={() => setIsOpen(false)}>Valmis</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

