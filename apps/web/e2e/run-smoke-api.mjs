import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";


const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(webRoot, "..", "..");
const apiRoot = path.join(repoRoot, "apps", "api");
const smokeDatabaseUrl = "sqlite:///./data/joby_smoke.db";
const apiPort = process.env.SMOKE_API_PORT || "18000";
const webOrigin = process.env.SMOKE_WEB_ORIGIN || "http://127.0.0.1:13000";


function resolvePython() {
  if (process.env.JOBY_PYTHON) {
    return process.env.JOBY_PYTHON;
  }

  const candidates = [
    path.join(repoRoot, ".venv", "Scripts", "python.exe"),
    path.join(repoRoot, ".venv", "bin", "python"),
    "python",
  ];

  for (const candidate of candidates) {
    if (candidate === "python" || existsSync(candidate)) {
      return candidate;
    }
  }

  throw new Error("No Python executable found for smoke API startup.");
}


function runOnce(command, args, options) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { ...options, stdio: "inherit" });
    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) {
        resolve();
        return;
      }
      reject(new Error(`Command failed with exit code ${code}`));
    });
  });
}


const python = resolvePython();
const env = {
  ...process.env,
  DATABASE_URL: process.env.DATABASE_URL || smokeDatabaseUrl,
  CORS_ORIGINS: `${webOrigin},http://localhost:13000`,
};

await runOnce(
  python,
  [path.join(repoRoot, "scripts", "seed_smoke_data.py")],
  { cwd: apiRoot, env },
);

const server = spawn(
  python,
  ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", apiPort],
  { cwd: apiRoot, env, stdio: "inherit" },
);

const shutdown = (signal) => {
  if (!server.killed) {
    server.kill(signal);
  }
};

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));

server.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});