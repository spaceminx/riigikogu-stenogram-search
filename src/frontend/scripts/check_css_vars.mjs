import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const rootDir = path.resolve(__dirname, "..");
const srcDir = path.join(rootDir, "src");

// 1. Gather all CSS, JSX, and JS files under src/
const allFiles = [];
function walk(dir) {
  for (const entry of fs.readdirSync(dir)) {
    const fullPath = path.join(dir, entry);
    if (fs.statSync(fullPath).isDirectory()) {
      walk(fullPath);
    } else if (fullPath.endsWith(".css") || fullPath.endsWith(".jsx") || fullPath.endsWith(".js")) {
      allFiles.push(fullPath);
    }
  }
}
walk(srcDir);

// 2. Extract all defined CSS custom properties from CSS files
const definedVars = new Set();
for (const file of allFiles) {
  if (file.endsWith(".css")) {
    const content = fs.readFileSync(file, "utf8");
    for (const match of content.matchAll(/--([a-zA-Z0-9_-]+)\s*:/g)) {
      definedVars.add(`--${match[1]}`);
    }
  }
}

// 3. Scan for any var(--...) usages that are not in definedVars
const undefinedUses = [];
for (const file of allFiles) {
  const content = fs.readFileSync(file, "utf8");
  const lines = content.split("\n");
  lines.forEach((line, index) => {
    for (const match of line.matchAll(/var\(\s*(--[a-zA-Z0-9_-]+)/g)) {
      const varName = match[1];
      if (!definedVars.has(varName)) {
        undefinedUses.push({
          file: path.relative(rootDir, file),
          line: index + 1,
          varName,
          snippet: line.trim(),
        });
      }
    }
  });
}

// 4. Report results
if (undefinedUses.length > 0) {
  console.error(`Found ${undefinedUses.length} usage(s) of undefined CSS variable(s):`);
  undefinedUses.forEach((u) => {
    console.error(`  ${u.file}:${u.line} uses ${u.varName} -> "${u.snippet}"`);
  });
  process.exit(1);
} else {
  console.log(
    `CSS variable check passed: all var(--...) references are defined (scanned ${allFiles.length} files).`
  );
  process.exit(0);
}
