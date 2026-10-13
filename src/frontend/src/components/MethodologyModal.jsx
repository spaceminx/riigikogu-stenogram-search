import React, { useEffect } from "react";
import { formatDate } from "../lib/calendarUtils";
import { formatSyncTime, isSyncStale } from "../lib/formatters";

export function MethodologyModal({ isOpen, onClose, systemStatus }) {
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal-content glass-panel methodology-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="methodology-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-top-bar">
          <div>
            <h2 id="methodology-modal-title" className="modal-heading">
              Andmed ja metoodika
            </h2>
            <div className="modal-meta-row">
              {systemStatus?.data_as_of && (
                <span>
                  Viimane istung: {formatDate(systemStatus.data_as_of)}
                  {systemStatus.latest_session_status === "UNEDITED"
                    ? " (esialgne stenogramm)"
                    : ""}
                </span>
              )}
              {systemStatus?.last_sync_at && (
                <>
                  <span>•</span>
                  <span>Uuendatud: {formatSyncTime(systemStatus.last_sync_at)}</span>
                </>
              )}
              {typeof systemStatus?.total_sessions === "number" && (
                <>
                  <span>•</span>
                  <span>{systemStatus.total_sessions.toLocaleString("et-EE")} istungit</span>
                </>
              )}
              {typeof systemStatus?.total_speeches === "number" && (
                <>
                  <span>•</span>
                  <span>{systemStatus.total_speeches.toLocaleString("et-EE")} kõnet</span>
                </>
              )}
              {typeof systemStatus?.total_persons === "number" && (
                <>
                  <span>•</span>
                  <span>{systemStatus.total_persons} saadikut</span>
                </>
              )}
            </div>
          </div>
          <button
            type="button"
            className="modal-close-icon-btn"
            onClick={onClose}
            title="Sulge aken (ESC)"
          >
            &times;
          </button>
        </div>

        {(systemStatus?.warning || isSyncStale(systemStatus?.last_sync_at)) && (
          <div className="methodology-warning">
            <strong>Hoiatus:</strong>{" "}
            {systemStatus?.warning || "Automaatne sünkroonimine võib olla peatunud."}
          </div>
        )}

        <div className="methodology-scroll">
          <div className="methodology-section">
            <h3>1. Kohaloleku mõõtmine</h3>
            <p>
              Kohaloleku statistika põhineb Riigikogu täiskogu ametlikel kohalolekukontrollidel.
              Registreeritud kohalolek näitab osalemist kontrollil konkreetsel ajamomendil, mitte
              saadiku pidevat füüsilist viibimist istungisaalis mitmetunnise arutelu kestel. Samuti
              ei kajasta see tööd alatistes komisjonides, fraktsioonides ega kohtumisi valijatega.
            </p>
          </div>

          <div className="methodology-section">
            <h3>2. Kõnede ja sõnavõttude loendamine</h3>
            <p>
              Kõned ja sõnavõtud pärinevad Riigikogu ametlikest stenogrammidest. Istungi juhataja
              ametikoht (Esimees, Aseesimees) on stenogrammis eraldi rollitunnusena talletatud.
            </p>
            <p>
              {systemStatus?.methodology?.speech_types ||
                "Kategooriad põhinevad Riigikogu stenogrammi sõnavõtu liigist; juhatajasõnavõtud tuvastatakse ametinimetuse (Esimees, Aseesimees) järgi, mitte liigi järgi, sest Riigikogu liigitus on selles osas ebajärjekindel."}
            </p>
            <p>
              {systemStatus?.methodology?.duration ||
                "Kõneaeg on arvutatud Riigikogu stenogrammi algus- ja lõpuajast ning on saadaval alates 2021. aastast; 2019–2020 kõnedel puudub algallikas algusaeg."}
            </p>
          </div>

          <div className="methodology-section">
            <h3>3. Toimetamata vs toimetatud stenogrammid</h3>
            <p>
              Vahetult pärast istungit avaldatakse stenogramm toimetamata kujul. Toimetatud ja
              kinnitatud lõpliku stenogrammi valmimisel asendab andmetoru teksti automaatselt
              ametliku redaktsiooniga.
            </p>
          </div>

          <div className="methodology-section">
            <h3>4. Erapooletus ja avaandmete allikad</h3>
            <p>
              Kõik andmed pärinevad ametlikest Riigikogu avaandmetest (
              <a href="https://api.riigikogu.ee" target="_blank" rel="noreferrer">
                api.riigikogu.ee
              </a>{" "}
              ja{" "}
              <a href="https://stenogrammid.riigikogu.ee" target="_blank" rel="noreferrer">
                stenogrammid.riigikogu.ee
              </a>
              ). Otsingumootor on erapooletu tehnoloogiline tööriist ega anna poliitilisi hinnanguid
              ega toeta ühtegi erakonda.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default MethodologyModal;
