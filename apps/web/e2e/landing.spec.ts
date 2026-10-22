import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("landing loads without requests to another origin", async ({ page }) => {
  const externalRequests: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).origin !== "http://127.0.0.1:4173") {
      externalRequests.push(request.url());
    }
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("See where your API money goes.");
  expect(externalRequests).toEqual([]);
});

test("the primary links point to signup and the demo routes", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("overcall-demo-session", JSON.stringify({ email: "demo@overcall.local" }));
  });
  await page.route("http://localhost:8000/api/**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "{}" }),
  );
  await page.goto("/");

  await page.getByRole("link", { name: "Sign up" }).click();
  await expect(page).toHaveURL(/\/signup$/);
  await page.goto("/");
  await page.getByRole("link", { name: /try the demo/i }).click();
  await expect(page).toHaveURL(/\/app$/);
});

test("FAQ can be opened with the keyboard and the page fits common widths", async ({ page }) => {
  await page.goto("/");
  const summary = page.locator("details summary").first();
  await summary.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("details").first()).toHaveJSProperty("open", true);

  for (const width of [320, 768, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    const hasHorizontalOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    );
    expect(hasHorizontalOverflow).toBe(false);
  }
});

for (const theme of ["light", "dark"]) {
  test(`landing has no axe violations in ${theme} theme`, async ({ page }) => {
    await page.addInitScript((preference) => {
      localStorage.setItem("overcall-theme", preference);
    }, theme);
    await page.goto("/");

    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
    await page.screenshot({ path: `test-results/landing-${theme}.png`, fullPage: true });
  });
}
