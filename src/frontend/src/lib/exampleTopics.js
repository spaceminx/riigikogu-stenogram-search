import { serializeGroupsToQuery } from "./queryHelpers.js";

// Example searches on the home page. Each topic is a set of OR blocks, so the search box shows
// what is actually searched; the terms are names of laws and policy areas, not evaluative words.
export const EXAMPLE_TOPICS = [
  { label: "Kaitse", groups: [["kaitsekulud"], ["laskemoon"], ["ajateenistus"], ["kaitseliit"]] },
  {
    label: "Riigieelarve",
    groups: [["riigieelarve"], ["lisaeelarve"], ["riigivõlg"], ["eelarve defitsiit"]],
  },
  { label: "Maksud", groups: [["käibemaks"], ["tulumaks"], ["automaks"], ["maksuküür"]] },
  { label: "Haridus", groups: [["õpetajate palk"], ["eestikeelne haridus"], ["kõrgharidus"]] },
  {
    label: "Energeetika",
    groups: [["tuulepark"], ["tuumajaam"], ["põlevkivi"], ["elektri hind"]],
  },
  { label: "Pensionid", groups: [["pension"], ["pensionisammas"], ["teine sammas"]] },
  { label: "Transport", groups: [["Rail Baltic"], ["ühistransport"], ["Via Baltica"]] },
];

export function getTopicQuery(topic) {
  return serializeGroupsToQuery(topic.groups);
}
