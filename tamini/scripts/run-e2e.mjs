// Runs each Playwright spec file in its own browser process.
//
// WHY: this dev machine has ~3.8 GB RAM. A single long-running Chromium
// process accumulates pages and intermittently OOMs/crashes mid-suite, while
// each file is stable in its own fresh browser. We also kill orphaned
// Playwright Chromium processes before the run and retry failed files once
// (fresh browser) since memory pressure is transient.
//
// Usage: node scripts/run-e2e.mjs
import { spawnSync } from "node:child_process";
import { readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(fileURLToPath(new URL(".", import.meta.url)), "..");
const testsDir = join(root, "tests");
const specs = readdirSync(testsDir)
  .filter((f) => f.endsWith(".spec.ts"))
  .sort();

const MAX_FILE_RETRIES = 1;
const delay = (ms) => new Promise((r) => setTimeout(r, ms));

// Kill orphaned headless Chromium processes from earlier crashed runs so they
// stop holding RAM. Only targets the Playwright-bundled browser binaries.
function killOrphanBrowsers() {
  if (process.platform !== "win32") return;
  const likelyPaths = [
    "ms-playwright",
    "playwright",
    "headless_shell",
    "chromium",
  ];
  try {
    const res = spawnSync(
      "powershell",
      [
        "-NoProfile",
        "-Command",
        "Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -match 'ms-playwright|headless_shell' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }",
      ],
      { encoding: "utf8" },
    );
    if (res.stderr) process.stdout.write(`[cleanup] ${res.stderr}`);
  } catch (e) {
    // ignore
  }
}

function runFile(spec) {
  const specPath = join("tests", spec).replace(/\\/g, "/");
  return spawnSync(
    "npx",
    [
      "playwright",
      "test",
      specPath,
      "--reporter=list",
      "--workers=1",
      "--timeout=120000",
    ],
    { stdio: "inherit", shell: true, cwd: root },
  );
}

killOrphanBrowsers();

let failed = [];
for (const spec of specs) {
  process.stdout.write(`\n=== Running ${spec} ===\n`);
  let res = runFile(spec);
  let attempts = 1;

  while (res.status !== 0 && attempts <= MAX_FILE_RETRIES) {
    process.stdout.write(`\n--- ${spec} failed (exit ${res.status}), retrying... ---\n`);
    killOrphanBrowsers();
    await delay(5000);
    res = runFile(spec);
    attempts += 1;
  }

  if (res.status !== 0) failed.push(spec);
}

process.stdout.write(`\n===== E2E summary =====\n`);
if (failed.length === 0) {
  process.stdout.write("All spec files passed.\n");
} else {
  process.stdout.write(`FAILED files: ${failed.join(", ")}\n`);
}
process.exit(failed.length ? 1 : 0);