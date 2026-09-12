import { defineConfig, devices } from '@playwright/test'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'


const backendPort = 5100
const frontendPort = 4173
const configDirectory = dirname(fileURLToPath(import.meta.url))
const backendDirectory = resolve(configDirectory, '../backend')
const pythonExecutable = resolve(configDirectory, '../.venv/Scripts/python.exe')


export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 2 : 0,
  reporter: [
    ['list'],
    ['html', { open: 'never' }],
  ],
  use: {
    baseURL: `http://127.0.0.1:${frontendPort}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: [
    {
      name: 'e2e-api',
      command: `"${pythonExecutable}" -m scripts.e2e_server`,
      cwd: backendDirectory,
      env: {
        ...process.env,
        E2E_BACKEND_PORT: String(backendPort),
      },
      url: `http://127.0.0.1:${backendPort}/api/health`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      name: 'e2e-web',
      command: `npm run dev -- --host 127.0.0.1 --port ${frontendPort} --strictPort`,
      env: {
        ...process.env,
        VITE_BACKEND_TARGET: `http://127.0.0.1:${backendPort}`,
      },
      url: `http://127.0.0.1:${frontendPort}`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
