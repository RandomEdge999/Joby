import { expect, test } from "@playwright/test";


test("fresh user can filter, inspect, and save a job locally", async ({ page }) => {
  await page.goto("/jobs");

  await expect(page.getByRole("heading", { name: "Find roles worth applying to" })).toBeVisible();
  await expect(page.getByText("2 matching jobs")).toBeVisible();

  const searchInput = page.getByPlaceholder("AI engineer, data analyst, backend intern");
  await searchInput.fill("machine learning");

  await expect(page.getByText("1 matching job")).toBeVisible();
  await expect(page.getByText("Platform Machine Learning Engineer")).toBeVisible();
  await expect(page.getByText("Finance Operations Analyst")).toHaveCount(0);

  await page.getByText("Platform Machine Learning Engineer").click();

  const detail = page.getByRole("dialog", { name: "Platform Machine Learning Engineer" });
  await expect(detail).toBeVisible();
  await expect(detail.getByRole("heading", { name: "Platform Machine Learning Engineer" })).toBeVisible();
  await expect(detail.getByText("Open posting")).toBeVisible();

  await detail.getByRole("button", { name: "Save" }).click();

  await expect(detail.getByText("Application status: Saved.")).toBeVisible();

  await page.goto("/applications");

  await expect(page.getByRole("heading", { name: "Applications" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Platform Machine Learning Engineer" })).toBeVisible();
});