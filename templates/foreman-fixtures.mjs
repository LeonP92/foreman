// Specs import test/expect from here: every page records console errors and responses >= 400,
// and leaves a full-page screenshot in $FOREMAN_OUT.
import path from "node:path";
import { test as base, expect } from "@playwright/test";

const slug = s => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

export const test = base.extend({
  page: async ({ page }, use, testInfo) => {
    const consoleErrors = [], badResponses = [];
    page.on("console", m => { if (m.type() === "error") consoleErrors.push(m.text()); });
    page.on("pageerror", e => consoleErrors.push(String(e)));
    page.on("response", r => { if (r.status() >= 400) badResponses.push(`${r.status()} ${r.url()}`); });
    await use(page);
    const file = path.join(process.env.FOREMAN_OUT, `${slug(testInfo.title)}-${testInfo.project.name}.png`);
    await page.screenshot({ path: file, fullPage: true });
    await testInfo.attach("foreman", {
      body: JSON.stringify({ consoleErrors, badResponses, screenshots: [file] }),
      contentType: "application/json",
    });
  },
});
export { expect };
