#!/usr/bin/env python3
"""Check that attendance tables fit inside mobile containers at 390 px without horizontal scroll.

Requirement: at 390 px viewport, table.scrollWidth <= container.clientWidth.
Tests both the members table and the factions table using headless Chrome.
"""

import os
import shutil
import subprocess
import sys
import tempfile


def find_chrome():
    if "CHROME_BIN" in os.environ and os.path.exists(os.environ["CHROME_BIN"]):
        return os.environ["CHROME_BIN"]

    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
    ]
    for c in candidates:
        if c.startswith("/") and os.path.exists(c):
            return c
        path = shutil.which(c)
        if path:
            return path
    return None


def generate_test_html(css_content):
    return f"""<!DOCTYPE html>
<html lang="et">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
* {{ box-sizing: border-box; }}
body {{ margin: 0; padding: 0; background: #0f172a; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
.mobile-wrapper {{ width: 100%; max-width: 390px; padding: 16px; margin: 0 auto; }}
.glass-panel {{ padding: 20px; }}
{css_content}
</style>
</head>
<body>
<div class="mobile-wrapper">
  <!-- 1. Members table -->
  <div class="glass-panel" id="panel-members">
    <div class="attendance-list" id="container-members">
      <table class="attendance-table" id="table-members">
        <thead>
          <tr>
            <th scope="col" class="att-col-rank">#</th>
            <th scope="col" class="att-col-name"><button type="button" class="att-sort-btn">Saadik ↓</button></th>
            <th scope="col" class="att-col-faction"><button type="button" class="att-sort-btn">Fraktsioon</button></th>
            <th scope="col" class="att-col-registered"><button type="button" class="att-sort-btn">Registreerus</button></th>
            <th scope="col" class="att-col-votes"><button type="button" class="att-sort-btn">Osales</button></th>
            <th scope="col" class="att-col-combined">
              <div class="att-mobile-header-sorts">
                <button type="button" class="att-sort-btn is-active">Hääletustel ↓</button>
                <span class="att-mobile-sort-sep">·</span>
                <button type="button" class="att-sort-btn">Kontrollides</button>
              </div>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td class="att-col-rank">1</td>
            <td class="att-col-name">
              <a href="#" class="speaker-name-link">Ando Kiviberg</a>
              <div class="att-mobile-faction-badge"><span class="faction-badge">Isamaa</span></div>
            </td>
            <td class="att-col-faction"><span class="faction-badge">Isamaa</span></td>
            <td class="att-col-registered"><div class="att-metric-cell"><span class="att-metric-main">61,9% · 203/328</span></div></td>
            <td class="att-col-votes"><div class="att-metric-cell"><span class="att-metric-main">83,1% · 822/989</span></div></td>
            <td class="att-col-combined">
              <div class="att-mobile-stacked-cell">
                <div class="att-mobile-metric-row">
                  <span class="att-mobile-metric-label">Hääletustel:</span>
                  <span class="att-mobile-metric-val">83,1% · 822/989</span>
                </div>
                <div class="att-mobile-subtext">ei hääletanud 9,0% · puudus 7,9%</div>
                <div class="att-mobile-metric-row">
                  <span class="att-mobile-metric-label">Kontrollides:</span>
                  <span class="att-mobile-metric-val">61,9% · 203/328</span>
                </div>
              </div>
            </td>
          </tr>
          <tr class="att-row-small-sample">
            <td class="att-col-rank">101</td>
            <td class="att-col-name">
              <a href="#" class="speaker-name-link">Väga Pikk Nimi Saadikukandidaat</a>
              <div class="att-mobile-faction-badge"><span class="faction-badge">Sotsiaaldemokraadid</span></div>
            </td>
            <td class="att-col-faction"><span class="faction-badge">Sotsiaaldemokraadid</span></td>
            <td class="att-col-registered"><div class="att-metric-cell"><span class="att-metric-main">100% · 2/2</span></div></td>
            <td class="att-col-votes"><div class="att-metric-cell"><span class="att-metric-main">100% · 4/4</span></div></td>
            <td class="att-col-combined">
              <div class="att-mobile-stacked-cell">
                <div class="att-mobile-metric-row att-metric-small-sample">
                  <span class="att-mobile-metric-label">Hääletustel:</span>
                  <span class="att-mobile-metric-val">100% · 4/4<span class="att-sample-note">vähe andmeid</span></span>
                </div>
                <div class="att-mobile-subtext">ei hääletanud 0% · puudus 0%</div>
                <div class="att-mobile-metric-row att-metric-small-sample">
                  <span class="att-mobile-metric-label">Kontrollides:</span>
                  <span class="att-mobile-metric-val">100% · 2/2<span class="att-sample-note">vähe andmeid</span></span>
                </div>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- 2. Factions table -->
  <div class="glass-panel" id="panel-factions" style="margin-top: 16px;">
    <div class="attendance-list" id="container-factions">
      <table class="attendance-table" id="table-factions">
        <thead>
          <tr>
            <th scope="col" class="att-col-rank">#</th>
            <th scope="col" class="att-col-name"><button type="button" class="att-sort-btn">Fraktsioon ↓</button></th>
            <th scope="col" class="att-col-count"><button type="button" class="att-sort-btn">Saadikuid</button></th>
            <th scope="col" class="att-col-registered"><button type="button" class="att-sort-btn">Registreerus</button></th>
            <th scope="col" class="att-col-votes"><button type="button" class="att-sort-btn">Osales</button></th>
            <th scope="col" class="att-col-combined">
              <div class="att-mobile-header-sorts">
                <button type="button" class="att-sort-btn is-active">Hääletustel ↓</button>
                <span class="att-mobile-sort-sep">·</span>
                <button type="button" class="att-sort-btn">Kontrollides</button>
              </div>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr class="faction-row-interactive">
            <td class="att-col-rank">1</td>
            <td class="att-col-name">
              <button type="button" class="faction-drilldown-btn">
                <span class="faction-title">Eesti Reformierakonna fraktsioon</span>
                <span class="drilldown-hint">Vaata saadikuid →</span>
              </button>
              <div class="att-mobile-faction-badge"><span class="faction-badge">39 saadikut</span></div>
            </td>
            <td class="att-col-count">39</td>
            <td class="att-col-registered"><div class="att-metric-cell"><span class="att-metric-main">82,4% · 1012/1228</span></div></td>
            <td class="att-col-votes"><div class="att-metric-cell"><span class="att-metric-main">88,1% · 3100/3518</span></div></td>
            <td class="att-col-combined">
              <div class="att-mobile-stacked-cell">
                <div class="att-mobile-metric-row">
                  <span class="att-mobile-metric-label">Hääletustel:</span>
                  <span class="att-mobile-metric-val">88,1% · 3100/3518</span>
                </div>
                <div class="att-mobile-subtext">ei hääletanud 5,0% · puudus 6,9%</div>
                <div class="att-mobile-metric-row">
                  <span class="att-mobile-metric-label">Kontrollides:</span>
                  <span class="att-mobile-metric-val">82,4% · 1012/1228</span>
                </div>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</div>

<div id="check-output">PENDING</div>

<script>
window.onload = () => {{
  const cMembers = document.getElementById('container-members');
  const tMembers = document.getElementById('table-members');
  const cFactions = document.getElementById('container-factions');
  const tFactions = document.getElementById('table-factions');

  const membersFit = tMembers.scrollWidth <= cMembers.clientWidth;
  const factionsFit = tFactions.scrollWidth <= cFactions.clientWidth;

  const res = [
    'MEMBERS:' + cMembers.clientWidth + ':' + tMembers.scrollWidth + ':' + membersFit,
    'FACTIONS:' + cFactions.clientWidth + ':' + tFactions.scrollWidth + ':' + factionsFit
  ].join('|');

  document.getElementById('check-output').textContent = 'EVAL:' + res;
}};
</script>
</body>
</html>"""


