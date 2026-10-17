import React, { useEffect } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, ShieldCheck } from "lucide-react";
import { CONTROLLER_NAME, CONTACT_EMAIL } from "../lib/siteInfo";

export function PrivacyView({ onOpenMethodology }) {
  useEffect(() => {
    const prevTitle = document.title;
    document.title = "Andmed ja privaatsus — Riigivaade";
    return () => {
      document.title = prevTitle;
    };
  }, []);

  return (
    <div style={{ maxWidth: "800px", margin: "1rem auto 2rem" }}>
      <div className="glass-panel" style={{ padding: "2rem" }}>
        <div style={{ marginBottom: "1.5rem" }}>
          <Link
            to="/"
            className="back-nav-btn"
            style={{
              textDecoration: "none",
              display: "inline-flex",
              alignItems: "center",
              gap: "0.5rem",
            }}
          >
            <ArrowLeft size={16} /> Tagasi avalehele
          </Link>
        </div>

        <div
          style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1.5rem" }}
        >
          <ShieldCheck size={28} color="var(--accent-primary)" />
          <h1 style={{ margin: 0, fontSize: "1.75rem" }}>Andmed ja privaatsus</h1>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "1.75rem", lineHeight: 1.6 }}>
          <section>
            <h2 style={{ fontSize: "1.15rem", marginBottom: "0.5rem" }}>Kes haldab</h2>
            <p style={{ margin: 0, color: "var(--text-secondary)" }}>
              Riigivaate veebilehte haldab {CONTROLLER_NAME}. Küsimused, parandusettepanekud ja
              vastuväited:{" "}
              <a
                href={`mailto:${CONTACT_EMAIL}`}
                style={{ color: "var(--accent-primary)", textDecoration: "underline" }}
              >
                {CONTACT_EMAIL}
              </a>
              .
            </p>
          </section>

          <section>
            <h2 style={{ fontSize: "1.15rem", marginBottom: "0.5rem" }}>Külastajate andmed</h2>
            <p style={{ margin: 0, color: "var(--text-secondary)" }}>
              Riigivaade ei kogu külastajate isikuandmeid ega kasuta küpsiseid ega analüütikat.
              Brauserisse salvestatakse ainult valitud teema (hele või tume). Veebilehte ja API-t
              vahendavad Vercel ja Cloudflare, kes töötlevad turvalisuse ja töökindluse tagamiseks
              tehnilisi logisid (sh IP-aadressi). Saadikute fotod laaditakse Riigikogu serverist.
            </p>
          </section>

          <section>
            <h2 style={{ fontSize: "1.15rem", marginBottom: "0.5rem" }}>
              Riigikogu liikmete andmed
            </h2>
            <p style={{ margin: 0, color: "var(--text-secondary)" }}>
              Riigivaade avaldab Riigikogu liikmete kohta avalikest allikatest pärit andmeid (nimi,
              foto, fraktsioon, valimisringkond, kõned, hääletused ja kohalolek). Andmeid
              töödeldakse parlamendi töö läbipaistvuse ja avalikkuse teavitamise eesmärgil. Kui
              leiate vea või soovite esitada vastuväite, kirjutage{" "}
              <a
                href={`mailto:${CONTACT_EMAIL}`}
                style={{ color: "var(--accent-primary)", textDecoration: "underline" }}
              >
                {CONTACT_EMAIL}
              </a>
              . Vigased andmed parandatakse.
            </p>
          </section>

          <section>
            <h2 style={{ fontSize: "1.15rem", marginBottom: "0.5rem" }}>
              Andmeallikad ja litsentsid
            </h2>
            <p style={{ margin: 0, color: "var(--text-secondary)" }}>
              Stenogrammid, hääletused, kohalolek ja saadikute andmed: Riigikogu avaandmed
              (api.riigikogu.ee), litsents CC BY-SA 3.0. Saadikute fotod: Riigikogu. Videod:
              Riigikogu YouTube&apos;i kanal, litsents CC BY-SA. Riigivaate töödeldud andmed, sh
              otsingutulemuste eksport, on samuti CC BY-SA litsentsi all.
            </p>
          </section>

          <section>
            <h2 style={{ fontSize: "1.15rem", marginBottom: "0.5rem" }}>Erapooletus</h2>
            <p style={{ margin: 0, color: "var(--text-secondary)" }}>
              Kuidas andmeid arvutatakse, vaata{" "}
              <button
                type="button"
                onClick={onOpenMethodology}
                style={{
                  background: "none",
                  border: "none",
                  color: "var(--accent-primary)",
                  textDecoration: "underline",
                  cursor: "pointer",
                  font: "inherit",
                  padding: 0,
                }}
              >
                metoodikast
              </button>
              .
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}

export default PrivacyView;
