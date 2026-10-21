import { useEffect, useRef } from "react";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "area[href]",
  'input:not([disabled]):not([type="hidden"])',
  "select:not([disabled])",
  "textarea:not([disabled])",
  "button:not([disabled])",
  "iframe",
  "object",
  "embed",
  "[contenteditable]",
  '[tabindex]:not([tabindex^="-"])',
].join(",");

/**
 * Traps keyboard focus inside a modal dialog when active.
 *
 * - On open: saves previously focused element, moves focus into dialog (first focusable or container).
 * - On Tab / Shift+Tab: wraps focus within the modal container.
 * - On Escape: invokes onClose callback.
 * - On close / unmount: restores focus back to the previously active element.
 */
export function useFocusTrap({ isOpen = true, onClose, initialFocusRef } = {}) {
  const containerRef = useRef(null);
  const previousActiveElementRef = useRef(null);

  useEffect(() => {
    if (!isOpen) return undefined;

    previousActiveElementRef.current = document.activeElement;

    const container = containerRef.current;
    if (container) {
      if (initialFocusRef?.current) {
        initialFocusRef.current.focus();
      } else {
        const focusables = container.querySelectorAll(FOCUSABLE_SELECTOR);
        if (focusables.length > 0) {
          focusables[0].focus();
        } else {
          container.focus();
        }
      }
    }

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        if (onClose) {
          event.preventDefault();
          event.stopPropagation();
          onClose();
        }
        return;
      }

      if (event.key !== "Tab") return;

      const modalElement = containerRef.current;
      if (!modalElement) return;

      const focusables = Array.from(modalElement.querySelectorAll(FOCUSABLE_SELECTOR));
      if (focusables.length === 0) {
        event.preventDefault();
        modalElement.focus();
        return;
      }

      const firstFocusable = focusables[0];
      const lastFocusable = focusables[focusables.length - 1];

      if (event.shiftKey) {
        if (
          document.activeElement === firstFocusable ||
          !modalElement.contains(document.activeElement)
        ) {
          event.preventDefault();
          lastFocusable.focus();
        }
      } else {
        if (
          document.activeElement === lastFocusable ||
          !modalElement.contains(document.activeElement)
        ) {
          event.preventDefault();
          firstFocusable.focus();
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      const prev = previousActiveElementRef.current;
      const isVisible = (el) => {
        if (!el || !document.contains(el)) return false;
        if (el.offsetWidth === 0 && el.offsetHeight === 0) return false;
        const style = window.getComputedStyle(el);
        return style.display !== "none" && style.visibility !== "hidden";
      };

      if (isVisible(prev) && typeof prev.focus === "function") {
        prev.focus();
      } else {
        const headerMenuTrigger = document.querySelector(".header-menu-trigger");
        if (headerMenuTrigger && typeof headerMenuTrigger.focus === "function") {
          headerMenuTrigger.focus();
        }
      }
    };
  }, [isOpen, onClose, initialFocusRef]);

  return containerRef;
}

export default useFocusTrap;
