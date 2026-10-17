import React from "react";
import { Link } from "react-router-dom";

export function Footer({ onOpenMethodology }) {
  return (
    <footer
      className="footer-wrap"
      style={{
        textAlign: "center",
        padding: "2rem 1rem",
        color: "var(--text-secondary)",
        fontSize: "0.85rem",
      }}
    >
      <p style={{ margin: "0.25rem 0" }}>
        <Link
          to="/andmed"
          style={{
            color: "inherit",
            textDecoration: "underline",
          }}
        >
          Andmed ja privaatsus
        </Link>
        {" · "}
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
      <p style={{ margin: "0.25rem 0" }}>Andmed: Riigikogu, CC BY-SA</p>
    </footer>
  );
}

export default Footer;
