import { test, expect } from "./foreman-fixtures.mjs";

test("total shows 3", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#total")).toHaveText("3", { timeout: 1000 });
});
