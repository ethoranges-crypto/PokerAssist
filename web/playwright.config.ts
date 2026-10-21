import { defineConfig } from "@playwright/test";
import os from "node:os";
import path from "node:path";

const API_PORT = 8765;
const WEB_PORT = 3100;
const db = path.join(os.tmpdir(), `pokerassist-e2e-${Date.now()}.sqlite3`);

export default defineConfig({
  testDir: "tests",
  timeout: 60_000,
  use: { baseURL: `http://127.0.0.1:${WEB_PORT}`, colorScheme: "dark" },
  webServer: [
    {
      // Backend without the LLM: explanations come from the engine.
      command: `python3 -m uvicorn app.main:app --port ${API_PORT}`,
      cwd: "..",
      env: { POKERASSIST_DB: db, POKERASSIST_DISABLE_LLM: "1" },
      url: `http://127.0.0.1:${API_PORT}/api/health`,
      timeout: 60_000,
    },
    {
      command: `npx next dev -p ${WEB_PORT}`,
      env: { POKERASSIST_API: `http://127.0.0.1:${API_PORT}` },
      url: `http://127.0.0.1:${WEB_PORT}`,
      timeout: 120_000,
    },
  ],
});
