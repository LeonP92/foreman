import { test, expect } from "./foreman-fixtures.mjs";

const card = (page, id) => page.locator(`.card[data-id="${id}"]`);
const top = async (page, id) => (await card(page, id).boundingBox()).y;
const opacity = (page, id) => card(page, id).evaluate(el => Number(getComputedStyle(el).opacity));

test("diagram focus pulls neighbours up and fades the rest", async ({ page }) => {
  await page.goto("/diagram.html");
  // checkout lane: cart, order, discounts; refunds links to discounts (last) but not to cart_view.
  const first = await top(page, "cart"), last = await top(page, "discounts");
  await card(page, "refunds").click();
  await expect.poll(() => top(page, "discounts")).toBe(first);
  await expect.poll(() => opacity(page, "cart_view")).toBeLessThanOrEqual(0.2);
  await page.locator("#canvas").click({ position: { x: 5, y: 5 } });
  await expect.poll(() => top(page, "discounts")).toBe(last);
  await expect.poll(() => opacity(page, "cart_view")).toBe(1);
});

test("diagram filter enter focuses the first match", async ({ page }) => {
  await page.goto("/diagram.html");
  await page.locator("#filter").fill("checkout/");
  await page.locator("#filter").press("Enter");
  await expect(card(page, "cart")).toHaveClass(/selected/);
});

test("map enter on a group drills in and focuses the breadcrumb", async ({ page }) => {
  await page.goto("/map.html");
  await page.locator(".card.group", { hasText: "app" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("#crumb-all")).toBeFocused();
});
