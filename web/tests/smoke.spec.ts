import { expect, test } from "@playwright/test";

test("enter a full cash hand street by street and analyse it", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("seat-BTN")).toContainText("★"); // default hero: BTN, 6-max

  let clicks = 0;
  const click = async (id: string) => {
    clicks++;
    await page.getByTestId(id).click();
  };
  const t0 = Date.now();

  // Preflop: AhKd, folded to hero who opens 2.5x; SB folds, BB calls.
  await click("card-Ah");
  await click("card-Kd");
  await expect(page.getByTestId("card-Ah")).toBeDisabled(); // used cards grey out
  await click("fold-to-hero");
  await expect(page.getByTestId("hero-to-act")).toBeVisible();
  await click("act-raise"); // default size 2.5x = 250
  await click("act-fold"); // SB
  await click("act-call"); // BB
  // Flop Kh7c2d, BB checks to hero.
  await click("street-flop");
  await click("card-Kh");
  await click("card-7c");
  await click("card-2d");
  await click("act-call"); // BB check
  await expect(page.getByTestId("hero-to-act")).toBeVisible();
  await expect(page.getByTestId("pot")).toContainText("Pot 550");
  await click("analyze");
  const entryMs = Date.now() - t0;

  const result = page.getByTestId("result");
  await expect(result).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("result-action")).toHaveText(/^(Bet|Check)/);
  await expect(page.getByTestId("confidence")).toHaveText(/high|medium|low/);
  await expect(page.getByTestId("range-grid").locator("div")).toHaveCount(169);
  await expect(page.getByTestId("explanation")).toContainText("top pair");
  console.log(`full hand entered with ${clicks} clicks in ${entryMs} ms (scripted)`);
  expect(clicks).toBeLessThanOrEqual(15);

  // History has the hand and can reopen it.
  await click("history-open");
  await expect(page.getByTestId("history")).toContainText("BTN");
  await page.getByTestId("history").locator("li button").first().click();
  await expect(page.getByTestId("result")).toBeVisible();
  await expect(page.getByTestId("pot")).toContainText("Pot 550");
});

test("Sit & Go push/fold spot", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("format-sng").click();
  await page.getByTestId("hero-stack-bb").fill("10");
  await page.getByTestId("stacks-equal").click();
  await page.getByTestId("card-As").click();
  await page.getByTestId("card-Ah").click();
  await page.getByTestId("fold-to-hero").click();
  await page.getByTestId("analyze").click();
  await expect(page.getByTestId("result-action")).toHaveText(/^All-in/, { timeout: 15_000 });
  await expect(page.getByTestId("result")).toContainText("Bubble factor");
});

test("backend validation errors are shown", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("format-sng").click();
  await page.getByTestId("payouts").fill("");
  await page.getByTestId("payouts").blur();
  await page.getByTestId("card-Ah").click();
  await page.getByTestId("card-Kd").click();
  await page.getByTestId("fold-to-hero").click();
  await page.getByTestId("analyze").click();
  await expect(page.getByTestId("error")).toContainText("payouts");
});

test("screenshot of a result", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 1100 });
  await page.goto("/");
  for (const c of ["card-Ah", "card-Kd", "fold-to-hero", "act-raise", "act-fold", "act-call", "street-flop", "card-Kh", "card-7c", "card-2d", "act-call", "analyze"])
    await page.getByTestId(c).click();
  await expect(page.getByTestId("result")).toBeVisible({ timeout: 15_000 });
  await page.screenshot({ path: process.env.SCREENSHOT ?? "test-results/result.png", fullPage: true });
});
