import { defineConfig } from '@playwright/test'

// Starts its own FastAPI (:8100) and Vite (:5180), so it never hits a dev server on 8000/5173.
export default defineConfig({
  testDir: 'e2e',
  // One backend process serves the whole run and the mock findings/reviews live in its memory,
  // so spec files must not race each other over that state.
  workers: 1,
  use: { baseURL: 'http://localhost:5180' },
  webServer: [
    {
      command: 'uv run fastapi run app/main.py --port 8100',
      cwd: '../backend',
      // The webhook POSTs back into this same server, so the tickets reach the mock inbox.
      env: { WEBHOOK_URL: 'http://localhost:8100/api/mock/ticketing' },
      url: 'http://localhost:8100/api/health',
      timeout: 120_000,
    },
    {
      command: 'npx vite --port 5180 --strictPort',
      env: { VITE_PROXY_TARGET: 'http://localhost:8100' },
      url: 'http://localhost:5180',
    },
  ],
})
