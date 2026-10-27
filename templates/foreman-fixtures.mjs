// Specs import test/expect from here: every page records console errors and responses >= 400,
// and leaves a full-page screenshot in $FOREMAN_OUT.
import fs from "node:fs";
import path from "node:path";
import { test as base, expect } from "@playwright/test";

const slug = s => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

// Claims live in the run dir (the cwd), so a title whose slug repeats gets -2, -3, ... even across
// worker restarts, without being fooled by screenshots an earlier run left in $FOREMAN_OUT.
function screenshotName(title, project) {
  fs.mkdirSync("claims", { recursive: true });
  for (let n = 1; ; n++) {
    const name = n === 1 ? `${slug(title)}-${project}` : `${slug(title)}-${n}-${project}`;
    try {
      fs.mkdirSync(path.join("claims", name));
      return `${name}.png`;
    } catch (e) {
      if (e.code !== "EEXIST") throw e;
    }
  }
}

export const test = base.extend({
  page: async ({ page }, use, testInfo) => {
    const consoleErrors = [], badResponses = [];
    page.on("console", m => { if (m.type() === "error") consoleErrors.push(m.text()); });
    page.on("pageerror", e => consoleErrors.push(String(e)));
    page.on("response", r => { if (r.status() >= 400) badResponses.push(`${r.status()} ${r.url()}`); });
    await use(page);
    // Evidence first: a crashed or closed page must not lose it.
    await testInfo.attach("foreman", {
      body: JSON.stringify({ consoleErrors, badResponses }),
      contentType: "application/json",
    });
    const file = path.join(process.env.FOREMAN_OUT, screenshotName(testInfo.title, testInfo.project.name));
    try {
      await page.screenshot({ path: file, fullPage: true });
    } catch {
      return;  // no screenshot from a dead page; the evidence above is kept
    }
    await testInfo.attach("foreman-screenshot", { body: JSON.stringify(file), contentType: "application/json" });
  },
});
export { expect };
