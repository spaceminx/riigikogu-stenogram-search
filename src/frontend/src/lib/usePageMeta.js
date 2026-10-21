import { useEffect } from "react";

const DEFAULT_TITLE = "Riigivaade — Riigikogu kõned, hääletused ja kohalolek";
const DEFAULT_DESCRIPTION =
  "Riigikogu stenogrammid, kõned, hääletused ja kohalolekukontrollid ühes otsitavas vaates.";

/**
 * Update document.title, <meta name="description">, and optional robots meta with cleanup on unmount.
 *
 * @param {string} [title] - Full page title (e.g. "<page> — Riigivaade")
 * @param {string} [description] - Factual Estonian description sentence
 * @param {Object} [options]
 * @param {boolean} [options.noindex] - If true, adds/sets <meta name="robots" content="noindex">
 */
export function usePageMeta(title, description, options = {}) {
  const noindex = Boolean(options?.noindex);

  useEffect(() => {
    const prevTitle = document.title;
    if (title) {
      document.title = title;
    }

    let descTag = document.querySelector('meta[name="description"]');
    const createdDescTag = !descTag;
    if (!descTag) {
      descTag = document.createElement("meta");
      descTag.name = "description";
      document.head.appendChild(descTag);
    }
    const prevDesc = descTag.getAttribute("content") || DEFAULT_DESCRIPTION;

    if (description) {
      descTag.setAttribute("content", description);
    }

    let robotsTag = document.querySelector('meta[name="robots"]');
    const createdRobotsTag = !robotsTag && noindex;
    const prevRobots = robotsTag ? robotsTag.getAttribute("content") : null;

    if (noindex) {
      if (!robotsTag) {
        robotsTag = document.createElement("meta");
        robotsTag.name = "robots";
        document.head.appendChild(robotsTag);
      }
      robotsTag.setAttribute("content", "noindex");
    }

    return () => {
      document.title = prevTitle || DEFAULT_TITLE;
      if (createdDescTag && descTag.parentNode) {
        descTag.parentNode.removeChild(descTag);
      } else if (descTag) {
        descTag.setAttribute("content", prevDesc);
      }

      if (noindex) {
        if (createdRobotsTag && robotsTag && robotsTag.parentNode) {
          robotsTag.parentNode.removeChild(robotsTag);
        } else if (robotsTag) {
          if (prevRobots) {
            robotsTag.setAttribute("content", prevRobots);
          } else if (robotsTag.parentNode) {
            robotsTag.parentNode.removeChild(robotsTag);
          }
        }
      }
    };
  }, [title, description, noindex]);
}
