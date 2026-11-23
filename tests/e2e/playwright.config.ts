import { defineConfig, type Project } from "@playwright/test";

const size = { width: 1920, height: 1080 };
// The hosted demo. `npm run azure` targets it when BASE_URL is not set (npm passes the script
// name to the run and its workers in npm_lifecycle_event).
const AZURE_URL = "https://oxaneworkbench.livelypond-56376142.eastus2.azurecontainerapps.io";
const baseURL =
  process.env.BASE_URL ?? (process.env.npm_lifecycle_event === "azure" ? AZURE_URL : "http://localhost:5180");

// The hosted app shares one database with everyone using it, and replays recorded AI with no
// test model. Specs that reset the scripted case, drive its session events directly or need the
// test model stay local; deals.spec.ts skips its reset-based test there itself, and its model
// tests skip on replay. azure-gaps.spec.ts is its own long live-AI run, started separately.
const LOCAL_ONLY = /(fallback|screens|flow|drills|azure-gaps)\.spec/;
const hosted = /^https:\/\//.test(baseURL) && !/localhost|127\.0\.0\.1/.test(baseURL);

// Only defined when BASE_URL names a hosted app, so a plain local run can never reach Azure.
// Traces are off there because some specs type the access code, which a trace would keep.
const azure: Project[] = hosted
  ? [{ name: "azure", testIgnore: LOCAL_ONLY, retries: 1, use: { trace: "off" } }]
  : [];

export default defineConfig({
  testDir: "./specs",
  // Every test shares one server-side case, so they must run one at a time.
  workers: 1,
  fullyParallel: false,
  timeout: 60_000,
  outputDir: "./test-results",
  reporter: [["list"]],
  expect: { timeout: 15_000, toHaveScreenshot: { maxDiffPixelRatio: 0.01, animations: "disabled" } },
  use: {
    baseURL,
    viewport: size,
    trace: "retain-on-failure",
  },
  projects: [
    { name: "stage", testIgnore: /fallback\.spec/ },
    {
      name: "fallback",
      testMatch: /fallback\.spec/,
      use: { video: { mode: "on", size }, launchOptions: { slowMo: 120 } },
    },
    ...azure,
  ],
});
