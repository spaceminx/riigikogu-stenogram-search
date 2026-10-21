import React, { useState, useRef, useEffect } from "react";
import { Play, ExternalLink } from "lucide-react";
import { parseVideoUrl, buildEmbedUrl } from "../lib/video";

/**
 * Click-to-load video embed for YouTube recordings.
 *
 * Requirements:
 * - Before click: Neutral 16:9 placeholder (no YouTube thumbnails, no Google requests)
 * - After click: Responsive 16:9 iframe loading from youtube-nocookie.com
 * - Shows note: "Video laaditakse YouTube'ist (youtube-nocookie.com) alles pärast klõpsu."
 * - Focus is passed to the iframe once loaded.
 */
export function VideoEmbed({
  videoUrl,
  durationSeconds = null,
  speaker = "",
  date = "",
  showExternalLink = true,
  autoLoad = false,
  className = "",
}) {
  const [isLoaded, setIsLoaded] = useState(autoLoad);
  const iframeRef = useRef(null);

  const videoMeta = parseVideoUrl(videoUrl);

  useEffect(() => {
    if (isLoaded && iframeRef.current) {
      iframeRef.current.focus();
    }
  }, [isLoaded]);

  if (!videoMeta) {
    return null;
  }

  const { videoId, start } = videoMeta;
  const end =
    typeof durationSeconds === "number" && durationSeconds > 0 ? start + durationSeconds : null;

  const embedUrl = isLoaded ? buildEmbedUrl({ videoId, start, end }) : null;
  const iframeTitle = `Riigikogu istungi video: ${speaker || "sõnavõtt"}${date ? `, ${date}` : ""}`;

  return (
    <div className={`video-embed-container ${className}`}>
      <div className="video-embed-aspect">
        {!isLoaded ? (
          <div className="video-embed-placeholder">
            <button
              type="button"
              className="video-embed-play-btn"
              onClick={() => setIsLoaded(true)}
              aria-label={`Vaata videot: ${speaker || "sõnavõtt"}`}
            >
              <span className="video-embed-play-icon" aria-hidden="true">
                <Play size={24} fill="currentColor" />
              </span>
              <span className="video-embed-play-text">Vaata videot</span>
            </button>
            <p className="video-embed-privacy-note">
              Video laaditakse YouTube'ist (youtube-nocookie.com) alles pärast klõpsu.
            </p>
          </div>
        ) : (
          <iframe
            ref={iframeRef}
            src={embedUrl}
            title={iframeTitle}
            className="video-embed-iframe"
            allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
            referrerPolicy="strict-origin-when-cross-origin"
            loading="lazy"
            tabIndex={0}
          />
        )}
      </div>

      {showExternalLink && videoUrl && (
        <div className="video-embed-actions">
          <a
            href={videoUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="speech-video-link"
            title="Vaata kõnet YouTube'is alates selle algusest"
          >
            <span>Vaata YouTube'is</span>
            <ExternalLink size={13} aria-hidden="true" />
          </a>
        </div>
      )}
    </div>
  );
}

export default VideoEmbed;
