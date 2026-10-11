import React from "react";

export function Footer({ onOpenMethodology }) {
  return (
    <footer
      className="footer-wrap"
      style={{
        textAlign: "center",
        padding: "2rem 1rem",
        color: "var(--color-text-muted, #94a3b8)",
        fontSize: "0.85rem",
      }}
    >
      <p style={{ margin: "0.25rem 0" }}>
        Riigikogu stenogrammid ja avaandmed ·{" "}
        <button
          type="button"
          onClick={onOpenMethodology}
          style={{
            background: "none",
            border: "none",
            color: "inherit",
            textDecoration: "underline",
            cursor: "pointer",
            font: "inherit",
            padding: 0,
          }}
        >
          Andmed ja metoodika
        </button>
      </p>
    </footer>
  );
}

export default Footer;
