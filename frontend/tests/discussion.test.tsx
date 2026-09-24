import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import DiscussionPage from '../src/pages/DiscussionPage';
import Roundtable from '../src/components/Roundtable';
import Transcript from '../src/components/Transcript';
import Insights from '../src/components/Insights';
import * as api from '../src/api';
import { baseSnapshot, newMessage } from './fixtures';

vi.mock('../src/api');

class QuietEventSource {
  addEventListener() {}
  close() {}
  onopen = null;
  onerror = null;
}

class RecordingEventSource {
  static latest: RecordingEventSource;
  url: string;
  listeners = new Map<string, (event: MessageEvent) => void>();
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(url: string) { this.url = url; RecordingEventSource.latest = this; }
  addEventListener(type: string, callback: (event: MessageEvent) => void) { this.listeners.set(type, callback); }
  emit(type: string, sequence: number, payload: object) {
    this.listeners.get(type)?.({ lastEventId: String(sequence), data: JSON.stringify(payload) } as MessageEvent);
  }
  close() {}
}

function renderDiscussion() {
  return render(<MemoryRouter initialEntries={['/discussions/test-id']}><Routes><Route path="/discussions/:id" element={<DiscussionPage />} /></Routes></MemoryRouter>);
}

describe('DiscussionPage', () => {
  beforeEach(() => {
    vi.stubGlobal('EventSource', QuietEventSource);
    vi.mocked(api.getDiscussion).mockResolvedValue(baseSnapshot);
  });
  afterEach(() => { cleanup(); vi.resetAllMocks(); vi.unstubAllGlobals(); });

  it('offers panel confirmation and starts only after a click', async () => {
    renderDiscussion();
    const preview = await screen.findByRole('region', { name: '阵容预览' });
    expect(within(preview).getByText('支持试点')).toBeVisible();
    expect(within(preview).getByText('教育')).toBeVisible();
    await userEvent.click(await screen.findByRole('button', { name: '确认阵容，开始讨论' }));
    expect(api.startDiscussion).toHaveBeenCalledWith('test-id');
  });

  it('shows a persisted review failure after refresh', async () => {
    vi.mocked(api.getDiscussion).mockResolvedValue({
      ...baseSnapshot, status: 'completed', messages: [newMessage],
      review_unavailable_message_ids: [newMessage.id],
    });
    renderDiscussion();
    expect(await screen.findByText(/本轮审查暂不可用/)).toBeVisible();
  });

  it('offers recovery when a discussion failed', async () => {
    vi.mocked(api.getDiscussion).mockResolvedValue({ ...baseSnapshot, status: 'failed', error_code: 'interrupted', resume_point: 'running' });
    renderDiscussion();
    await userEvent.click(await screen.findByRole('button', { name: '继续讨论' }));
    expect(api.resumeDiscussion).toHaveBeenCalledWith('test-id');
  });

  it('explains exhausted budget instead of offering a dead recovery button', async () => {
    vi.mocked(api.getDiscussion).mockResolvedValue({ ...baseSnapshot, status: 'failed', error_code: 'model_call_limit', resume_point: null });
    renderDiscussion();
    expect(await screen.findByText(/本场剩余模型调用预算不足/)).toBeVisible();
    expect(screen.queryByRole('button', { name: '继续讨论' })).not.toBeInTheDocument();
  });

  it('shows a natural-language summary without raw JSON', async () => {
    vi.mocked(api.getDiscussion).mockResolvedValue({ ...baseSnapshot, status: 'completed', summary: '先从小范围试点开始，并持续评估。' });
    renderDiscussion();
    expect(await screen.findByText('先从小范围试点开始，并持续评估。')).toBeInTheDocument();
    expect(screen.queryByText(/"consensus"/)).not.toBeInTheDocument();
  });

  it('switches among roundtable, transcript, and insights tabs', async () => {
    renderDiscussion();
    await screen.findByRole('tab', { name: '圆桌' });
    await userEvent.click(screen.getByRole('tab', { name: '记录' }));
    expect(screen.getByRole('tab', { name: '记录' })).toHaveAttribute('aria-selected', 'true');
    await userEvent.click(screen.getByRole('tab', { name: '洞察' }));
    expect(screen.getByRole('tab', { name: '洞察' })).toHaveAttribute('aria-selected', 'true');
  });

  it('starts streaming after the snapshot and retains content while reconnecting', async () => {
    vi.stubGlobal('EventSource', RecordingEventSource);
    renderDiscussion();
    await screen.findByRole('button', { name: '确认阵容，开始讨论' });
    expect(RecordingEventSource.latest.url).toContain('after=1');
    act(() => RecordingEventSource.latest.emit('message.created', 2, { message: newMessage }));
    expect(screen.getByText(newMessage.content)).toBeInTheDocument();
    act(() => RecordingEventSource.latest.emit('insight.review_unavailable', 3, { message_id: newMessage.id }));
    expect(screen.getByText(/本轮审查暂不可用/)).toBeInTheDocument();
    act(() => RecordingEventSource.latest.onerror?.());
    expect(screen.getByText(/正在重连，已保留现有内容/)).toBeInTheDocument();
    expect(screen.getByText(newMessage.content)).toBeInTheDocument();
  });
});

describe('live panels', () => {
  afterEach(cleanup);
  it('highlights the speaker seat and corresponding transcript entry', () => {
    const snapshot = { ...baseSnapshot, status: 'running' as const, agents: baseSnapshot.agents.map((agent) => agent.id === 'expert-a' ? { ...agent, public_status: 'speaking' } : agent), messages: [newMessage] };
    render(<><Roundtable snapshot={snapshot} /><Transcript snapshot={snapshot} activeMessageId={newMessage.id} /></>);
    expect(within(screen.getByRole('region', { name: '圆桌席位' })).getByText('甲专家').closest('[aria-current]')).toHaveAttribute('aria-current', 'true');
    expect(screen.getByText(newMessage.content).closest('[data-active]')).toHaveAttribute('data-active', 'true');
  });

  it('keeps the latest host question at the center of the table', () => {
    const hostMessage = { ...newMessage, id: 'host-question', agent_id: 'host', content: '请比较两种路径的证据与代价。' };
    render(<Roundtable snapshot={{ ...baseSnapshot, messages: [hostMessage] }} />);
    expect(screen.getByText(hostMessage.content).closest('.table-surface')).toBeInTheDocument();
  });

  it('links a claim-risk flag to the originating message', async () => {
    const locate = vi.fn();
    const insight = { ...baseSnapshot.insight, claim_flags: [{ message_id: newMessage.id, quote: '83%', reason_code: 'needs_external_check' as const, explanation: '无来源', status: 'open' as const }] };
    render(<Insights insight={insight} onLocateMessage={locate} />);
    await userEvent.click(screen.getByRole('link', { name: /查看原发言/ }));
    expect(locate).toHaveBeenCalledWith(newMessage.id);
  });
});
