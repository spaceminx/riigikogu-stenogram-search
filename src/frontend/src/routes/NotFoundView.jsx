import React from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, HelpCircle } from "lucide-react";

export function NotFoundView() {
  return (
    <div
      className="glass-panel"
      style={{
        padding: "3rem 1.5rem",
        textAlign: "center",
        margin: "2rem auto",
        maxWidth: "600px",
      }}
    >
      <div
        style={{
          display: "inline-flex",
          padding: "1rem",
          borderRadius: "50%",
          background: "var(--color-bg-subtle, #f1f5f9)",
          marginBottom: "1rem",
        }}
      >
        <HelpCircle size={48} color="var(--color-primary, #315b84)" />
      </div>
      <h2 style={{ fontSize: "1.75rem", marginBottom: "0.5rem" }}>404 – Lehekülge ei leitud</h2>
      <p
        style={{ color: "var(--color-text-muted, #64748b)", marginBottom: "2rem", lineHeight: 1.6 }}
      >
        Otsitud aadressi ei eksisteeri või on see teisaldatud.
      </p>
      <Link
        to="/"
        className="search-button"
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "0.5rem",
          textDecoration: "none",
        }}
      >
        <ArrowLeft size={16} />
        <span>Tagasi avalehele</span>
      </Link>
    </div>
  );
}

export default NotFoundView;
