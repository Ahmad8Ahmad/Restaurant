/**
 * Global setup/teardown for the 1000-order Playwright load test.
 *
 * Seeds the dev SQLite database with the load-test accounts — 100
 * restaurants, 100 delivery drivers, 100 customers (idempotent via
 * `--purge`) — and makes sure a dev server is reachable on
 * 127.0.0.1:8002, starting one if not, and killing only the process this
 * setup spawned.
 *
 * Uses the project venv so `python` resolves to the same interpreter as the
 * app (C:\Food\venv).
 */
import { execSync, spawn } from "node:child_process";
import net from "node:net";
import path from "node:path";

export const LOAD_BASE = "http://127.0.0.1:8002";
export const ACCOUNTS = Number(process.env.LT_ACCOUNTS || 100); // restaurants / drivers / customers
export const ORDERS = Number(process.env.LT_ORDERS || 1000);
export const ROOT_DIR = path.resolve(__dirname, "..");
const PYTHON = path.join("C:", "Food", "venv", "Scripts", "python.exe");
const SETTINGS = "tamini.settings.dev";
const PORT = 8002;

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
    if (await isPortOpen(PORT)) return true;
    await new Promise((r) => setTimeout(r, 750));
  }
  return false;
}

export default async function globalSetup() {
  const seedCmd = [
    "manage.py",
    "seed_load_test_data",
    `--settings=${SETTINGS}`,
    "--purge",
    "--count",
    String(ACCOUNTS),
  ];
  execSync(`"${PYTHON}" ${seedCmd.join(" ")}`, {
    cwd: ROOT_DIR,
    stdio: "inherit",
  });

  if (!(await isPortOpen(PORT))) {
    spawnedServer = spawn(
      PYTHON,
      [
        "manage.py",
        "runserver",
        `127.0.0.1:${PORT}`,
        `--settings=${SETTINGS}`,
        "--noreload",
      ],
      { cwd: ROOT_DIR, stdio: "ignore" },
    );
    if (!(await waitForServer(180_000))) {
      throw new Error(`Dev server did not start on 127.0.0.1:${PORT}`);
    }
  }
}

async function globalTeardown() {
  if (spawnedServer) {
    spawnedServer.kill();
  }
}

export { globalTeardown };
