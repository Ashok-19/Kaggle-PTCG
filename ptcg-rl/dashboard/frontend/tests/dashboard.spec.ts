import { expect, test } from "@playwright/test";

test("G3a completion and next-gate boundary are visible", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Active workstreams" })).toBeVisible();
  await expect(page.getByText("PASS", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("NO ACTIVE GATE", { exact: true })).toBeVisible();
  await expect(page.getByText("6/10", { exact: true })).toBeVisible();
  await expect(page.getByText(/training remains unauthorized/)).toBeVisible();
  await expect(page.getByText("USD 0.00", { exact: true })).toBeVisible();
  await page.screenshot({ path: "../../reports/dashboard/screenshots/command-center.png", fullPage: true });
});

test("roadmap and negative history remain inspectable", async ({ page }) => {
  await page.goto("/#roadmap");
  await page.getByRole("button", { name: "Gates & Roadmap" }).click();
  await expect(page.getByRole("heading", { name: "Gates & Roadmap" })).toBeVisible();
  const r1Step = page.locator(".roadmap-step").filter({ hasText: "R1" });
  const g2Step = page.locator(".roadmap-step").filter({ hasText: "G2" });
  const g3aStep = page.locator(".roadmap-step").filter({ hasText: "G3a" });
  const g3bStep = page.locator(".roadmap-step").filter({ hasText: "G3b" });
  await expect(r1Step.getByText("Passed", { exact: true })).toBeVisible();
  await expect(g2Step.getByText("Passed", { exact: true })).toBeVisible();
  await expect(g3aStep.getByText("Passed", { exact: true })).toBeVisible();
  await expect(g3bStep.getByText("Not started", { exact: true })).toBeVisible();
  await page.screenshot({ path: "../../reports/dashboard/screenshots/gates-roadmap.png", fullPage: true });

  await page.getByRole("button", { name: "Evidence", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Evidence & Decisions" })).toBeVisible();
  await expect(page.getByText("Displayed replay list mismatch contained before transfer")).toBeVisible();
  await expect(page.getByText("DEC-010 · Authorize G2/R1 and strict evaluation")).toBeVisible();
});

test("learning lab explains boundaries and provides interactive simulators", async ({ page }) => {
  await page.goto("/#learning");
  await page.getByRole("button", { name: "Learning Lab" }).click();
  await expect(page.getByRole("heading", { name: "Learning Lab" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Turn and prize-race planner" })).toBeVisible();
  await expect(page.getByText("Projected winner")).toBeVisible();

  await page.getByRole("tab", { name: "Damage math" }).click();
  await expect(page.getByRole("heading", { name: "Damage and knockout sandbox" })).toBeVisible();
  await expect(page.getByText("Remaining HP", { exact: true })).toBeVisible();

  await page.getByRole("tab", { name: "Deck odds" }).click();
  await expect(page.getByRole("heading", { name: "Opening consistency calculator" })).toBeVisible();
  await expect(page.getByText("See at least one")).toBeVisible();

  await page.getByRole("tab", { name: "Agent choices" }).click();
  await expect(page.getByRole("heading", { name: "Legal-option and multi-select lab" })).toBeVisible();
  await expect(page.getByRole("button", { name: /STOP/ })).toBeDisabled();
  await page.getByRole("button", { name: "Bench slot A" }).click();
  await expect(page.getByRole("button", { name: /STOP/ })).toBeEnabled();

  await expect(page.getByRole("heading", { name: "What G1R proved" })).toBeVisible();
  await expect(page.getByText("No PPO training before G2 and evaluation implementation review.")).toBeVisible();
  await page.screenshot({ path: "../../reports/dashboard/screenshots/learning-lab.png", fullPage: true });
});

test("mobile command center has no overlapping primary controls", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Active workstreams" })).toBeVisible();
  await page.screenshot({ path: "../../reports/dashboard/screenshots/command-center-mobile.png", fullPage: true });
});
