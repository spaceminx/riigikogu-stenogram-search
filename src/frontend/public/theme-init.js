// Applies a stored dark theme before the first paint; App.jsx takes over once React has loaded.
// A plain file, not inline, because the CSP allows scripts only from this site.
try {
  var savedTheme = localStorage.getItem("theme");
  if (savedTheme === "light" || savedTheme === "dark") {
    document.documentElement.dataset.theme = savedTheme;
  }
} catch {
  // localStorage may be unavailable in private browsing; the light default applies
}
