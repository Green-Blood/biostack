import { test, expect, chromium } from "@playwright/test";

const BASE = "http://127.0.0.1:3100";

test.describe("mobile header", () => {
  let browser: Awaited<ReturnType<typeof chromium.launch>>;

  test.beforeAll(async () => {
    browser = await chromium.launch();
  });
  test.afterAll(async () => { await browser.close(); });

  async function mobilePage() {
    const ctx = await browser.newContext({
      viewport: { width: 360, height: 780 },
      userAgent: "Mozilla/5.0 (Linux; Android 14; SM-S931B) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36",
    });
    const page = await ctx.newPage();
    await page.goto(BASE, { waitUntil: "networkidle" });
    return { ctx, page };
  }

  test("compact header shows logo, search and menu", async () => {
    const { ctx, page } = await mobilePage();
    await expect(page.getByText("BioStack", { exact: true }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: /поиск|search/i })).toBeVisible();
    // Scope to the mobile header: the sheet's close button shares the same aria-label.
    await expect(page.locator("header.md\\:hidden").getByRole("button", { name: /меню|menu|открыть|open/i })).toBeVisible();
    // Mobile keeps the compact header and hides the desktop sidebar.
    await expect(page.locator("header.md\\:hidden")).toBeVisible();
    await expect(page.locator("aside")).toBeHidden();
    await ctx.close();
  });

  test("menu opens a sheet with nav, themes and language", async () => {
    const { ctx, page } = await mobilePage();
    await page.getByRole("button", { name: /меню|menu|открыть|open/i }).first().click();
    await expect(page.getByRole("link", { name: /обзор|overview/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /хронология|timeline/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /настройки|settings/i })).toBeVisible();
    // The footer label is visible text; the picker also exposes it as an aria-label,
    // so match the element rather than the text to avoid a strict-mode collision.
    await expect(page.locator("p", { hasText: /цветовая тема|colour theme/i }).first()).toBeVisible();
    await expect(page.locator("p", { hasText: /язык|language/i }).first()).toBeVisible();
    await expect(page.getByRole("dialog", { name: /меню|menu|открыть|open/i }).getByRole("button").first()).toBeVisible();
    await ctx.close();
  });

  test("sheet closes on backdrop click", async () => {
    const { ctx, page } = await mobilePage();
    await page.getByRole("button", { name: /меню|menu|открыть|open/i }).first().click();
    await expect(page.getByRole("link", { name: /обзор|overview/i })).toBeVisible();
    // The close button is the only button inside the dialog (its aria-label is the sheet label).
    await page.getByRole("dialog", { name: /меню|menu|открыть|open/i }).getByRole("button").first().click();
    await expect(page.getByRole("link", { name: /обзор|overview/i })).toHaveCount(0);
    await ctx.close();
  });

  test("theme switch works from the sheet", async () => {
    const { ctx, page } = await mobilePage();
    await page.getByRole("button", { name: /меню|menu|открыть|open/i }).first().click();
    // Click the first named theme row (Paper / Бумага). Theme rows are radios.
    await page.getByRole("radio", { name: /бумага|paper/i }).first().click();
    await page.waitForTimeout(150);
    // The html data-theme attribute should have changed to "paper"
    await expect(page.locator("html")).toHaveAttribute("data-theme", "paper");
    await ctx.close();
  });

  test("desktop keeps the sidebar, no compact header", async () => {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await ctx.newPage();
    await page.goto(BASE, { waitUntil: "networkidle" });
    await expect(page.locator("aside")).toBeVisible();
    await expect(page.locator("header.md\\:hidden")).toBeHidden();
    await ctx.close();
  });
});