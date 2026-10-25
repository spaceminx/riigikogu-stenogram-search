// SVG attributes cannot read CSS variables, so charts use the token values from styles/tokens.css
export const CHART_COLORS = {
  light: {
    surface: "#ffffff",
    text: "#1c1f26",
    muted: "#5e6472",
    border: "#dadce2",
    accent: "#2e3f78",
    series: ["#2e3f78", "#8796cf", "#8b919d", "#c4c8d0"],
  },
  dark: {
    surface: "#1b1e25",
    text: "#e9eaee",
    muted: "#a4a9b5",
    border: "#2d313b",
    accent: "#93a5e8",
    series: ["#93a5e8", "#4e60a8", "#a4a9b5", "#6b7080"],
  },
};

export function chartColors(theme) {
  return CHART_COLORS[theme === "dark" ? "dark" : "light"];
}
