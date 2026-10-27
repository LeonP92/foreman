import { defineConfig } from "@playwright/test";

const env = process.env;

export default defineConfig({
  testDir: ".",
  testMatch: /\.m?[jt]s$/,
  testIgnore: ["playwright.config.mjs", "foreman-fixtures.mjs"],
  // Relative to this file (the run dir), which is deleted; the default resolves to the cache root.
  outputDir: "test-results",
  workers: 1,
  globalTimeout: 10 * 60_000,
  reporter: [["json", { outputFile: `${env.FOREMAN_OUT}/results.json` }]],
  projects: env.FOREMAN_BRANCH_URL
    ? [
        { name: "base", use: { baseURL: env.FOREMAN_BASE_URL } },
        { name: "branch", use: { baseURL: env.FOREMAN_BRANCH_URL } },
      ]
    : [{ name: "app", use: { baseURL: env.FOREMAN_BASE_URL } }],
});
