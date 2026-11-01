import { defineConfig } from "@playwright/test";

const size = { width: 1920, height: 1080 };

export default defineConfig({
  testDir: "./specs",
  // Every test shares one server-side case, so they must run one at a time.
  workers: 1,
  fullyParallel: false,
  timeout: 60_000,
  outputDir: "./test-results",
  reporter: [["list"]],
  expect: { toHaveScreenshot: { maxDiffPixelRatio: 0.01, animations: "disabled" } },
  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:5180",
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
  ],
});
