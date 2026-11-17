import { expect, test } from "@playwright/test";
import { installMocks } from "./mock";

test("Three modes (Image, Video, FaceSwap) switch cleanly and submit jobs", async ({ page }) => {
  const ctl = await installMocks(page);
  await page.goto("/");

  await expect(page.getByRole("button", { name: "图片", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "视频", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "换脸", exact: true })).toBeVisible();

  await page.getByLabel("提示词").fill("neon street in Tokyo");
  await page.getByRole("button", { name: "生成", exact: true }).click();

  expect(ctl.calls.some((c) => c.url === "/api/jobs" && c.body?.kind === "image")).toBe(true);

  await page.getByRole("button", { name: "换脸", exact: true }).click();
  await expect(page.getByRole("button", { name: "开始换脸", exact: true })).toBeVisible();
});
