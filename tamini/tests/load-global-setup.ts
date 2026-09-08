/**
 * Global setup/teardown for the Playwright load test.
 *
 * Seeds the dev SQLite database with the 100/100/100 load-test accounts
 * (idempotent), and makes sure a dev server is reachable on 127.0.0.1:8001 —
 * starting one if not, and killing only the process this setup spawned.
 *
 * Uses the project venv so `python` resolves to the same interpreter as the
 * app (C:\Food\venv).
 */
import { execSync, spawn } from "node:child_process";
import net from "node:net";
import path from "node:path";

export const LOAD_BASE = "http://127.0.0.1:8001";
export const ROOT_DIR = path.resolve(__dirname, "..");
const PYTHON = path.join("C:", "Food", "venv", "Scripts", "python.exe");
const SETTINGS = "tamini.settings.dev";

let spawnedServer: ReturnType<typeof spawn> | null = null;

function isPortOpen(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const sock = net.connect({ host: "127.0.0.1", port });
    sock.setTimeout(1500);
    sock.on("connect", () => {
      sock.destroy();
      resolve(true);
    });
    sock.on("error", () => resolve(false));
    sock.on("timeout", () => {
      sock.destroy();
      resolve(false);
    });
  });
}

async function waitForServer(ms: number): Promise<boolean> {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    if (await isPortOpen(8001)) return true;
    await new Promise((r) => setTimeout(r, 750));
  }
  return false;
}

export default async function globalSetup() {
  // 1. Reprovision the seed data. --purge wipes the previous run's
  //    load-test users/orders for a deterministic, fresh baseline.
  const seedCmd = [
    "manage.py",
    "seed_load_test_data",
    `--settings=${SETTINGS}`,
    "--purge",
    "--count",
    "100",
  ];
  execSync(`"${PYTHON}" ${seedCmd.join(" ")}`, {
    cwd: ROOT_DIR,
    stdio: "inherit",
  });

  // 2. Make sure the dev server is up.
  if (!(await isPortOpen(8001))) {
    spawnedServer = spawn(
      PYTHON,
      [
        "manage.py",
        "runserver",
        "127.0.0.1:8001",
        `--settings=${SETTINGS}`,
        "--noreload",
      ],
      { cwd: ROOT_DIR, stdio: "ignore" },
    );
    if (!(await waitForServer(120_000))) {
      throw new Error("Dev server did not start on 127.0.0.1:8001");
    }
  }
}

// Teardown runs after the whole suite (or on abort) — only when we started it.
async function globalTeardown() {
  if (spawnedServer) {
    spawnedServer.kill();
  }
}

export { globalTeardown };