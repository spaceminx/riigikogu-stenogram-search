import fs from "node:fs";
import path from "node:path";
import { execSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const rootDir = path.resolve(__dirname, "..");

// 1. Get previous commit's App.css or current src/App.css
let originalCss = "";
try {
  originalCss = execSync("git show HEAD:src/frontend/src/App.css", {
    encoding: "utf8",
  });
} catch {
  // If not in git HEAD, read from working directory if it existed
  const appCssPath = path.join(rootDir, "src/App.css");
  if (fs.existsSync(appCssPath)) {
    originalCss = fs.readFileSync(appCssPath, "utf8");
  } else {
    console.error("Could not find original App.css from HEAD or filesystem.");
    process.exit(1);
  }
}

// 2. Read import order from src/styles/index.css
const indexCssPath = path.join(rootDir, "src/styles/index.css");
if (!fs.existsSync(indexCssPath)) {
  console.error("src/styles/index.css not found.");
  process.exit(1);
}

const indexContent = fs.readFileSync(indexCssPath, "utf8");
const importLines = indexContent
  .split("\n")
  .map((l) => l.trim())
  .filter((l) => l.startsWith("@import"));

const importedFiles = importLines.map((l) => {
  const match = l.match(/@import\s+["']\.\/([^"']+)["'];/);
  if (!match) {
    console.error(`Invalid import syntax in index.css: ${l}`);
    process.exit(1);
  }
  return match[1];
});

// 3. Concatenate all imported files in order
let concatenated = "";
for (const file of importedFiles) {
  const filePath = path.join(rootDir, "src/styles", file);
  if (!fs.existsSync(filePath)) {
    console.error(`Imported file not found: ${filePath}`);
    process.exit(1);
  }
  const chunk = fs.readFileSync(filePath, "utf8");
  if (concatenated.length > 0) concatenated += "\n";
  concatenated += chunk;
}

// 4. Compare byte-for-byte (ignoring trailing newlines)
const trimmedOriginal = originalCss.replace(/\r?\n+$/, "");
const trimmedConcat = concatenated.replace(/\r?\n+$/, "");

if (trimmedOriginal === trimmedConcat) {
  console.log(
    "CSS split verification PASSED: concatenated styles match original App.css byte-for-byte."
  );
  console.log(
    `Original: ${trimmedOriginal.length} bytes, Concatenated: ${trimmedConcat.length} bytes across ${importedFiles.length} files.`
  );
  process.exit(0);
} else {
  console.error(
    "CSS split verification FAILED: concatenated styles do not match original App.css."
  );
  console.error(
    `Original: ${trimmedOriginal.length} bytes, Concatenated: ${trimmedConcat.length} bytes.`
  );
  process.exit(1);
}
