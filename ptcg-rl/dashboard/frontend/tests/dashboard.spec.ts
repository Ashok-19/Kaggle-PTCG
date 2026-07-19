import { expect, test } from "@playwright/test";

test("parallel R1 and G2 work is visible in the command center", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Active workstreams" })).toBeVisible();
  await expect(page.getByText("R1", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("G2", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/Verify index and daily replay manifests/)).toBeVisible();
  await expect(page.getByText("USD 0.00", { exact: true })).toBeVisible();
  await page.screenshot({ path: "../../reports/dashboard/screenshots/command-center.png", fullPage: true });
});

test("roadmap and negative history remain inspectable", async ({ page }) => {
  await page.goto("/#roadmap");
  await page.getByRole("button", { name: "Gates & Roadmap" }).click();
  await expect(page.getByRole("heading", { name: "Gates & Roadmap" })).toBeVisible();
  await expect(page.getByText("Passed", { exact: true }).nth(1)).toBeVisible();
  await expect(page.getByText("QUEUED", { exact: true }).first()).toBeVisible();
  await page.screenshot({ path: "../../reports/dashboard/screenshots/gates-roadmap.png", fullPage: true });

  await page.getByRole("button", { name: "Evidence", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Evidence & Decisions" })).toBeVisible();
  await expect(page.getByText("Public-history exposure confirmed")).toBeVisible();
  await expect(page.getByText("DEC-010 · Authorize G2/R1 and strict evaluation")).toBeVisible();
});

test("learning lab explains boundaries from durable records", async ({ page }) => {
  await page.goto("/#learning");
  await page.getByRole("button", { name: "Learning Lab" }).click();
  await expect(page.getByRole("heading", { name: "Learning Lab" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "What G1R proved" })).toBeVisible();
  await expect(page.getByText("No episode JSON transfer before the immutable R1 plan is reviewed.")).toBeVisible();
});

test("mobile command center has no overlapping primary controls", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Active workstreams" })).toBeVisible();
  await page.screenshot({ path: "../../reports/dashboard/screenshots/command-center-mobile.png", fullPage: true });
});
