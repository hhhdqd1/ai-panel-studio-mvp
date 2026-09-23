import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import HomePage from '../src/pages/HomePage';
import * as api from '../src/api';

vi.mock('../src/api');

function renderHome() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/discussions/:id" element={<p>已进入讨论 test-id</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('HomePage', () => {
  beforeEach(() => {
    vi.mocked(api.listDiscussions).mockResolvedValue([]);
    vi.mocked(api.createDiscussion).mockResolvedValue({ id: 'test-id', status: 'generating_panel' });
  });
  afterEach(() => {
    cleanup();
    vi.resetAllMocks();
  });

  it('requires a nonblank topic', async () => {
    renderHome();
    const button = screen.getByRole('button', { name: '创建圆桌' });
    expect(button).toBeDisabled();
    await userEvent.type(screen.getByLabelText('讨论议题'), '  ');
    expect(button).toBeDisabled();
  });

  it('uses four experts by default and opens the created discussion', async () => {
    renderHome();
    await userEvent.type(screen.getByLabelText('讨论议题'), 'AI 与教育');
    await userEvent.click(screen.getByRole('button', { name: '创建圆桌' }));
    await waitFor(() => expect(api.createDiscussion).toHaveBeenCalledWith({ topic: 'AI 与教育', expert_count: 4 }));
    expect(await screen.findByText('已进入讨论 test-id')).toBeInTheDocument();
  });

  it('shows existing discussions with a continue link', async () => {
    vi.mocked(api.listDiscussions).mockResolvedValue([
      { id: 'seed-id', topic: '城市交通的未来', expert_count: 4, status: 'awaiting_confirmation', stage: null, created_at: '2026-09-23T00:00:00Z', updated_at: '2026-09-23T00:00:00Z' },
    ]);
    renderHome();
    expect(await screen.findByText('城市交通的未来')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /继续/ })).toHaveAttribute('href', '/discussions/seed-id');
  });
});
