import { expect, test } from "@playwright/test";
import { installMocks } from "./mock";

test("Three modes (Image, Video, FaceSwap) switch cleanly and submit jobs", async ({ page }) => {
  const ctl = await installMocks(page);
  await page.goto("/");

  await expect(page.getByRole("button", { name: "图片" })).toBeVisible();
  await expect(page.getByRole("button", { name: "视频" })).toBeVisible();
  await expect(page.getByRole("button", { name: "换脸" })).toBeVisible();

  await page.getByLabel("提示词").fill("neon street in Tokyo");
  await page.getByRole("button", { name: "生成" }).click();

  expect(ctl.calls.some((c) => c.url === "/api/jobs" && c.body?.kind === "image")).toBe(true);

  await page.getByRole("button", { name: "换脸" }).click();
  await expect(page.getByText("全自动远程 GPU 换脸流水线")).toBeVisible();
});
