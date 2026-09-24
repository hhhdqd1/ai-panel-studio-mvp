import { expect, test } from '@playwright/test';

test('a roundtable survives refresh, locates risks, and reaches a natural summary', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('讨论议题').fill('AI 与教育如何共存？');
  await page.getByRole('button', { name: '创建圆桌' }).click();
  await expect(page.getByRole('button', { name: '确认阵容，开始讨论' })).toBeVisible();
  await expect(page.getByRole('region', { name: '阵容预览' })).toContainText('视角1');
  await page.screenshot({ path: test.info().outputPath('panel-preview.png'), fullPage: true });
  await page.getByRole('button', { name: '确认阵容，开始讨论' }).click();
  await expect(page.locator('[data-testid="transcript-message"]').first()).toBeVisible();
  await expect(page.locator('.round-seat.seat-active')).toHaveCount(1);
  await page.reload();
  await expect(page.getByRole('heading', { name: '主持人总结' })).toBeVisible();
  await expect(page.getByText('具体效果和数字待核实。')).toBeVisible();
  await expect(page.getByRole('link', { name: /查看原发言/ })).toBeVisible();
  await expect(page.locator('body')).not.toContainText('chain_of_thought');
  await expect(page.locator('body')).not.toContainText('{"consensus"');

  // Capture the authored seed panel for the handoff screenshots, after the
  // newly created discussion has already exercised the full workflow.
  await page.goto('/');
  await page.getByRole('link', { name: /中小学是否应该引入 AI 个性化学习助手/ }).click();
  const seedStart = page.getByRole('button', { name: '确认阵容，开始讨论' });
  const seedSummary = page.getByRole('heading', { name: '主持人总结' });
  await expect(seedStart.or(seedSummary)).toBeVisible();
  if (await seedStart.isVisible()) await seedStart.click();
  await expect(seedSummary).toBeVisible();
  await expect(page.getByRole('link', { name: /查看原发言/ })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath('desktop.png'), fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('tab', { name: '洞察' }).click();
  await page.getByRole('link', { name: /查看原发言/ }).click();
  await expect(page.getByRole('tab', { name: '记录' })).toHaveAttribute('aria-selected', 'true');
  const sourceId = new URL(page.url()).hash.slice(1);
  await expect(page.locator(`#${sourceId}`)).toHaveAttribute('data-active', 'true');
  const dimensions = await page.evaluate(() => ({
    viewport: window.innerWidth,
    page: document.documentElement.scrollWidth,
    scroll: document.querySelector('.transcript-list')?.scrollHeight ?? 0,
    visible: document.querySelector('.transcript-list')?.clientHeight ?? 0,
  }));
  expect(dimensions.page).toBe(dimensions.viewport);
  expect(dimensions.scroll).toBeGreaterThan(dimensions.visible);
  await page.screenshot({ path: test.info().outputPath('mobile.png'), fullPage: true });
});

test('two concurrently running roundtables do not mix their records', async ({ page, context }) => {
  async function create(target: typeof page, topic: string) {
    await target.goto('/');
    await target.getByLabel('讨论议题').fill(topic);
    await target.getByRole('button', { name: '创建圆桌' }).click();
    await expect(target.getByRole('button', { name: '确认阵容，开始讨论' })).toBeVisible();
    return target.url();
  }
  const first = await create(page, '教育资源分配');
  const secondPage = await context.newPage();
  const second = await create(secondPage, '城市绿地规划');
  expect(first).not.toBe(second);
  await Promise.all([
    page.getByRole('button', { name: '确认阵容，开始讨论' }).click(),
    secondPage.getByRole('button', { name: '确认阵容，开始讨论' }).click(),
  ]);
  await Promise.all([
    expect(page.getByRole('heading', { name: '主持人总结' })).toBeVisible(),
    expect(secondPage.getByRole('heading', { name: '主持人总结' })).toBeVisible(),
  ]);
  await expect(page.getByRole('region', { name: '实时讨论记录' })).toContainText('教育资源分配');
  await expect(page.getByRole('region', { name: '实时讨论记录' })).not.toContainText('城市绿地规划');
  await expect(secondPage.getByRole('region', { name: '实时讨论记录' })).toContainText('城市绿地规划');
  await expect(secondPage.getByRole('region', { name: '实时讨论记录' })).not.toContainText('教育资源分配');
  await secondPage.close();
});
