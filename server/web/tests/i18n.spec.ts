import { expect, test } from "@playwright/test";
import { installMocks } from "./mock";

test("Language toggle switches UI between Chinese (ZH) and English (EN)", async ({ page }) => {
  await installMocks(page);
  await page.goto("/");

  await expect(page.getByRole("button", { name: "图片" })).toBeVisible();
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await expect(page.getByRole("button", { name: "Image" })).toBeVisible();
  await expect(page.getByRole("button", { name: "FaceSwap" })).toBeVisible();

  await page.getByRole("button", { name: "ZH", exact: true }).click();
  await expect(page.getByRole("button", { name: "换脸" })).toBeVisible();
});
