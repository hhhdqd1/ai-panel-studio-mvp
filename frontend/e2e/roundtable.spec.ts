import { expect, test } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

const screenshots = resolve(process.cwd(), '../docs/screenshots');

test('a roundtable survives refresh, locates risks, and reaches a natural summary', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('讨论议题').fill('AI 与教育如何共存？');
  await page.getByRole('button', { name: '创建圆桌' }).click();
  await expect(page.getByRole('button', { name: '确认阵容，开始讨论' })).toBeVisible();
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
  mkdirSync(screenshots, { recursive: true });
  await page.screenshot({ path: resolve(screenshots, 'desktop.png'), fullPage: true });

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
  await page.screenshot({ path: resolve(screenshots, 'mobile.png'), fullPage: true });
});

test('two roundtables do not mix their discussion records', async ({ page }) => {
  async function create(topic: string) {
    await page.goto('/');
    await page.getByLabel('讨论议题').fill(topic);
    await page.getByRole('button', { name: '创建圆桌' }).click();
    await expect(page.getByRole('button', { name: '确认阵容，开始讨论' })).toBeVisible();
    return page.url();
  }
  const first = await create('教育资源分配');
  const second = await create('城市绿地规划');
  expect(first).not.toBe(second);
  await page.getByRole('button', { name: '确认阵容，开始讨论' }).click();
  await expect(page.getByRole('heading', { name: '主持人总结' })).toBeVisible();
  await page.goto(first);
  await page.getByRole('button', { name: '确认阵容，开始讨论' }).click();
  await expect(page.getByRole('heading', { name: '主持人总结' })).toBeVisible();
  await expect(page.getByRole('region', { name: '实时讨论记录' })).toContainText('教育资源分配');
  await expect(page.getByRole('region', { name: '实时讨论记录' })).not.toContainText('城市绿地规划');
  await page.goto(second);
  await expect(page.getByRole('region', { name: '实时讨论记录' })).toContainText('城市绿地规划');
  await expect(page.getByRole('region', { name: '实时讨论记录' })).not.toContainText('教育资源分配');
});
