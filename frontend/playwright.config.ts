import { defineConfig } from '@playwright/test'

// Starts its own FastAPI (:8100) and Vite (:5180), so it never hits a dev server on 8000/5173.
export default defineConfig({
  testDir: 'e2e',
  use: { baseURL: 'http://localhost:5180' },
  webServer: [
    {
      command: 'uv run fastapi run app/main.py --port 8100',
      cwd: '../backend',
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