def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    css_path = os.path.join(repo_root, "src", "frontend", "src", "App.css")
    if not os.path.exists(css_path):
        print(f"Error: App.css not found at {css_path}", file=sys.stderr)
        sys.exit(1)

    with open(css_path, encoding="utf-8") as f:
        css_content = f.read()

    chrome_bin = find_chrome()
    if not chrome_bin:
        print(
            "Warning: Chrome/Chromium binary not found. Skipping live browser check.",
            file=sys.stderr,
        )
        sys.exit(0)

    html_content = generate_test_html(css_content)

    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html_content)
        temp_html = f.name

    try:
        cmd = [
            chrome_bin,
            "--headless=new",
            "--disable-gpu",
            "--window-size=390,844",
            "--dump-dom",
            temp_html,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        eval_line = None
        for line in res.stdout.splitlines():
            if "EVAL:" in line:
                eval_line = line
                break

        if not eval_line:
            print(
                f"Error: Failed to obtain evaluation result from headless Chrome: {res.stderr}",
                file=sys.stderr,
            )
            sys.exit(1)

        # Parse EVAL:MEMBERS:306:306:true|FACTIONS:306:306:true
        eval_data = eval_line[eval_line.index("EVAL:") + 5 :].split("<")[0].strip()
        parts = eval_data.split("|")
        all_passed = True

        for part in parts:
            name, c_width, t_width, fits_str = part.split(":")
            fits = fits_str.lower() == "true"
            label = "Members table" if name == "MEMBERS" else "Factions table"
            if fits:
                print(
                    f"PASS: {label} fits at 390px viewport: scrollWidth ({t_width}px) <= clientWidth ({c_width}px)"
                )
            else:
                print(
                    f"FAIL: {label} overflows at 390px viewport: scrollWidth ({t_width}px) > clientWidth ({c_width}px)",
                    file=sys.stderr,
                )
                all_passed = False

        if not all_passed:
            sys.exit(1)

        print("All attendance tables fit within mobile screens with no horizontal scroll.")
    finally:
        if os.path.exists(temp_html):
            os.remove(temp_html)


if __name__ == "__main__":
    main()
