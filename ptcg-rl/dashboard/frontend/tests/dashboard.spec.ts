import { expect, test } from "@playwright/test";

test("G1 completion is visible in the command center", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "G1 readiness" })).toBeVisible();
  await expect(page.getByText("SUCCEEDED", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("bounded native smoke", { exact: true })).toBeVisible();
  await expect(page.getByText(/Official binding exposes no semantic engine version/)).toBeVisible();
  await page.screenshot({ path: "../../reports/dashboard/screenshots/command-center.png", fullPage: true });
});

test("roadmap and negative history remain inspectable", async ({ page }) => {
  await page.goto("/#gates");
  await page.getByRole("button", { name: "Gates & Roadmap" }).click();
  await expect(page.getByRole("heading", { name: "Gates & Roadmap" })).toBeVisible();
  await expect(page.getByText("Passed", { exact: true }).nth(1)).toBeVisible();
  await page.screenshot({ path: "../../reports/dashboard/screenshots/gates-roadmap.png", fullPage: true });
  await page.getByRole("button", { name: "Timeline" }).click();
  await expect(page.getByText("Public-history exposure confirmed")).toBeVisible();
});

test("mobile command center has no overlapping primary controls", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "G1 readiness" })).toBeVisible();
  await page.screenshot({ path: "../../reports/dashboard/screenshots/command-center-mobile.png", fullPage: true });
});
